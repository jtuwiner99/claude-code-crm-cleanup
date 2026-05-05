# Contact scoring-model JSON schema (v1)

The structured format the deterministic `score_contact_fit` function consumes as a parameter. One file per customer, typically at:

```
scoring-models/contact.json
```

Your contact-fit rules — typically extracted from their ICP doc, a kickoff conversation, or hand-authored — get encoded into this JSON shape. Unlike the account scoring model (which is prose-heavy and routed through an AI gateway), this is purely deterministic — no AI involved.

## Why this shape

Contact scoring inputs are already AI-resolved categoricals: persona (from a multi-dim classifier), seniority (same call), still_there (from a job-change detector). Aggregating them into a fit verdict is a deterministic lookup over the user's rules — no judgment required.

The schema mirrors the **field-by-field** discipline of [account-scoring-model-schema.md](account-scoring-model-schema.md) — versioned, typed, validated — but is intentionally simpler. Rich edge-case prose lives in an AI-driven contact-scoring function (an opt-in for customers who need it); this file is for the deterministic case that covers ~80% of engagements.

## Schema

```json
{
  "schema_version": 1,
  "object_type": "contact",

  "still_there_required": true,

  "target_personas": [
    "sales",
    "revenue_operations",
    "marketing",
    "executive"
  ],

  "seniority_floor": "director",
  "seniority_ladder": [
    "ic",
    "senior_ic",
    "manager",
    "director",
    "vp_or_head",
    "c_level",
    "founder"
  ]
}
```

## Field-by-field

### `schema_version` (int, required)

Currently `1`. Increment when this schema changes shape in a way that breaks backward compatibility.

### `object_type` (string, required)

Always `"contact"`. Validates that the file is a contact-scoring model (not account). The `score_contact_fit` function reads this field for the audit trail.

### `still_there_required` (bool, optional, default `true`)

When `true`, a contact whose `still_there` is `false` short-circuits to `not_ideal` regardless of other signals. When `false`, the function ignores `still_there` and scores on persona + seniority alone.

Set to `false` for engagements where you want to score a contact's intrinsic fit independent of whether they're still at the on-record company — e.g. when the recipe is identifying movers that should be re-targeted at their NEW company.

### `target_personas` (array of strings, required)

Your in-target persona/department values. Each entry MUST be an internal `value` from the active persona-taxonomy YAML. Entries that aren't in the active classifier's taxonomy are silently ignored (audit hook: `score_contact_fit.sub_scores.persona_check.target_personas` records the rule, classifier output goes in `.value`).

Typical defaults by customer type:

| Customer ICP | Typical target_personas |
|---|---|
| GTM / sales-led B2B SaaS | `["sales", "revenue_operations", "marketing", "executive"]` |
| Product-led B2B SaaS | `["product", "engineering", "executive"]` |
| Finance vertical | Customer overrides taxonomy entirely; uses domain-specific values like `["compliance", "investor_relations", "legal", "operations"]` |

### `seniority_floor` (string, required)

The minimum seniority value a contact must have to count as "in-target by seniority." Lower values disqualify on the seniority axis. The string MUST be a value present in `seniority_ladder`.

### `seniority_ladder` (array of strings, required)

Ordered list of seniority values, low-to-high. Index-based comparison drives the floor check. Customers who use coarser scales (`["ic", "manager", "leader"]`) or finer scales (separating VP and SVP) configure this freely — must match the user's seniority taxonomy.

The ladder must contain `seniority_floor`. Values not in the ladder are treated as below the floor (audit hook: `seniority_check.value` records the actual value for taxonomy-drift detection).

## Verdict logic

The `score_contact_fit` function applies these rules:

1. If `identity_match === 'mismatch'` is passed → `not_ideal` (short-circuit).
2. If `still_there_required` AND `still_there === false` → `not_ideal` (short-circuit).
3. Compute `persona_match` = `target_personas.includes(persona)`.
4. Compute `seniority_meets_floor` = `seniority_ladder.indexOf(seniority) >= seniority_ladder.indexOf(seniority_floor)`.
5. If `persona_match AND seniority_meets_floor` → `ideal`.
6. If `persona_match OR seniority_meets_floor` → `acceptable`.
7. Otherwise → `not_ideal`.

## Out-of-scope (use an AI-judged contact scorer if needed)

The deterministic schema deliberately doesn't model:

- **Weighted scoring** ("VP RevOps = 100, VP Sales = 80"). Binary in/out only.
- **Edge cases** ("CFO at <50-employee company doesn't count", "founder + technical role overrides"). These require AI judgment.
- **Multi-tier hierarchies** (Tier 1 / 2 / 3 / Bad Fit). The function emits 3-state categorical (`ideal | acceptable | not_ideal`); customers needing more granularity need a different function.
- **Vertical-specific personas** (e.g. compliance / investor relations / legal hierarchies). Override the persona taxonomy via a project-specific YAML and reference those values in `target_personas`.

When your scoring rules require any of the above, build an AI-judged contact-scoring function instead of stretching this schema.

## Validation

The `score_contact_fit` function validates required fields at runtime:

- Throws if `target_personas` is not an array.
- Throws if `seniority_ladder` is empty or not an array.
- Throws if `seniority_floor` is missing OR not present in `seniority_ladder`.

These are **recipe-author bugs** (config drift), not data bugs — fail loud. The function does not silently default; the user must fix the rules JSON.

## Related

- Function consumer: [`enrichment-functions/score_contact_fit/`](../../enrichment-functions/score_contact_fit/)
- Account-side analog: [account-scoring-model-schema.md](account-scoring-model-schema.md) (different shape — prose-heavy, AI-driven)
- Persona/department taxonomy: [`enrichment-functions/preset_categories/contact_department.yaml`](../../enrichment-functions/preset_categories/contact_department.yaml)
- Seniority taxonomy: [`enrichment-functions/preset_categories/contact_seniority.yaml`](../../enrichment-functions/preset_categories/contact_seniority.yaml)
