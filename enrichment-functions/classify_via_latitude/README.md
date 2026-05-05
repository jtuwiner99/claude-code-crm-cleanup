# classify_via_latitude

Generic classification function — any property, any taxonomy, single OR multi-select. Routes through Latitude so every classification call is observable, evaluable via GEPA, and tied into the existing QA loop.

## Why this is one function, not many

A naive design would have separate functions per classification type and per cardinality: `classify_company_type`, `classify_industry`, `classify_contact_seniority`, `tag_destination_activities_multi`, etc. That ignores the architectural fact that **the prompt is the wrapper, the categories are the data, and the cardinality is a per-property decision** — and they vary independently. your QA loop (Latitude prompt-iteration process) already encodes the prompt-vs-data split:

- The Latitude prompt at `<prompt_path>` is the wrapper. It does research, applies the matching rules, enforces output format. One prompt can serve any classification by accepting `{{categories_json}}` as a variable.
- The categories taxonomy lives in your taxonomy config, gets exported to JSON, and gets passed in at call time.
- The cardinality (one answer vs. many) is a property of the output schema, not the prompt or the data.

So the function abstraction is: *given (prompt_path, parameters, categories_json, output_mode), call Latitude and emit the classification.* Every classification type is just a different combination of those four inputs.

## Output modes

| Mode | When to use | Example | Output shape |
|---|---|---|---|
| `single` (default) | Property where one value applies — company_type (SaaS XOR E-commerce XOR ...), seniority (Director XOR VP XOR ...), industry-as-vertical when you want one primary | `category="SaaS"`, `category_label="SaaS"`, `categories=null` | string |
| `multi` | Property where multiple values can apply concurrently — destination activity tagging (snow_sports + hiking + dining all at one resort), buyer-persona signals (cost-conscious + technical-buyer at the same contact), industry-as-multi when a company genuinely sells across verticals | `categories=["snow_sports","hiking"]`, `category_labels=["Snow Sports","Hiking"]`, `category=null` | array |

The non-active mode's outputs are always null. Don't read them in the wrong mode — `function.yaml` invariants spell this out.

## Latitude prompt contracts

**Single mode** (existing — same contract the QA runner already enforces):

```json
{
  "summary": "what the entity does (2-3 sentences)",
  "category": "<EXACT internal value from categories_json>",
  "category_label": "<human label of same category>",
  "reasoning": "why this category fits (2-4 sentences)"
}
```

**Multi mode** (new):

```json
{
  "summary": "what the entity is (2-3 sentences)",
  "categories": ["<value_1>", "<value_2>", "..."],
  "category_labels": ["<Label 1>", "<Label 2>", "..."],
  "reasoning": "why these categories fit; one bullet per category preferred"
}
```

In both modes:

- **Internal values must come from `categories_json`'s `value` field**, never the human label. These strings are written back to HubSpot.
- `categories` and `category_labels` MUST be the same length and parallel-ordered.
- Empty array `[]` is a valid multi-mode result. Don't force the prompt to pick at least one.
- The Latitude prompt is responsible for category constraint enforcement — if the model hallucinates a value not in `categories_json`, the function passes it through; downstream callers should validate.

## When to use

After all the data the prompt needs to make the decision is collected:

- **Company classification** (company_type, industry, etc.): runs after `linkedin_url_verified` + `company_summary_from_website`. Prompt typically takes `{domain}`.
- **Contact classification** (department, seniority, persona): after the contact has a job title + company context. Prompt typically takes `{job_title, company_summary, employee_count}`.
- **Multi-select tagging** (destination activities, capability tags, etc.): after research has gathered enough signal. Prompt typically takes the research summary directly.

## When NOT to use

- The classification can be done deterministically from existing fields (e.g. department from a known job-title-to-department lookup table). Don't burn an AI call when a JS map will do.
- The categories list is small (≤3) and the boundaries are obvious. Latitude is overkill.
- You need the same classification on every row of a CSV import and the cost-per-row would dominate. Run it once on a unique-domain set, cache.
- **(multi mode)** The categories aren't really independent — if knowing one rules out another, that's a single-select with hierarchy, not a multi-select.

## Inputs / outputs

See `function.yaml`.

The contract leaves `categories_json` flexible to support any property. Default taxonomies live in `../preset_categories/` (e.g. `company_type.json`). Customer-level overrides live at `your-recipe-folder/preset_categories/<name>.json` and take precedence at compile time.

## Security model — Latitude API key

**Deepline currently has no runtime secret-store primitive.** The only `secret` field in the Deepline workflow schema is for incoming-webhook signature verification, not for API-key references in HTTP request payloads.

What this means in practice:

- The function takes `latitude_api_key` as a caller-supplied input (NOT a `{{secrets.<NAME>}}` reference, since that doesn't resolve to anything).
- The the compiler sources the key from `.env` (`LATITUDE_API_KEY`) and inlines its literal value into the compiled workflow JSON at compile time.
- That JSON gets stored in Deepline. **The stored workflow definition contains the live API key.** Anyone with read access to the workflow definition has the key.

Mitigations:

1. **Restrict workflow read access in Deepline** (org-level — same as you'd protect any secret).
2. **Rotate the Latitude API key periodically** and re-deploy.
3. **Consider per-project Latitude projects** when a project requires harder credential isolation; provision a per-project key and inject it via the client-level recipe override.

This limitation is shared with the existing production `account_enrichment` workflow (which has the same Bearer token inlined). It's not a regression introduced by this function — it's the current Deepline ceiling. Worth a feedback note to Deepline if/when it becomes a real risk; tracked in this README rather than escalated unilaterally.

## QA loop integration

Every call's `latitude_conversation_uuid` is captured on the function output. That's the trace key the QA Results interface uses to link production runs back to Latitude UI traces. To trace a specific failure:

1. Read `function_output.latitude_conversation_uuid`.
2. Open Latitude UI → traces → search by UUID.
3. Inspect token-level prompt + response.
4. Decide: definitions problem (fix in your taxonomy config) vs. prompt problem (fix in Latitude).

For details see your QA loop → Triaging failures.

## Multi-tenancy on the Latitude project

`latitude_project_id` defaults to the env var `LATITUDE_PROJECT_ID`. All classification prompts in this default config live in one shared project. Override per-project when:

- Your data must not co-mingle with other tenants. traces (compliance / NDA).
- You want your own GEPA optimization runs without affecting shared defaults.
- A customer maintains their own custom prompt versions.

Provisioning: create a new Latitude project, copy the relevant prompts in, get a project-scoped API key. Add to your `.env` and reference at the recipe level.

## Gotchas

- **`category` not in `categories_json` is a real failure mode** (model hallucinates a category). The function does NOT validate; downstream consumers should `if (!categories.find(c => c.value === out.category)) flag(...)`. Same applies to multi mode — validate every entry in `out.categories`. This is by design — validation is the caller's responsibility, not the transport's.
- **Empty array vs. null in multi mode.** `categories: []` means "the prompt ran and decided no categories matched" — a valid result. `categories: null` means "the call failed". Distinguish at the caller: `if (out.categories === null) handleFailure(); else if (out.categories.length === 0) handleNoMatches();`.
- **`live` is locked in Latitude v3.** Per memory `project_latitude_v3_api_capabilities`, you cannot push directly to `live` via API. Workflow: edit on a draft commit, validate via experiment, then publish — the function picks up the new prompt automatically because it pins to `live`.
- **Timeout = 60s** by default. Latitude prompts that do heavy research can run 20-40s. Don't lower below 30s.
- **Multi-mode prompts need explicit "you may select 0 or more" instruction**. Models default to picking at least one if not told otherwise. Empty-array results require it to be explicitly allowed in the prompt.

## Smoke test

Single mode (matches production):

```bash
deepline workflows apply --payload "$(cat tmp/classify_via_latitude.workflow.json)"
deepline workflows call --workflow-id <ID> --payload '{
  "prompt_path": "category_enrichment/enrichment_classify",
  "parameters": { "domain": "stripe.com" },
  "categories_json": '"$(cat ../preset_categories/company_type.json)"',
  "latitude_api_key": "<your-latitude-key>",
  "output_mode": "single"
}'
# Expect: category=SaaS, category_label=SaaS, summary populated, categories=null
```

Multi mode (synthetic — requires a corresponding Latitude prompt that returns the multi-select shape):

```bash
deepline workflows call --workflow-id <ID> --payload '{
  "prompt_path": "destination/activity_tagging",
  "parameters": { "destination_summary": "Park City, Utah — known for skiing, mountain biking, hiking trails, hot springs, summer arts festivals." },
  "categories_json": [{"value":"snow_sports","label":"Snow Sports","description":"...","positive_signals":[],"negative_signals":[]}, {"value":"hiking","label":"Hiking","description":"...","positive_signals":[],"negative_signals":[]}, {"value":"water_sports","label":"Water Sports","description":"...","positive_signals":[],"negative_signals":[]}],
  "latitude_api_key": "<your-latitude-key>",
  "output_mode": "multi"
}'
# Expect: categories=["snow_sports","hiking"], category_labels=["Snow Sports","Hiking"], category=null
```
