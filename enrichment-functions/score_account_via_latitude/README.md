# score_account_via_latitude

Apply your account-scoring model and emit a tier (1..N) with reasoning, sub-scores, and confidence. Routes through Latitude using a single agency-level prompt; your tier rules pass in as a parameter.

## Status: opt-in add-on (NOT default)

Spine-only — only injectable when `recipe.use_agency_spine: true` and you have a scoring model file at `your-recipe-folder/scoring-models/account.json`.

**Use this function when:**

- You have a documented scoring model (in a Google Doc, PDF, internal wiki, or call notes).
- You want CRM-routable tier values written back to HubSpot/Salesforce.
- Account prioritization is operator-meaningful — without scoring, every enriched account looks the same to downstream sales workflows.

**Skip this function when:**

- You don't have a scoring model and don't want one built (rare).
- The CRM already has tiers from a deterministic field (read directly from Salesforce/HubSpot). v1 doesn't support "passthrough from CRM field" — schema v2 will.

## Why this exists

Most B2B GTM workflows end up needing some form of account tiering. The pattern is consistent:

1. You have a scoring doc (or you author one on a discovery call).
2. The doc has tier definitions (1-4 typically), structured rules (geo, size, ICP sub-type), and edge cases (C-suite handling, hybrid roles, title noise).
3. The system needs to apply that scoring at the END of enrichment, after all the upstream signals are populated.

Before this function: scoring lived only in Clay (per-project Latitude classification step or hand-rolled JS column). Each project required a one-off rebuild. After: a single shared Latitude prompt + one structured JSON per project = scoring works the same way for every project, with all tuning at the prompt level.

## How it works

Three commands:

1. **`build_request`** — composes the Latitude POST body. Takes the row's `account_signals` (JSON-serialized enrichment outputs) and your `tier_rules_json` (your scoring model JSON, serialized) as parameters.
2. **`latitude_call`** — POSTs to `gateway.latitude.so/api/v3/projects/<id>/versions/<v>/documents/run` with path `account_scoring/score_tier`. Returns the AI's structured-output verdict.
3. **`compose_output`** — extracts `tier`, `tier_label`, `reasoning`, `sub_scores`, `confidence` from the response. On Latitude failure, defaults to mid-tier (e.g. Tier 3 in a 4-tier model) — operator's "default to OK / lower-priority" bias.

The agency Latitude prompt is at `account_scoring/score_tier`. Source: `latitude-prompt-spec.md` in this directory.

## Inputs / outputs

See `function.yaml` for the typed contract. Things worth highlighting:

1. **`account_signals` is operator-controlled.** Plugin assembles it from upstream outputs (domain, name, country, employee_count, sub_type classification, summary, LinkedIn payload). Add fields when your scoring rules need them (e.g. revenue, founded_year). Plugin shouldn't include EVERYTHING the row has — keep the AI focused on signals the rules actually reference.

2. **`tier_rules_json` is the source of truth.** Customer-specific. Lives in your local recipe folder at `scoring-models/account.json`. Schema documented in this repo's wiki.

3. **`latitude_api_key` is baked into the compiled playbook.** Same security model as `classify_via_latitude`. Rotate keys → re-compile + wipe affected runs. See `classify_via_latitude/README.md` for the implications.

4. **Default-to-mid-tier on failure.** When Latitude fails or returns unparseable output, the function emits `tier = max(1, tier_count - 1)` (e.g. 3 in a 4-tier model). NEVER defaults to Tier 1 (false high-priority) or top tier (false disqualify). Operator's documented bias.

## Pipeline placement

```
... default spine (normalize → verify → summary → linkedin → hq) ...
       ↓
classify_via_latitude (sub-type classification — feeds account_signals)
       ↓
country_presence / m_and_a / corporate_structure / company_division (enrichment plugins)
       ↓
score_account_via_latitude  ← here (opt-in, spine-only)
       ↓
deep enrichment commands (gated downstream of score_account_via_latitude when recipe is strict-mode)
```

The plugin adapter (`the account-scoring plugin`) takes care of injection ordering. Scoring runs AFTER classification + enrichment plugins so the AI sees all signals.

## Smoke test

Worked examples below assume a hypothetical biotech-targeting B2B SaaS scoring model: Tier 1 = core geo + Biotech sub-type + 25+ researchers; Tier 4 = non-core geo disqualifier; Consultants force Tier 3 regardless of size.

```bash
deepline workflows apply --payload "$(cat tmp/score_account_via_latitude.workflow.json)"

# Tier 1 case — core geo + Biotech sub-type + 25+ researchers
deepline workflows call --workflow-id <ID> --payload '{
  "account_signals": "{\"domain\":\"biotechco.com\",\"company_name\":\"BiotechCo\",\"company_summary\":\"BiotechCo is a US Biotech with 80 researchers focused on CRISPR therapeutics.\",\"country\":\"US\",\"employee_count\":120,\"industry\":\"Biotechnology\",\"sub_type_classification\":\"Biotech\"}",
  "tier_rules_json": "<your scoring model JSON>",
  "latitude_api_key": "<key>"
}'
# Expect: tier=1, tier_label="Highest priority", reasoning cites
#   "core geo + Biotech + 25+ researchers", confidence>=80

# Tier 4 case (non-core geo)
deepline workflows call --workflow-id <ID> --payload '{
  "account_signals": "{\"domain\":\"randomco.cn\",\"company_name\":\"RandomCo\",\"country\":\"CN\",\"employee_count\":50,\"sub_type_classification\":\"Biotech\"}",
  "tier_rules_json": "<your scoring model JSON>",
  "latitude_api_key": "<key>"
}'
# Expect: tier=4, tier_label="Disqualified", reasoning cites
#   "non_core_geo_disqualifier override fired"

# Forced Tier 3 (Consultants — core geo + large size, but sub-type forces tier_3)
deepline workflows call --workflow-id <ID> --payload '{
  "account_signals": "{\"domain\":\"strategyfirm.com\",\"company_name\":\"Strategy Firm\",\"country\":\"US\",\"employee_count\":200,\"sub_type_classification\":\"Consultants\"}",
  "tier_rules_json": "<your scoring model JSON>",
  "latitude_api_key": "<key>"
}'
# Expect: tier=3, reasoning cites "Consultants forced to Tier 3 regardless of geo / size"
```

## Gotchas

- **Sub-type classification must match your vocabulary.** Your `axes.icp_sub_types.tier_1_eligible` (e.g. `["Biotech", "CRO", "CDMO"]`) should match the values your upstream `classify_via_latitude` emits. If your classification taxonomy is `["SaaS", "FinTech", "E-Commerce"]`, a biotech-flavored scoring model won't match anything. Ensure alignment at recipe-composition time.
- **Tier reasoning quality varies with prompt + signals.** When `account_signals` is sparse (null employee_count, generic summary), the AI's reasoning gets vaguer. Improve upstream enrichment quality before assuming the scoring prompt is the problem.
- **Latitude prompts version separately from this function.** Pin to a specific draft commit when debugging by setting `latitude_version` in the recipe. Default `live` always tracks the latest published version.
- **The function does NOT do its own classification.** Sub-type classification (Biotech vs Consultants vs SaaS) is `classify_via_latitude`'s job, upstream. If your scoring needs sub-type but classification isn't enabled, the AI falls back to inferring from `company_summary` — less accurate.

## Pointers

- Prompt source-of-truth: `latitude-prompt-spec.md` in this directory
- Worked example scoring-model JSON: `scoring-models/account.example.json` in this repo (when added)
