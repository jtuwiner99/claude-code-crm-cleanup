# Enrichment Functions

Reusable, parameterized enrichment building blocks. Inspired by Clay's Functions feature: write the logic once, call it from any pipeline, maintain it in one place.

## Why this exists

Before Functions, every CRM-cleanup engagement re-implemented the same primitives — domain normalization, LinkedIn URL discovery + verification, LinkedIn-to-firmographics extraction. When one of those broke or got better, every client recipe had to be patched independently. Functions invert that: the canonical version lives here in this repo, every client recipe `uses:` it, and updates flow through.

## Folder shape

```
enrichment-functions/
├── README.md                            ← this file
├── <function_name>/
│   ├── function.yaml                    ← typed I/O contract + metadata
│   ├── commands.jsonc                   ← Deepline commands with {{input.*}} placeholders
│   └── README.md                        ← what it does, when to use, gotchas
```

Each function's `function.yaml` declares:

- **`inputs`** — typed, with `required: true|false`. `{{input.<name>}}` placeholders inside `commands.jsonc` are filled by the caller at compile time.
- **`outputs`** — typed contract. The caller binds these to its own aliases.
- **`providers`** — Deepline tools the function uses (so we can audit credit burn).
- **`ai_calls`** — model tier + estimated tokens per call (so we can audit AI spend).
- **`estimated_cost_usd`** — per-invocation rough cost.

## Resolution order

When the compiler resolves a function reference (e.g. `uses: linkedin_url_verified@1`), it looks for an override in this order:

1. **Client-level override** — `your-recipe-folder/enrichment-functions/<name>/`
2. **Default** — `enrichment-functions/<name>/` ← this directory

Client overrides should be the smallest possible delta — typically a tweaked waterfall order, a swapped provider, or a different AI prompt. If a client's needs diverge enough to be a different function entirely, name it differently and don't override.

## Versioning

Functions are versioned in `function.yaml`. Major version bumps are breaking changes to the I/O contract; minor bumps are internal logic changes that preserve the contract. Callers pin to a major version (`uses: linkedin_url_verified@1`).

## Adding a new function

1. Create the folder + three files.
2. Define the contract in `function.yaml` first — what does the caller need to pass in, what does it get back?
3. Implement `commands.jsonc` against that contract.
4. Smoke-test as a standalone hosted Deepline workflow (`deepline workflows apply` + `workflows call` on a known-good input).
5. Document in `README.md`: what the function does, when to use it, when *not* to, known gotchas.

## Default account-enrichment recipe

These functions run on every standard account-enrichment recipe. Each has a clear role; the chain is the spine that every enrichment project starts from.

| Order | Name | Status | Purpose |
|---|---|---|---|
| 1 | `normalize_domain_and_name` | ported_from_clay | Clean a raw domain + (optionally) discover/clean the company name. |
| 2 | `verify_domain_alive` | ported_from_clay | Two-layer liveness check — free HTTP ping + cheap AI parking-page detector. Gate that drops dead/parked domains before they burn enrichment credits downstream. Default-to-keep on AI uncertainty. |
| 3 | `company_summary_from_website` | ported_from_clay | Visit the website and produce a dense multi-paragraph summary (used as grounding for downstream AI). |
| 4 | `linkedin_url_verified` | ported_from_clay | Find a company's LinkedIn URL from its domain and confirm it actually belongs to that company. Two-tier (cheap provider + AI fuzzy match → AI web-research fallback). Also emits firmographics from the verifying tier (size band, industry, name, description). |
| 5 | `extract_hq_address` | ported_from_clay | Extract HQ street/city/state/postal/country with operator-controlled CRM-format toggles (MD vs Maryland; US vs United States). LinkedIn-payload primary, AI-website-scrape fallback. Always-on default — every customer wants HQ address. |
| 6 | `classify_via_latitude` | ported_from_production | Generic classification function — any property, any taxonomy, single OR multi-select. Routes through Latitude for QA observability + GEPA prompt optimization. Categories are data (your taxonomy config); the prompt is the wrapper; the cardinality is `output_mode`. One function classifies company_type, industry, contact department, seniority, multi-select tagging (e.g. destination activities), etc. Run once per classification taxonomy. |

## Default contact-cleanup recipe

The contact-side spine. Shipped 2026-05-04. Composes the same way the account spine does — one URL discovery, one provider scrape, one identity gate, one job-change check, one classification call (multi-dim), one scoring step. Reference recipe at `recipes/default_contact_cleanup.yaml`; recurring subset at `recipes/contact_job_change_loop.yaml`.

| Order | Name | Status | Purpose |
|---|---|---|---|
| 1 | `find_contact_linkedin_url` | ported_from_clay | Resolve a contact's LinkedIn URL from name + company. Two-tier: Prospeo `enrich_person` (agency contact-side default, set 2026-05-04) → deeplineagent web research. Skipped at recipe level when row already has `linkedin_url`. |
| 2 | `enrich_contact_linkedin_profile` | ported_from_clay | Single Harvest direct API call (`api.harvest-api.com/linkedin/profile`). Returns full profile JSON + hoisted convenience fields (`current_role`, `name`, `location`). Optional flags: `find_email`, `include_about_profile`, `main_only`. |
| 3 | `validate_contact_identity` | ported_from_clay | Confirm scraped profile = right person. Deterministic name + company match (Levenshtein + nickname dictionary + experience-history search) + AI tiebreaker (gpt-5-mini) only when signals split. Emits `confirmed | weak | mismatch`. |
| 4 | `detect_job_change` | ported_from_clay | Pure deterministic JS — compare scraped current employer vs on-record. Emits `still_there | moved | unclear` plus new_company_* fields and `started_role_within_3_months` (direct port of Ontra's recency formula). |
| 5 | `classify_multi_dim_via_latitude` | net-new | Sibling to `classify_via_latitude` — one Latitude call classifies multiple dimensions (e.g. persona + seniority from one title). One `latitude_conversation_uuid` covers all dimensions. Prompt at `multi_dim_classification/classify`. |
| 6 | `score_contact_fit` | net-new | Pure deterministic JS — aggregate `still_there + persona + seniority` into `ideal | acceptable | not_ideal` using your `your-recipe-folder/scoring-models/contact.json` (schema in `wiki/contact-scoring-model-schema.md`). |

Distinct from the account-side scoring function (`score_account_via_latitude`) which IS Latitude-based — account scoring judges prose-heavy scoring docs (geo overrides, ICP sub-types, edge cases). Contact scoring aggregates already-AI-resolved categoricals, where deterministic logic is auditable, cheaper, and faster. If your contact-scoring rules require narrative judgment, build `score_contact_via_latitude` (deferred opt-in) instead of stretching the deterministic schema.

## Opt-in add-ons

These functions are NOT in the default recipe. They run only when the project requirements identify a need for them. Each has its own decision criteria documented in its README's "Status: opt-in add-on" section.

| Name | Status | When to use | Cost per row |
|---|---|---|---|
| `country_presence_verified` | ported_from_clay (opt-in) | Your market mix has heavy country-level domains (.co.uk, .de, etc.) AND/OR sales is territory-assigned AND/OR known false-positive problem with marketing-only country domains. Typical for EMEA-heavy engagements. | ~$0.012 (3 AI calls) |
| `detect_acquisition` | ported_from_clay (opt-in) | Your TAM is in an M&A-heavy vertical (PE-backed targeting, strategic-buyer-driven categories, mature SaaS consolidation), OR scoping flagged duplicate parent/child records as a CRM-quality problem, OR ABM motion where parent-record duplicates break routing. Pair with `acquired_brand_status` to get the full M&A picture. See `skills/ma-and-corporate-structure-playbook` for the operational playbook. | ~$0.005 baseline + ~$0.003 on acquired rows (2 AI calls when acquired, 1 when not) |
| `acquired_brand_status` | ported_from_clay (opt-in) | Pair with `detect_acquisition` when you need to differentiate independently-operated acquired brands (e.g. Slack under Salesforce — keep + tag as child) from fully absorbed ones (e.g. Clearbit under HubSpot — dedupe / route to parent). Reuses upstream `verify_domain_alive` for liveness — does NOT call any paid third-party HTTP service. | ~$0.004 when AI judgment runs; $0 when deterministic short-circuits fire (redirect-to-parent or domain inactive) |
| `detect_corporate_structure` | shipped (opt-in, spine-only) | Your TAM features durable parent-child relationships across DIFFERENT legal entities, independent of any M&A event — restaurant brand portfolios (Outback / Bloomin'), family-owned restaurant groups, franchises with corporate parents, conglomerate portfolios. Distinct from `detect_acquisition` (event-based) and from `detect_company_division` (same-entity branches). Emits `relationship_type` (independent/parent/subsidiary), parent_name, parent_domain, known_subsidiaries. Strict-mode gate drops subsidiaries before classification (operator routes to parent records). | ~$0.005 (1 AI call) |
| `detect_company_division` | shipped (opt-in, spine-only) | Your TAM features regional or BU branches of the SAME legal company — H&M UK / H&M Australia / H&M Global, Under Armour regional arms, Microsoft Gaming / Cloud / Office BUs. Distinct from `detect_corporate_structure` (which covers different legal entities). Composes with `country_presence_verified` (validates regional records have real in-country staff). Emits `is_division`, `division_type` (regional/business_unit), `global_parent_name`, `division_scope`. Strict-mode gate drops divisional records (operator routes to global parent). | ~$0.004 (1 AI call) |

## Planned future extensions

| Name | Status | Why it's not built yet |
|---|---|---|
| `company_core_from_linkedin` | planned | Builds when you need richer Harvest-based firmographics (integer employee count, HQ address, founded year, specialties) beyond PDL's size band. Today `extract_hq_address` covers HQ; full Harvest payload is a future plug-in. |
| `country_employee_count` | planned | Builds when one of Apify HarvestAPI / Crustdata / PDL gains a by-country headcount tool. Clay's MixRank `get-counts-by-country-for-profiles-with-mixrank` has no Deepline equivalent today. Once available, `country_presence_verified` gets sharper scoring by consuming it as an input. |
| `extract_all_locations` | planned | Builds when you need the full list of company offices, not just HQ. Today `extract_hq_address` returns one location only. |
| `find_contact_email` | planned | Layer-3 contact-side opt-in. Multi-provider waterfall (leadmagic → datagma → bettercontact) for SMTP-verified email finding. Today `enrich_contact_linkedin_profile.find_email=true` covers single-provider Harvest email finding; the dedicated waterfall ships when you need long-tail coverage. |
| `find_contact_mobile` | planned | Layer-3 contact-side opt-in. Mobile waterfall (Lusha → Datagma → Fullenrich). Builds when your outbound motion includes phone outreach. |
| `score_contact_via_latitude` | planned | Future opt-in — Latitude-based contact scoring for customers whose scoring rules require narrative judgment over edge cases (e.g. complex C-suite-level overrides). Today `score_contact_fit` (deterministic) covers the typical case. |

## Preset categories

`preset_categories/` holds default classification taxonomies (company type, industry, contact department, seniority). They serve as bootstrap material when starting a new project — copied into your taxonomy config as version 1, then iterated. See `preset_categories/README.md` for the resolution order (project-level taxonomy override > project-root preset override > default).

## Agency default cheap-AI model

As of **2026-05-01**, the default cheap-AI model for enrichment functions is **`openai/gpt-5-mini`**. This applies to the gpt-4o-mini-class slots — name normalization, parking-page detection, LinkedIn fuzzy-match verification, etc. — wherever a function needs an inexpensive structured-output call. Higher-stakes calls (e.g. classification through Latitude) are governed by the Latitude prompt's model selection, not this default.

Why gpt-5-mini: it is the current floor in the deeplineagent catalog that supersedes 4o-mini for our class of structured cheap calls. Earlier ports used 4o-mini because that was the floor when the original Clay tables were built. The bump applies repo-wide; per-function overrides live on each function's `model` input parameter where exposed.

This default is expected to be validated against golden datasets (Latitude experiments) before being treated as final. If one of the cheap classes turns out to underperform 4o-mini on a specific task, override that function's model rather than the agency default.

## Provenance and porting

These functions are ported from production Clay tables (exported 2026-05-01). Each function's `function.yaml` includes a `clay_origin:` section noting the source and intentional deviations from a verbatim port. Provider substitutions (notably MixRank → PDL) are documented in the affected function's README under "Provider substitution".

The M&A pair (`detect_acquisition` + `acquired_brand_status`) come from a separate Clay workbook focused on parent-child + acquisition workflows. Two intentional deviations from the Clay source:

- **ApiVoid (paid third-party HTTP status checker) DROPPED.** `acquired_brand_status` reuses upstream `verify_domain_alive`'s `final_url` and `is_live` outputs — the default spine already paid for those signals, so re-probing here would be wasteful. Documented in `acquired_brand_status/function.yaml::clay_origin.port_notes`.
- **AI calls collapsed.** `detect_acquisition` folds Clay's chained Company-Domain Match + M&A Detection + M&A Analysis + DBA Analysis into one structured-output deeplineagent call (saves three rounds of context-shedding). `acquired_brand_status` folds Clay's Status Research + Status Decision into one structured-output call.
