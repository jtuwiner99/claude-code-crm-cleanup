# linkedin_url_verified

Find a company's LinkedIn URL from its domain and confirm the URL actually belongs to that company. Two-tier strategy: cheap provider lookup with AI fuzzy-match verification, with an AI web-research fallback if the first tier doesn't match.

## Why this exists

Bare domain → LinkedIn URL lookups are unreliable. Providers will return *some* LinkedIn URL for nearly any domain, but it's frequently the wrong company (especially for short generic names, acquired entities, or holding-company structures). This function adds the verification layer that turns a noisy lookup into a trustworthy field — and falls back to web research when the cheap path doesn't match.

## When to use

Any time a downstream step needs the LinkedIn URL or LinkedIn-derived firmographics, and the caller cannot tolerate "wrong company" silent failures. Specifically: before any segmentation, qualification, or routing logic that conditions on LinkedIn data.

## When NOT to use

- The source system already provides a hand-validated LinkedIn URL (e.g. CRM where a human linked it).
- You're enriching a contact, not a company.

## Verification strategy

| Tier | Lookup | Verification | Runs when | AI cost |
|---|---|---|---|---|
| 1 | Lusha `enrich_company(domain)` | gpt-5-mini (agency default) fuzzy-match using a strict matching-engine system prompt | always | one cheap call |
| 2 | deeplineagent web-research → PDL `enrich_company(linkedin_url)` | same matching-engine prompt on the new payload | tier-1 fuzzy-match returned `is_match: false` | one mid + one cheap |

The function emits exactly one of: `tier_1_provider_match` | `tier_2_web_research_match` | `unverified`.

### Why Lusha for tier 1

Empirical 30-domain bench (`tmp/linkedin-waterfall-test/`, 2026-05-04) on a representative pilot CRM:

| Provider | Hit rate | Cost/hit | Avg latency |
|---|---|---|---|
| **Lusha** | **27/30 (90%)** | **~$0.0045** | **1.34s** |
| PDL | 27/30 (90%) | ~$0.10 | 1.79s |
| Crustdata | 23/30 (77%) | ~$0.09 | 4.70s |

Lusha and PDL miss the *same* 3 domains (parked, defunct, or typo'd) — a Lusha→PDL cascade caught zero additional rows in the bench, so paying for both is wasted spend. Lusha alone, with the AI fuzzy-match verification still gating the result, is the right tier 1.

Crustdata is strictly dominated: slower, lower hit rate, and missed real B2B SaaS companies that Lusha and PDL both caught.

## Why no deterministic tier

An earlier scaffold had a deterministic "domain string-match" tier ahead of the AI fuzzy match. Removed during the Clay port — Clay's logic is AI-only, with the matching engine's system prompt encoding the deterministic rules (exact root match, subdomain match, brand-family/regional domain) inside the AI's decision priority. This is more permissive on legitimate edge cases (regional subsidiaries, brand families) at the cost of one extra cheap-AI call per row. If you need deterministic-only, use a different function.

## Inputs / outputs

See `function.yaml`.

The contract REQUIRES `company_summary` upstream. The matching engine uses it as one of its three signals (alongside the LinkedIn description and the company domains). Without it, tier 1 verification accuracy drops sharply on similarly-named-but-different companies.

## Provider substitution

Clay's source table uses MixRank `enrich-company-with-mixrank-v2`. Deepline has no MixRank tool. v1.0.0 ported to PDL; v1.1.0 (2026-05-04) swapped tier 1 to Lusha after the bench above. PDL is retained for tier 2 because Lusha's input schema only accepts `domain`, not `linkedin_url` — and tier 2's whole job is to re-enrich the URL the AI web-research found.

Lusha response → output mapping (handled in `compose_output`):

| Output field | Lusha path | PDL path (tier 2) |
|---|---|---|
| `linkedin_url` | `result.data.social.linkedin.url` (https-prefixed; stripped) | `result.data.linkedin_url` (bare) |
| `company_name_provider` | `result.data.name` | `result.data.name` |
| `website_provider` | `result.data.domain` | `result.data.website` |
| `description_provider` | `result.data.description` | `result.data.description` |
| `employee_size_band` | `result.data.employees` (e.g. `"10001 - 100000"`) | `result.data.size` (e.g. `"11-50"`) |
| `industry` | `result.data.mainIndustry` (fallback `industry`) | `result.data.industry` |
| `founded_year` | `result.data.founded` (string, parsed to int) | `result.data.founded` (int) |
| `full_provider_payload` | raw Lusha `result.data` | raw PDL `result.data` |

Client-level overrides MAY swap providers if cost or coverage drives the choice — see top-level README on resolution order. PDL remains a viable tier-1 substitute for engagements where Lusha's coverage gaps are a problem (notably EU long-tail and SMB). Re-run the bench on a customer-representative sample before committing.

## Caching `full_provider_payload`

The function exposes the verifying tier's full PDL payload. Downstream functions that need richer firmographics (and that we may eventually build on top of Harvest) can read the cached PDL fields directly without a redundant lookup. Open question on whether the compiler should make this passthrough automatic — see top-level README.

## Gotchas

- **`company_summary` of "N/A" weakens tier 1 considerably.** When the upstream summary function returns "N/A" (dead site, blocked page), tier 1 verification has only domain + name to work with. Caller may want to short-circuit and skip this function entirely on summary="N/A" rows rather than spending the AI calls.
- **Tier 2's web research may return URLs that don't actually exist on LinkedIn.** The flow re-runs PDL with the new URL and re-verifies — if PDL can't enrich the URL, tier 2 stays `ran=true, is_match=false` and the final answer is `unverified`. Don't trust `tier_2_web_research.linkedin_url` directly without the re-verification.
- **Don't trust `linkedin_url` when `verified=false`.** The function emits `linkedin_url=null` in that case, but if a future change populates a best-guess, callers must continue to gate on `verified` not on `linkedin_url`.
- **Size-band string format differs between tiers.** Lusha emits e.g. `"10001 - 100000"` (spaces around the dash); PDL emits e.g. `"10001+"` or `"11-50"` (no spaces). Code that does `if (employee_count >= 50)` will not work — map the band to a min-count first, and tolerate both formats.
- **Lusha can return wrong-company URLs at non-trivial rates.** From the v1.1.0 bench: ~10% of Lusha "hits" were a wrong-but-similarly-named company (e.g. `mosaicapp.com` → `linkedin.com/company/mosaicnyc`). The matching-engine fuzzy-match catches these and bumps to tier 2; the verified-hit rate (post-AI gate) is ~85%, not 90%. Don't relax the verification step on Lusha — it's load-bearing.
- **Lusha coverage skews US/B2B-SaaS.** Lusha is known to be weaker on EU long-tail and on SMB. For enrichment projects heavy on those segments, re-run the bench against a representative sample and consider falling back to PDL as tier 1.

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/linkedin_url_verified.workflow.json)"
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "stripe.com",
  "company_name_clean": "Stripe",
  "company_summary": "Stripe is a payments infrastructure company that builds APIs and tools for online businesses to accept payments, manage subscriptions, and operate financial workflows. Sells primarily to internet businesses, software platforms, and enterprises."
}'
# Expect: linkedin_url=https://www.linkedin.com/company/stripe, verified=true,
#   verification_tier=tier_1_provider_match
```
