# find_contact_linkedin_url

Resolve a contact's LinkedIn profile URL from name + company when the URL isn't already on the row. Two-tier strategy: provider match (Prospeo) + AI web-research fallback. Identity verification happens downstream — this function's only job is candidate-URL discovery.

## Why this exists

CRMs typically have name + company + maybe email for a contact, but rarely a hand-validated LinkedIn URL. Without a URL, every downstream contact-cleanup step fails (Harvest can't scrape what it can't find). This function turns the "name + company" minimum input into the URL the rest of the pipeline depends on, with a cost-aware tiering that doesn't burn AI calls when a cheap provider lookup will do.

## When to use

- The contact row is missing `linkedin_url` and the recipe needs to enrich it.
- Recipe-level pattern: gate this function with `run_if_js: "!row.input.linkedin_url"` so rows that already have a URL skip the waterfall entirely.

## When NOT to use

- The CRM has a hand-validated LinkedIn URL — don't burn the waterfall, pass directly to `enrich_contact_linkedin_profile`.
- You need to verify whether an existing URL is the right person — that's `validate_contact_identity`, which runs after the Harvest scrape.
- Bulk discovery / building TAM lists from scratch — use `apollo_people_search` directly with title + seniority filters; this function is for single-row resolution.

## Verification strategy

| Tier | Lookup | Runs when | Cost |
|---|---|---|---|
| 1 | `prospeo_enrich_person` (by email OR first+last+company_website) | always (when at least name OR email present) | 1 Prospeo credit |
| 2 | `deeplineagent` web research | tier-1 returned no URL OR returned a non-profile URL | one mid-cost AI call |

The function emits exactly one of: `tier_1_prospeo_enrich` | `tier_2_web_research` | `unfound`.

### Why Prospeo for tier 1

Set 2026-05-04 as the agency contact-side default. Prospeo's `enrich_person` is single-call, accepts the four most common identity keys (email, name+domain, name+company_name, linkedin_url), and returns the matched person's full record including `linkedin_url` plus email and (optionally, off here) mobile. When email is present, match precision is highest; for name+domain, it's still solid because domain anchors the company.

Prospeo is preferred over Apollo for contact-side resolution because:
- **Cleaner URL coverage on B2B SaaS contacts** — Prospeo's index is contact-side-first, where Apollo's strength is account-side firmographics.
- **Single call returns the URL + email + firmographics** — when the recipe also wants email (Layer-3 `find_contact_email` opt-in), Prospeo can collapse two calls into one.
- **Per-credit pricing scales predictably** at the agency's typical row volumes.

Apollo `people_match` remains a viable client-override swap for engagements where Apollo's coverage outperforms Prospeo on a representative sample. Re-run a coverage bench before committing to a swap.

### Why deeplineagent for tier 2

When Apollo misses, the only viable fallback is web research. The deeplineagent's web-search tools find the canonical LinkedIn URL by searching "<name> <company> linkedin profile" and constraining to `linkedin.com/in/`. This is the same pattern as `linkedin_url_verified`'s tier 2 — proven, cheap, and stops here (no further verification needed in THIS function).

## Why no identity verification in this function

The function's only output is a candidate URL. Whether the URL belongs to the right person is `validate_contact_identity`'s responsibility — it runs against the Harvest scrape (which has the full profile, not just a URL) and emits `confirmed | weak | mismatch`. Folding identity verification into this function would force a Harvest call here, doubling the spend on rows whose URL is wrong (you'd scrape the wrong person, then discover it's wrong, then start over).

The split is the same architecture pattern as account-side: `linkedin_url_verified` finds + verifies in one function because Lusha returns firmographics for free with the URL (verifying is just a fuzzy-match step on data already paid for). Contact-side has separate cost models (URL providers vs. profile scraper), so the verification step lives downstream of the scrape.

## Inputs / outputs

See `function.yaml`.

The contract works with minimum `(first_name, last_name, company_name_clean)`. Pass `email` and `company_domain` when available — both materially improve Apollo's tier-1 precision.

## Gotchas

- **Prospeo can return `linkedin_url` for a same-named person at a different company.** When `company_website` (domain) is missing, the match key collapses to `(first_name, last_name)` which is non-unique. Always pass `company_domain` when you have it. Identity verification downstream catches mismatches but doesn't avoid the Harvest spend on the wrong person.
- **Prospeo's response shape has multiple possible URL paths.** The compose step checks `result.person.linkedin_url`, `result.data.person.linkedin_url`, `result.linkedin_url`, `result.data.linkedin_url` in order. If Prospeo's response shape changes upstream, all four paths null and the row falls to tier 2 — monitor `verification_signals.tier_1.raw_url=null` rate as a schema-drift signal.
- **Prospeo sometimes returns LinkedIn company URLs instead of profile URLs.** The compose step filters with `linkedin.com/in/` — anything else falls through to tier 2.
- **Tier 2's web research can hallucinate URLs.** The deeplineagent prompt constrains the URL format, but agents occasionally return plausible-looking URLs that 404. The downstream Harvest call handles this gracefully (returns `profile_json: null`), but the row is still spend on the agent call. Monitor the `tier_2_web_research.url_found=true && Harvest fails` rate as a quality signal.
- **No tier 3 by design.** The agency catalog principle is "cheap waterfall providers first, AI fallback once, stop." Adding a tier 3 (e.g. Apollo) is plausible but adds cost without proven coverage gains. Re-run the bench against a customer-representative sample before adding tiers.

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/find_contact_linkedin_url.workflow.json)"
deepline workflows call --workflow-id <ID> --payload '{
  "first_name": "Bill",
  "last_name": "Gates",
  "company_name_clean": "Bill & Melinda Gates Foundation",
  "company_domain": "gatesfoundation.org"
}'
# Expect: linkedin_url contains "linkedin.com/in/williamhgates",
#   found=true, linkedin_url_source="tier_1_prospeo_enrich".
```

For a row that should fall to tier 2 (made-up name to force Apollo miss):
```bash
deepline workflows call --workflow-id <ID> --payload '{
  "first_name": "Zxqv",
  "last_name": "Mqwx",
  "company_name_clean": "Acme Corp",
  "company_domain": "acme-doesnt-exist-2026.com"
}'
# Expect: found=false, linkedin_url_source="unfound", verification_signals.tier_2.ran=true.
```

## Related

- **Upstream:** `normalize_domain_and_name` (when `company_name_clean` isn't already on the row).
- **Downstream:** `enrich_contact_linkedin_profile` (consumes the URL this function emits).
- **Sibling (account-side):** `linkedin_url_verified` — account-side does URL discovery + verification + firmographics in one function because Lusha's payload makes it free; contact-side splits the steps because cost models differ.
- **Identity verification (downstream):** `validate_contact_identity` — gates the URL against the scraped profile.
