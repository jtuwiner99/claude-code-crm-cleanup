# Latitude prompt spec — `multi_dim_classification/classify`

This document specifies the Latitude prompt that `classify_multi_dim_via_latitude` calls. The prompt must exist in your Latitude project at this path before the function is usable. Authoring lives in Latitude UI; this file is the contract the function expects.

## Path

`multi_dim_classification/classify` (default; overridable via the function's `prompt_path` input).

## Purpose

Classify an entity (contact, company, etc.) along N categorical dimensions in one call. The prompt receives the entity's context plus an array of dimensions, each with its own categories taxonomy. The prompt returns one categorical assignment per dimension.

## Input parameters (Latitude variables)

The function passes these to the prompt automatically:

| Parameter | Type | Description |
|---|---|---|
| `dimensions` | JSON string | Array of `{name, label, categories_json}` where `categories_json` is itself a JSON-stringified array. The prompt MUST parse the outer array AND each inner `categories_json`. |
| `dimensions_count` | number | Count of dimensions. Use as a sanity check — your `dimensions_result` MUST contain exactly this many keys. |

Plus whatever entity-context parameters the caller passes. For contact persona+seniority, the canonical set is:

| Parameter | Type | Description |
|---|---|---|
| `job_title` | string | Contact's current title (LinkedIn or CRM-clean). |
| `company_summary` | string | Dense summary of the contact's current company. |
| `profile_about` | string | LinkedIn "About" section (when available). |
| `headline` | string | LinkedIn headline ("VP Marketing at Acme \| ex-Stripe"). |

For other multi-dim use cases (industry+vertical, department+function), define your own context parameter set.

## Required output schema

The prompt MUST emit exactly this shape:

```json
{
  "summary": "<one-paragraph summary of the entity, used as common context for all dimensions>",
  "dimensions_result": {
    "<dim_name_1>": {
      "category": "<exact value from dim_1's categories_json>",
      "label": "<human-readable label matching the value>",
      "reasoning": "<2-3 sentences citing positive/negative signals from dim_1's categories_json>"
    },
    "<dim_name_2>": {
      "category": "...",
      "label": "...",
      "reasoning": "..."
    }
  },
  "reasoning": "<optional cross-cutting reasoning that informed multiple dimensions; can be empty string>"
}
```

### Rules

1. **`dimensions_result` MUST have exactly `dimensions_count` keys** with names matching the input `dimensions[].name`.
2. **`category` MUST be the EXACT internal `value` field** from the matching dimension's `categories_json`. Casing matters. If you can't find a match, use the dimension's `default_value` (read it from the categories_json — it's typically encoded as a meta field or by convention named `unclear` / `other`).
3. **Reasoning per dimension MUST cite signals.** Reference the `positive_signals` / `negative_signals` fields from the dimension's categories_json when explaining the verdict. This is the QA-loop hook for prompt iteration.
4. **No null categories.** Always pick something — if uncertain, pick the dimension's default value (e.g. `unclear` for seniority, `other` for persona).

## Suggested prompt skeleton

```markdown
---
provider: openai
model: gpt-5
temperature: 0
---

You are a precise multi-dimensional classifier. Given an entity description and {{dimensions_count}} categorical dimensions, return one classification per dimension.

ENTITY:
- Title: {{job_title}}
- Company summary: {{company_summary}}
- Profile about: {{profile_about}}
- Headline: {{headline}}

DIMENSIONS TO CLASSIFY:
{{dimensions}}

Each dimension's categories_json is a JSON array of category objects with `value`, `label`, `description`, `positive_signals`, `negative_signals`.

For EACH dimension:
1. Read all categories.
2. Pick the ONE category whose positive_signals best match the entity AND whose negative_signals don't apply.
3. If no category clearly fits, pick the dimension's default value (typically `unclear` or `other`).
4. Emit reasoning citing 1-2 specific signals from positive_signals or negative_signals.

OUTPUT (return ONLY this JSON, no markdown):

{
  "summary": "<entity summary>",
  "dimensions_result": {
    "<dim_name>": {
      "category": "<exact internal value>",
      "label": "<human label>",
      "reasoning": "<signal-grounded justification>"
    }
  },
  "reasoning": "<optional cross-cutting>"
}
```

## Authoring + iteration

Use Latitude's GEPA loop on a representative sample of (entity, expected_dimensions_result) pairs. The prompt iterates against one judge rubric: for each dimension, "did the model pick the right category given the inputs?"

When iterating, push changes to a draft commit first (the function's `latitude_version` input accepts a draft commit ID). Validate against your eval set. Publish to `live` only after validation.

## Why one prompt vs. multiple

A single multi-dim prompt:

- Costs ~50% less per row than two separate `classify_via_latitude` calls (one research pass, two classifications).
- Produces more coherent results — the model judges both dimensions from the same reasoning, reducing the "drifted" cases where persona and seniority disagree (e.g. classifying as `vp_or_head` for seniority but `ic` for persona because the title was ambiguous in different ways).
- Has one trace per row (one `latitude_conversation_uuid`), simplifying QA when the dimensions are conceptually linked.

The cost of this consolidation: when one dimension is well-known and the other isn't, the prompt's reasoning may bias toward the easier dimension. Mitigation — when adding a 3rd or 4th dimension, monitor per-dimension accuracy on the eval set and split the prompt if any dimension drops materially.

## Failure modes

- **Latitude prompt model picks a category not in `categories_json`.** The function does not validate constraints — caller (or QA loop) must. Mitigation: high-precision prompts use `temperature: 0` and explicit "MUST be the EXACT value from categories_json" instruction.
- **Model collapses dimensions** (returns `{ category, label }` at the top level instead of nested under `dimensions_result`). Symptom: function emits `dimensions_result: null`. Mitigation: stronger model (gpt-5+) and explicit schema instruction.
- **Model omits a dimension** (returns `dimensions_result` with only some keys). Function emits null for the missing dimension's slot. Caller decides whether to retry (re-run the function) or treat as `unclear`.
- **Latitude API returns 429 / 5xx.** The function emits null outputs and `raw_response.error` is populated. Recipe-level retries are your choice.

## Related

- Function consumer: `enrichment-functions/classify_multi_dim_via_latitude/`
- Sibling single-dim prompt: `category_enrichment/enrichment_classify` (used by `classify_via_latitude`)
- QA directive: your QA loop
- Preset categories: `enrichment-functions/preset_categories/`
