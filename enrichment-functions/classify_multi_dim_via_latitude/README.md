# classify_multi_dim_via_latitude

Multi-dimensional classification through ONE Latitude call. Use when multiple categorical dimensions should be judged from the same input — contact persona AND seniority from one title, industry AND vertical from one company, department AND function from one role.

Sibling to `classify_via_latitude`, which handles single-dimension classifications.

## Why this exists

Persona and seniority are both functions of the same job title. Calling Latitude twice (once per dimension) duplicates the research step inside the prompt — same title, same company context, two API calls, two billed runs. One call with two output dimensions cuts cost ~50% on multi-dim properties and produces more coherent results (the model judges both dimensions from the same reasoning, so they don't drift).

## When to use

- Persona + seniority for contacts (the canonical first caller).
- Any case where two or more categorical dimensions are functions of the same input and judging them together is plausible.

## When NOT to use

- Single-dimension classification — use `classify_via_latitude`. This function adds ceremony (dimensions array, dimensions_result object) without value when there's only one dimension.
- Dimensions that need fundamentally different inputs (one needs the full company website, another needs only the title). Splitting into two `classify_via_latitude` calls is cleaner.
- High-stakes scoring where you want each dimension's Latitude trace separate (e.g. compliance reviews). The single shared `latitude_conversation_uuid` makes per-dimension QA harder.

## Latitude prompt prerequisite

Before this function is callable, the Latitude prompt at `multi_dim_classification/classify` (or your custom path) must exist and conform to the response contract. See `latitude-prompt-spec.md` in this directory for the full contract.

The prompt accepts these parameters:
- `dimensions` — JSON-stringified array of `{ name, label, categories_json }`. Each dimension's categories taxonomy is its own JSON-stringified array.
- `dimensions_count` — number, used by the prompt to validate it returns the expected count.
- Plus whatever entity-context parameters the caller passes (`job_title`, `company_summary`, etc.).

The prompt returns:
```json
{
  "summary": "<one-paragraph summary>",
  "dimensions_result": {
    "<dim_name>": { "category": "<internal-value>", "label": "<human-label>", "reasoning": "<2-3 sentences>" }
  },
  "reasoning": "<cross-cutting reasoning>"
}
```

## Inputs / outputs

See `function.yaml`. Key fields:

- `dimensions` — array. Each entry: `{ name, categories_json: [...] }`. Example:
  ```yaml
  dimensions:
    - name: persona
      categories_json: !load preset_categories/contact_department.yaml
    - name: seniority
      categories_json: !load preset_categories/contact_seniority.yaml
  ```
- `parameters` — object containing the entity context. Example for contact persona+seniority:
  ```yaml
  parameters:
    job_title: "VP of Revenue Operations"
    company_summary: "Series C B2B SaaS company..."
    profile_about: "Building the GTM tech stack..."
    headline: "VP RevOps at Acme | ex-Stripe"
  ```
- Output `dimensions_result` is keyed by dimension name:
  ```json
  {
    "persona": { "category": "revenue_operations", "label": "Revenue Operations", "reasoning": "..." },
    "seniority": { "category": "vp_or_head", "label": "VP / Head", "reasoning": "..." }
  }
  ```

## Single-uuid-per-call contract

ALL dimensions share one `latitude_conversation_uuid`. This is intentional — it's one Latitude call. Downstream QA loops that previously assumed "one uuid per classified property" must update:

- For multi-dim runs, fetch the trace once and key annotations by dimension name (e.g. `<uuid>::persona`, `<uuid>::seniority`).
- The QA directive (your QA loop) tracks the migration.

## Gotchas

- **Empty dimension responses.** If the Latitude prompt forgets to emit a dimension that was in the input, `dimensions_result.<missing_dim>` is `null` (not absent). Caller must handle null per dimension. The compose_output JS preserves the input dimension names so downstream consumers always know which slots to read.
- **Category constraint enforcement is the prompt's job.** This function does NOT validate that `dimensions_result.<dim>.category` is in the dimension's `categories_json`. If the prompt hallucinates a category not in the taxonomy, it goes through. Your caller (or QA loop) must verify.
- **Models with weak instruction-following can collapse dimensions.** Tested-good model: gpt-5 (Latitude default for multi-dim). gpt-4o-mini and below sometimes return `dimensions_result: { category: ..., label: ... }` (collapsed to a single dim) on prompts with 3+ dimensions. Configure the model at the prompt level in Latitude.
- **Order of dimensions in the input matters for prompt clarity, NOT correctness.** `dimensions_result` is keyed by name, not indexed by position. But put high-priority dimensions first in the input array — most LLMs give the first dimension more reasoning budget.
- **Don't pass dimensions with conflicting category values.** If `persona.categories_json` and `seniority.categories_json` both contain a category with `value: "vp"` (intentionally or by accident), the prompt's output may ambiguate which dimension the value belongs to. Use unambiguous internal values per dimension.

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/classify_multi_dim_via_latitude.workflow.json)"

deepline workflows call --workflow-id <ID> --payload '{
  "dimensions": [
    {"name": "persona", "categories_json": [
      {"value": "sales", "label": "Sales", "description": "AEs, SDRs, sales leadership"},
      {"value": "revenue_operations", "label": "Revenue Operations", "description": "RevOps, sales ops, GTM systems"},
      {"value": "marketing", "label": "Marketing", "description": "Demand gen, brand, content"}
    ]},
    {"name": "seniority", "categories_json": [
      {"value": "ic", "label": "IC"},
      {"value": "manager", "label": "Manager"},
      {"value": "director", "label": "Director"},
      {"value": "vp_or_head", "label": "VP / Head"},
      {"value": "c_level", "label": "C-Level"}
    ]}
  ],
  "parameters": {
    "job_title": "VP of Revenue Operations",
    "company_summary": "Series C B2B SaaS company building HR tech",
    "headline": "VP RevOps at Acme | ex-Stripe"
  },
  "latitude_api_key": "<KEY>",
  "latitude_project_id": "<PROJECT_ID>"
}'
# Expect:
#   dimensions_result.persona.category="revenue_operations"
#   dimensions_result.seniority.category="vp_or_head"
#   single latitude_conversation_uuid populated
```

## Related

- **Sibling:** `classify_via_latitude` — single-dim version. Use for any one-property classification.
- **Latitude prompt spec:** `latitude-prompt-spec.md` (in this directory).
- **QA-loop reference:** your QA loop.
- **Preset categories** (data layer): `preset_categories/contact_department.yaml`, `preset_categories/contact_seniority.yaml`, `preset_categories/company_type.json`, etc.
- **First caller:** the `default_contact_cleanup` recipe via `enrichment-functions/recipes/`.
