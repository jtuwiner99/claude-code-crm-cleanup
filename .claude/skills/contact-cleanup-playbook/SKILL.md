---
name: contact-cleanup-playbook
description: Use this skill when scoping or building a enrichment project that involves contact CRM cleanup — verifying who's still at the on-record company, classifying persona/seniority, scoring contact fit, or detecting job changes. Covers the contact-enrichment spine (`find_contact_linkedin_url` → `enrich_contact_linkedin_profile` → `validate_contact_identity` → `detect_job_change` → `classify_multi_dim_via_latitude` → `score_contact_fit`), worked examples, persona-taxonomy choice per customer, scoring-rules JSON authoring, recipe composition with the static-cleanup vs ongoing-job-change-loop variants, and what's deferred (email/mobile waterfalls, AI-driven contact scoring).
---

# Contact-cleanup playbook

The operational guide for cleaning up B2B contacts in your CRM — confirming identity, detecting job changes, classifying persona + seniority, and scoring fit. Covers when to use the static spine vs the ongoing job-change loop, how to choose a persona taxonomy per customer, and how the six contact-side enrichment functions compose.

## When to invoke this skill

- A you notice "half our contacts have left", "our SDRs are calling people who don't work there anymore", or "we don't even know if these contacts are at the company anymore".
- Your project scope includes contact cleanup (not just account cleanup).
- You're about to scaffold a new contact-side enrichment function — read this skill first; the spine is already covered.
- A customer wants to detect contacts who recently moved jobs (high-value-contact trigger). Use the `contact_job_change_loop` recipe.
- Recipe-composition work where the contact spine is being added to your `enrichment-recipe.yaml`.

## Contact cleanup is the default for any contact-engagement, not a toggle

Unlike M&A detection (opt-in per customer because most customers don't need it), contact cleanup IS the default for any engagement that includes contacts in scope. The reasoning: ~25% of B2B SaaS contacts change roles every 18 months — every your CRM is rotting on the contact side, no exception. The only question is which Layer-3 add-ons to enable (email finding, mobile finding, AI-driven scoring), not whether to run the spine.

The toggles to consider:

| Add-on | Status | Turn on when |
|---|---|---|
| Layer-3 `find_contact_email` | deferred | Outbound motion includes email AND Harvest's single-call `find_email=true` flag isn't sufficient (need provider waterfall for deliverability long-tail). |
| Layer-3 `find_contact_mobile` | deferred | Outbound motion includes phone (cold dialing, SMS). |
| AI-driven contact scoring | deferred | Your scoring rules require narrative judgment (complex C-suite-level overrides, edge cases). Default `score_contact_fit` (deterministic) covers the typical case. |

## The cleanup pipeline (six functions)

```
find_contact_linkedin_url (skipped if URL on row)
       ↓
enrich_contact_linkedin_profile  ← Harvest direct API
       ↓
validate_contact_identity (gate: identity_match !== 'mismatch')
       ↓
detect_job_change
       ↓
classify_multi_dim_via_latitude (persona + seniority in ONE call)
       ↓
score_contact_fit  ← deterministic JS, not Latitude
```

Each step's cost defends the next step's cost — don't scrape if no URL, don't validate if no profile, don't classify or score on mismatched identity.

| Step | What it does | Cost | When it runs |
|---|---|---|---|
| 1. `find_contact_linkedin_url` | Resolve URL from name + company. Prospeo `enrich_person` (tier 1) → deeplineagent web research (tier 2). | ~$0.006 (Prospeo); +$0.01 if tier 2 fires | Skipped at recipe level when row already has `linkedin_url` |
| 2. `enrich_contact_linkedin_profile` | Single Harvest direct API call. Returns full profile JSON + hoisted convenience fields. | ~$0.001 baseline (~$0.005 with `find_email=true`, ~$0.003 with `include_about_profile=true`) | Always (when URL present from step 1 or row.input) |
| 3. `validate_contact_identity` | Deterministic name + company match + AI tiebreaker on signal-split rows. Emits `confirmed | weak | mismatch`. | $0 deterministic; ~$0.0008 AI tiebreaker on ~30-40% of rows | Always (when profile present) |
| 4. `detect_job_change` | Pure deterministic JS comparison of scraped current employer vs on-record. | $0 | Always (when profile present) |
| 5. `classify_multi_dim_via_latitude` | One Latitude call → persona + seniority. | ~$0.012 | Always (when identity not mismatched) |
| 6. `score_contact_fit` | Deterministic aggregation: `still_there + persona + seniority` → `ideal | acceptable | not_ideal`. | $0 | Always (when classification present) |

Total cost per row, typical: ~$0.020 baseline (URL on row) to ~$0.030 (URL discovery fires + Harvest + Latitude classification). Materially cheaper than Clay's per-row AI cleanup workflows (~$0.10+ per row in many production builds).

## The two recipes

### `default_contact_cleanup` (one-time spine)

Reference template at `enrichment-functions/recipes/default_contact_cleanup.yaml`. Use this for:

- A first contact-cleanup pass — running the spine over their full contact CRM export.
- Quarterly / annual freshness sweeps.
- Onboarding a new SDR's call list.

### `contact_job_change_loop` (recurring, subset)

Reference template at `enrichment-functions/recipes/contact_job_change_loop.yaml`. Lighter-weight — skips URL discovery, identity validation, and classification. Just refreshes employer + emits movement signal.

Use this for:

- Weekly / monthly recurring job-change detection on contacts already cleaned by the static recipe.
- High-value-contact (HVC) movement triggers — when a target buyer at a target company moves to a new company, the recipe emits a Slack notification or CRM event.

The `started_role_within_3_months` boolean is the hot signal — recently-moved contacts are typically the highest-value re-engagement targets (new role, new pain points, fresh budget cycle).

## Persona taxonomy choice (the key per-project decision)

The default persona taxonomy lives at `enrichment-functions/preset_categories/contact_department.yaml`:

- `marketing` | `sales` | `revenue_operations` | `customer_success` | `product` | `engineering` | `finance` | `people_ops` | `executive` | `other`

This works for typical B2B SaaS engagements where the ICP is Director-and-above in Marketing/Sales/RevOps.

Override the taxonomy per-project when:

- **Your ICP is vertical-specific.** A finance-vertical contact taxonomy might be `compliance`, `investor_relations`, `legal`, `capital_markets`, `finance`, `operations`, `tax`, `business_development`, `investment_bank`, `technology`, `deal_team`, `executive`, `general`. If your end customers are PE firms, hedge funds, or law firms, this is the right taxonomy — don't force the default.
- **If your go-to-market is product-led, not sales-led.** Default emphasizes sales/marketing/revops; PLG motions often want `product`, `engineering`, `data`, `executive` as the main buckets (with sales/marketing folded into `executive` or `other`).
- **Customer has multiple ICP sub-types** with different personas per sub-type. Define one taxonomy per sub-type and let the recipe branch.

Override mechanism: place a project-specific YAML at `<project-root>/preset_categories/contact_persona.yaml`. Reference it in the recipe's `dimensions[].categories_json` load path.

Always pair the persona taxonomy with a matching `target_personas` list in the user's `scoring-models/contact.json` — the values must be a subset of the active taxonomy.

## Scoring rules JSON

Per-project config at `<project-root>/scoring-models/contact.json`. Schema v1 documented at [`docs/schemas/contact-scoring-model.md`](../../../docs/schemas/contact-scoring-model.md). Minimal example:

```json
{
  "schema_version": 1,
  "object_type": "contact",
  "still_there_required": true,
  "target_personas": ["sales", "revenue_operations", "marketing", "executive"],
  "seniority_floor": "director",
  "seniority_ladder": ["ic", "senior_ic", "manager", "director", "vp_or_head", "c_level", "founder"]
}
```

The verdict:

- `ideal` — persona ∈ target_personas AND seniority >= floor AND (still_there OR !required)
- `acceptable` — persona ∈ target_personas OR seniority >= floor (XOR with ideal)
- `not_ideal` — neither AND/OR criteria met, OR identity_match=mismatch, OR !still_there with required=true

Authoring tips:

- **Start with default taxonomy values.** Before customizing, verify the default `contact_department.yaml` + `contact_seniority.yaml` cover the user's ICP. Often they do.
- **Set `seniority_floor` to "director" by default.** This matches a typical "Director+ in Marketing/Sales/RevOps" ICP rule. Loosen to `manager` for customers whose buyer is more practitioner-y; tighten to `vp_or_head` for high-ACV enterprise sales.
- **`still_there_required: true` by default.** Turn off only when scoring movers as ideal contacts at their NEW company is the recipe's intent (rare).
- **No weighted scoring in v1.** Binary in/out per axis. If a customer demands weighted scoring, build an AI-judged contact-scoring function instead.

## Worked examples

### Bill Gates @ Gates Foundation — confirmed, ideal

Inputs: `(first_name="William", last_name="Gates", company_name_clean="Bill & Melinda Gates Foundation", linkedin_url="https://www.linkedin.com/in/williamhgates")`.

Sequence:

1. `find_contact_linkedin_url` SKIPPED — `linkedin_url` already on row.
2. `enrich_contact_linkedin_profile` — Harvest returns full profile, `current_role.company_name="Bill & Melinda Gates Foundation"`.
3. `validate_contact_identity` — name match (Bill→William nickname expansion), company match in current role. `identity_match="confirmed"`. AI tiebreaker did NOT run.
4. `detect_job_change` — current company matches on-record. `status="still_there"`.
5. `classify_multi_dim_via_latitude` — persona=`executive`, seniority=`founder` (Latitude sees "Co-chair" + "Bill Gates" → founder bucket).
6. `score_contact_fit` — persona ∈ target list (executive yes), seniority ladder index for `founder` >= floor `director` → `score="ideal"`.

CRM action: contact stays in active prospecting list; persona + seniority writeback.

### Tim Cook with stale CRM record — moved (false positive caught by identity)

Inputs: `(first_name="Tim", last_name="Cook", company_name_clean="Microsoft", linkedin_url="https://www.linkedin.com/in/tcook")`.

Sequence:

1. URL on row → skip.
2. `enrich_contact_linkedin_profile` — Harvest returns Tim Cook's profile, current_role at Apple.
3. `validate_contact_identity` — name matches. Company match search across full experience: Tim Cook never worked at Microsoft. AI tiebreaker fires (deterministic split: name yes, company no). AI judges no-match. `identity_match="mismatch"`.
4. RECIPE GATES — `validate_contact_identity.identity_match !== 'mismatch'` is FALSE. Recipe stops here. `detect_job_change`, `classify_*`, `score_contact_fit` skipped.

CRM action: flag the row for human review — the URL on the CRM points to the wrong person. Don't write any signals back; the data is unreliable.

### Recently-moved RevOps leader — moved, recent, ideal target

Inputs: `(first_name="Jane", last_name="Doe", company_name_clean="OldCo", linkedin_url="<verified URL>")`. Used in the ongoing `contact_job_change_loop` recipe.

Sequence:

1. `enrich_contact_linkedin_profile` (`main_only=true`, cheap) — Harvest returns profile, current_role.company_name="NewCo", started Q1 2026.
2. `detect_job_change` — current=NewCo, on_record=OldCo, no name/domain match. `status="moved"`. Started 2 months ago → `started_role_within_3_months=true`.

Recipe-level: emit Slack alert to the account team — "RevOps leader moved to NewCo within last 3 months, fresh re-engagement target."

### Junior IC at target company — not_ideal

Inputs: `(first_name="Sam", last_name="Junior", company_name_clean="TargetCo", linkedin_url="<verified URL>")`.

Sequence: spine runs through to scoring. Persona=`sales`, seniority=`ic`.

`score_contact_fit`:
- persona ∈ target list (sales yes).
- seniority ladder index for `ic` (=0) < floor `director` (=3). Seniority does NOT meet floor.
- Verdict: `acceptable` (persona match alone, seniority below floor) — NOT `ideal`.

CRM action: not in primary outbound segment. Maybe in a "future-DM" nurture list when they get promoted.

## Provider preferences for contact-side

| Need | Default tool | Why | Override when |
|---|---|---|---|
| Find LinkedIn URL from name + company | `prospeo_enrich_person` (tier 1) | Single-call enrich; Prospeo's index is contact-side-first; collapses URL + email + firmographics in one credit | Sample bench shows Apollo `people_match` outperforms Prospeo on your specific TAM (rare on B2B SaaS) |
| Scrape full LinkedIn profile from URL | Harvest direct API (`api.harvest-api.com/linkedin/profile`) | LinkedIn-direct, low latency, single call | Bulk scrapes >10k rows where Apify HarvestAPI's batch actor amortizes startup latency better |
| Persona + seniority classification | Latitude (`classify_multi_dim_via_latitude`) | Trace observability + GEPA prompt optimization + single call covers both dimensions | Never — classification is always Latitude per house rule |
| Contact scoring | Deterministic JS (`score_contact_fit`) | Inputs are already-AI-resolved categoricals; no need for AI on aggregation | Your scoring doc requires narrative judgment over edge cases — build an AI-judged contact-scoring function |
| Email finding (when needed) | Harvest `find_email=true` flag (single-call) | Collapses with profile scrape | Customer needs deliverability long-tail — build `find_contact_email` waterfall (leadmagic → datagma → bettercontact) |
| Mobile finding (when needed) | (Layer-3 deferred) | Mobile waterfall is opt-in, not in default spine | If your outbound includes phone — build `find_contact_mobile` (Lusha → Datagma → Fullenrich) |

## Composing with the account spine

When your project covers BOTH accounts and contacts, run the account spine first, then the contact spine:

```
Account spine (per account):
  normalize_domain_and_name → verify_domain_alive → company_summary_from_website
  → linkedin_url_verified → extract_hq_address → classify_via_latitude

Contact spine (per contact, with company_summary from upstream account):
  find_contact_linkedin_url → enrich_contact_linkedin_profile → validate_contact_identity
  → detect_job_change → classify_multi_dim_via_latitude → score_contact_fit
```

The account spine produces `company_summary` which the contact spine consumes (improves `find_contact_linkedin_url`'s tier-2 web-research fallback AND Latitude persona/seniority context).

When a customer wants ONLY contact cleanup (no account work), pass a placeholder summary or skip the upstream account spine — the contact spine works without it but classification quality drops slightly.

## What this skill does NOT cover

- Net-new contact discovery (building a contact list from filters / criteria, not cleaning an existing list). Use `apollo_people_search` or `prospeo_search_person` directly at the recipe level — different problem class.
- Account-side enrichment — see the [`enrichment-functions-catalog`](../enrichment-functions-catalog/SKILL.md) skill.
- M&A detection / corporate-structure / company-division — see [`ma-and-corporate-structure-playbook`](../ma-and-corporate-structure-playbook/SKILL.md).
- The Latitude prompt template authoring for `multi_dim_classification/classify` — see the function's own `latitude-prompt-spec.md`.

## Related references

- **Functions:** `enrichment-functions/{find_contact_linkedin_url, enrich_contact_linkedin_profile, validate_contact_identity, detect_job_change, classify_multi_dim_via_latitude, score_contact_fit}/`
- **Recipes:** `enrichment-functions/recipes/{default_contact_cleanup, contact_job_change_loop}.yaml`
- **Schema:** [`docs/schemas/contact-scoring-model.md`](../../../docs/schemas/contact-scoring-model.md)
- **Catalog:** [`enrichment-functions-catalog`](../enrichment-functions-catalog/SKILL.md)
- **Sibling skill:** [`ma-and-corporate-structure-playbook`](../ma-and-corporate-structure-playbook/SKILL.md)
