# detect_acquisition

Detect whether a company has been acquired or merged into another company, identify the acquirer, and distinguish a true acquisition from a DBA / rebrand.

## Status: opt-in add-on (NOT default)

This function is **opt-in**, not part of the default account-enrichment recipe. Most engagements don't need M&A detection — the default spine treats every domain as an independent entity.

**Use this function when:**

- The your TAM is in an M&A-heavy vertical (PE-backed targeting, strategic-buyer-driven categories, mature SaaS where consolidation is active).
- Scoping flagged duplicate parent/child records as a quality problem in the CRM.
- If your motion is ABM-style and a routed-to-parent-record duplicate is a deal-breaker.
- You have explicit business rules around acquired-company handling (drop, tag-as-child, route-to-parent's owner).

**Skip this function when:**

- M&A is rare in your market and the cost of one AI call per row outweighs the signal.
- You don't care which legal entity owns a brand — your team sells to brand-level decision makers regardless.
- The default recipe is already producing acceptable record quality.

## Why this exists

Acquired companies create routing ambiguity in CRMs. Three failure modes the default recipe doesn't catch:

1. **Absorbed brand still in the CRM**: Clearbit was acquired by HubSpot in 2023. clearbit.com now redirects, all employees moved to hubspot.com emails, the brand is dissolved. A CRM record for "Clearbit" routes a rep to a non-existent entity.
2. **Acquired-but-still-independent brand**: Slack was acquired by Salesforce, but slack.com is still active and the brand operates independently. The right CRM behavior is "tag as a child of Salesforce, keep enriching" — not "drop".
3. **DBA / rebrand mistaken for acquisition**: ClickUp dba Mango Technologies. Mango Technologies is the legal entity, ClickUp is the brand — same company. Naive M&A detection flags this as acquired and corrupts the record.

This function emits programmatic signals that let a calling recipe handle each case correctly. It pairs with `acquired_brand_status` (which validates whether the acquired brand is still operating) to produce the full M&A picture.

## Two AI tiers

| Tier | Purpose | Cost |
|---|---|---|
| 1. detection_and_analysis | Combined acquisition detection + acquirer/acquired extraction + DBA-vs-acquisition disambiguation. Always runs. Returns `is_acquired`, `is_dba_rebrand`, `acquirer_name`, `acquired_company_name`, `canonical_company_name`, `canonical_company_domain`, confidence + reasoning. | One AI call (~$0.005, gpt-5-mini, ~3500 tokens). |
| 2. acquirer_and_original_domain | Acquirer's root domain + acquired company's original pre-acquisition domain + new product page URL (e.g. clari.com/products/groove/) when one exists. Runs ONLY when tier 1 returned `is_acquired=true`. | One AI call (~$0.003, gpt-5-mini, ~1500 tokens). Skipped on non-acquired rows. |

Total: ~$0.008/row when acquired, ~$0.005/row otherwise. Cost shape favors customer recipes where the acquired-rate is low — the second-tier lookup is gated.

## Pipeline placement

```
normalize_domain_and_name
       ↓
verify_domain_alive (drop if !is_keepable)
       ↓
company_summary_from_website
       ↓
detect_acquisition  ← here (opt-in)
       ↓ (gate downstream on is_acquired === false || acquired_brand_status.status === 'independent')
linkedin_url_verified
       ↓
extract_hq_address
       ↓
classify_via_latitude
```

This function comes AFTER `company_summary_from_website` because it consumes the summary as grounding for the detection prompt — the AI uses the summary to disambiguate DBA-vs-acquisition without re-fetching the website.

It comes BEFORE `linkedin_url_verified` and the rest of the spine when you want to drop or re-key acquired records before further enrichment burns provider credits. (Recipes that want to keep acquired records and merely tag them can run this in parallel with the rest of the spine.)

## Inputs / outputs

See `function.yaml` for the typed contract. Three things worth highlighting:

1. **`company_summary` is required.** The detection prompt uses it as grounding so the AI doesn't have to re-fetch the website. Without it, accuracy on edge-case DBA-vs-acquisition drops materially.
2. **`canonical_company_name` and `canonical_company_domain` are ALWAYS populated.** Callers can bind to these fields without conditional logic — they're the right values for downstream CRM record keying regardless of branch.
3. **`is_acquired` is nullable.** Null means the AI step failed (treat as "not checked", NOT as `false`). Recipe authors should branch on `is_acquired === true` and `is_acquired === false` explicitly, never on truthiness.

## Default-to-not-acquired semantics

The function defaults to NOT flagging as acquired when uncertain:

- AI step failure → `is_acquired=null`, `acquirer_*` and `acquired_*` fields all null.
- `ma_outcome=none` (no evidence found) → `is_acquired=false`.
- `is_dba_rebrand=true` ALWAYS overrides → `is_acquired=false`. A rebrand is not an acquisition, even if the AI initially detected M&A language (e.g. "Right Networks rebranded to Rightworks" might trigger acquisition keywords; the DBA check catches this).

Why err on independent: false positives (incorrectly flagging an independent company as acquired) drop legitimate prospects from downstream enrichment when the recipe runs in M&A-strict mode. False negatives (missing an acquisition) cost a duplicate-enrichment downstream but don't drop a real customer.

## What this function does NOT cover

- **Whether the acquired brand is still operating.** That's `acquired_brand_status` — chain it after this function (gate on `is_acquired === true`) to determine `independent` vs. `absorbed` vs. `inactive`.
- **Native subsidiaries / divisions WITHOUT an acquisition event** (e.g. Delta's rescue-mission subsidiary, VLOX-style aviation parent-child portfolios). Those have parent-child relationships but no M&A event to detect. Tracked as the planned `detect_corporate_structure` future-extension function — see `enrichment-functions-catalog`.
- **CRM-side routing or merge logic.** This function emits the M&A signals; the calling recipe decides what to do with them (drop the record, tag as child, route to acquirer's owner, etc.).

## Gotchas

- **DBA disambiguation is the failure mode that matters most.** ClickUp dba Mango Technologies, Stripe dba Stripe Inc — the AI must NOT flag these as acquisitions. The detection prompt explicitly instructs the model to treat DBA / rebrand as separate from acquisition. Smoke-test against ClickUp before shipping a recipe.
- **The Wayback Machine may not have the original-domain snapshot.** When tier 2 returns `acquired_original_domain=null`, the function still emits a valid result — downstream callers should treat null as "unknown original domain" and fall back to the input domain (which is what the canonical_company_domain field already does).
- **Confidence numeric mapping is not from a model.** `acquisition_confidence` is `{confirmed: 85, likely: 65, none: 10}` — a static map from `ma_outcome`. It is NOT a model-emitted score. Callers wanting a true model-graded probability should use the `verification_signals.detection_and_analysis.ma_outcome` enum directly and apply their own threshold.
- **Cost scales with acquired-rate.** Tier 2 fires only on acquired rows. A customer with a 5% acquired-rate pays ~$0.005 + 0.05 × $0.003 ≈ $0.0052/row average. A customer with a 30% acquired-rate pays ~$0.005 + 0.30 × $0.003 ≈ $0.0059/row average. Modest cost variance.
- **Domain-redirect signal is NOT directly checked here.** This function reasons about acquisition from web research + summary + AI judgment. Whether the input domain currently redirects to a live acquirer site is `acquired_brand_status`'s job (it consumes `verify_domain_alive.final_url`). Don't replicate the redirect check in this function.

## Future integration

A configuration UI for "always-on defaults vs. opt-in toggles" is not yet built. Once it ships, this function will appear under the M&A toggle alongside `acquired_brand_status`. Until then, recipe authors enable it explicitly per project.

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/detect_acquisition.workflow.json)"

# Case 1: classic absorbed acquisition (Clearbit → HubSpot, 2023)
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "clearbit.com",
  "company_name_clean": "Clearbit",
  "company_summary": "Clearbit was a B2B data enrichment and intent platform. Acquired by HubSpot in November 2023; the brand is now Breeze Intelligence under HubSpot."
}'
# Expect: is_acquired=true, is_dba_rebrand=false, acquirer_name="HubSpot",
#   acquirer_domain="hubspot.com", acquired_original_domain="clearbit.com",
#   acquisition_confidence=85, canonical_company_name="Clearbit"

# Case 2: independent (no M&A event)
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "workato.com",
  "company_name_clean": "Workato",
  "company_summary": "Workato is an integration and automation platform for the enterprise..."
}'
# Expect: is_acquired=false, is_dba_rebrand=false, acquirer_name=null,
#   acquisition_confidence=10, canonical_company_name="Workato"

# Case 3: acquired but still independently operated brand (Slack → Salesforce)
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "slack.com",
  "company_name_clean": "Slack",
  "company_summary": "Slack is a business communication platform; acquired by Salesforce in 2021 but operates independently as Slack Technologies, LLC..."
}'
# Expect: is_acquired=true, is_dba_rebrand=false, acquirer_name="Salesforce",
#   acquirer_domain="salesforce.com", canonical_company_name="Slack"
# Note: this function only says "acquired"; whether Slack is still operating
# independently is acquired_brand_status's call.

# Case 4: DBA — must NOT be flagged as acquired (reference example)
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "clickup.com",
  "company_name_clean": "ClickUp",
  "company_summary": "ClickUp is a project management and productivity platform; the legal entity is Mango Technologies, Inc., dba ClickUp..."
}'
# Expect: is_acquired=false, is_dba_rebrand=true, acquirer_name=null,
#   canonical_company_name="ClickUp", canonical_company_domain="clickup.com"
```

## Clay parity

Source: Clay table `(f) Check Acquisition Status + Verify Company Name` (ported from production Clay table). Five AI calls in the Clay version (gpt-4o + clay-neon mix); we collapse to two structured-JSON deeplineagent calls on gpt-5-mini.

Field-by-field mapping vs. Clay table outputs:

| Clay column | Port output | Notes |
|---|---|---|
| `Acquired` | `is_acquired` | Same boolean. DBA cases now correctly return false (Clay table did not gate this). |
| `(o) Acquiring Company Name` | `acquirer_name` | Same name; null when `is_acquired=false` (Clay returned blank). |
| `(o) Acquiring Company Domain` | `acquirer_domain` | Same value; verified via tier-2 web research. |
| `(o) Acquired Company` | `acquirer_name`'s counterpart — folded into `canonical_company_name` when acquired | Clay had a separate field; the port uses canonical_company_name = acquired-co brand name when acquired. |
| `(o) Acquired Company's Original Domain` | `acquired_original_domain` | Same value. |
| `(o) Independent Company Name` | `canonical_company_name` (when `is_acquired=false`) | Clay had two parallel name fields; port uses one canonical field always populated. |
| `(o) Independent Company Domain` | `canonical_company_domain` (when `is_acquired=false`) | Same simplification as above. |
| `(o) New Product Page URL` | `new_product_page_url` | Same value. Null when no dedicated landing page exists. |
| `Confidence Category` (very_high/high/medium/low/different_companies) | `verification_signals.detection_and_analysis.company_domain_match_confidence` | Available in audit trail; not promoted to a top-level output. |
| `M&A Analysis Reason` | `verification_signals.detection_and_analysis.reasoning` | Available in audit trail. |
| `Explanation` (Company-Domain Match) | Folded into `verification_signals.detection_and_analysis.reasoning` | Combined reasoning field. |

The Clay table also did dozens of normalize-domain / normalize-name actions and a downstream "write to other table" step — those are upstream-of-this-function (`normalize_domain_and_name` already runs) and recipe-level (CRM writeback is per-project), not function-level.
