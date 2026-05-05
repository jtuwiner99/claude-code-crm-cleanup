# Account scoring-model JSON schema (v1)

The structured format a scoring prompt consumes as a parameter. One file per customer, typically at:

```
scoring-models/account.json
```

Your tier rules — typically in your scoring doc — get converted into this JSON shape via the `convert-scoring-doc-to-model` skill (or hand-authored when the rules are simple).

The scoring prompt receives this JSON serialized as a string in the `tier_rules_json` parameter (analog to `categories_json` for classification).

## Why this shape

Hybrid: rigid fields for the deterministic parts (geo lists, size thresholds, ICP sub-type mappings — things the AI shouldn't have to "interpret") and free-form prose for the fuzzy parts (edge cases, judgment guidance, dual-function role handling). The AI applies the rigid fields literally and uses the prose to handle ambiguity.

Versioned via `schema_version` so future shape changes don't silently break existing customers' models.

## Schema

```json
{
  "schema_version": 1,
  "object_type": "account",
  "tier_count": 4,

  "tiers": [
    {
      "tier": 1,
      "label": "Highest priority",
      "rules_text": "Plain-language description of when this tier applies. Free-form prose lifted from the user's scoring doc."
    }
    // ... one entry per tier, ordered by tier ascending (1 = best)
  ],

  "axes": {
    "geo": {
      "core": ["US", "CA", "GB", "..."],
      "secondary": ["BR", "JP", "IN", "..."]
      // anything not in core or secondary is treated as non_core by default
    },
    "size": {
      "primary_metric": "researcher_count",
      "fallback_metric": "employee_count",
      "thresholds": { "large": 25, "medium": 11 }
      // implicit: anything below `medium` is "small"
    },
    "icp_sub_types": {
      "tier_1_eligible": ["Biotech", "CRO", "CDMO", "Medical Device"],
      "force_tier_3": ["Consultants", "Agencies"]
      // optional: "force_tier_4": [...] for hard disqualifiers
    }
  },

  "overrides": [
    {
      "id": "non_core_geo_disqualifier",
      "if": "geo == non_core",
      "then": { "tier": 4 }
    },
    {
      "id": "secondary_geo_downgrade",
      "if": "geo == secondary",
      "then": { "tier_adjust": -1, "floor": 3 }
    }
  ],

  "edge_cases": [
    "C-suite titles (COO/CFO/CEO/CBO) should not be downgraded to Tier 3 by 'Other' bucket — minimum Tier 2",
    "Hybrid R&D + leadership roles (VP R&D, Head of Research Ops) should elevate, not split"
  ],

  "notes_to_ai": "Bias toward Tier 3 (default) unless evidence is strong. Tier 4 means auto-disqualified."
}
```

## Field-by-field

### `schema_version` (int, required)
Currently `1`. Increment when this schema changes shape in a way that breaks backward compatibility.

### `object_type` (string, required)
`"account"` for account scoring. Future: `"contact"` for lead-tier scoring (separate file at `scoring-models/lead.json`). Reserved so the same schema shape can host both.

### `tier_count` (int, required)
Number of tiers in the model. Typically 3 or 4. Should equal `len(tiers)`.

### `tiers` (array, required)
One entry per tier, ordered from best (`tier: 1`) to worst.

- **`tier`** (int) — the numeric tier value the AI emits. Sequential 1..N.
- **`label`** (string) — short human-readable name (e.g. "Highest priority", "Disqualified"). Surfaces in the AI's response and in CRM writeback.
- **`rules_text`** (string) — free-form prose describing when this tier applies. **Lifted directly from the user's scoring doc.** The AI uses this for the soft / judgment-call parts of the decision.

### `axes` (object, optional)
Structured fields for the deterministic parts of the scoring rules. The AI is instructed to apply these literally (no interpretation). Three sub-axes today; extensible.

#### `axes.geo` (object, optional)
- **`core`** — array of country codes (ISO alpha-2 by convention) that count as the user's core geos. Tier-1 eligibility usually requires core.
- **`secondary`** — array of country codes for secondary geos (often produces a tier downgrade).
- Anything not listed in either array is implicit non_core (typically forces Tier 4).

#### `axes.size` (object, optional)
- **`primary_metric`** — preferred size metric. Common values: `"researcher_count"` (Biotech/Pharma), `"employee_count"` (default), `"engineering_headcount"` (DevTools), `"revenue"` (when CRM has it).
- **`fallback_metric`** — used when primary is null/missing. Usually `"employee_count"`.
- **`thresholds`** — named thresholds the rules reference. Common shape: `{"large": N, "medium": M}` where `large >= N` and `medium >= M < large`.

#### `axes.icp_sub_types` (object, optional)
- **`tier_1_eligible`** — sub-type values that qualify for the top tier(s).
- **`force_tier_3`** — sub-type values that explicitly downgrade to Tier 3 regardless of other axes (e.g. consultants, agencies).
- **`force_tier_4`** (optional) — hard-disqualifying sub-types.

The sub-type values must match the output of an upstream classification step (when you have a sub-type classification in your taxonomy config). When no upstream classification exists, the AI infers sub-type from the company summary directly.

### `overrides` (array, optional)
Override rules applied AFTER the base tier is determined. Each override:

- **`id`** (string) — unique identifier so the AI's reasoning can cite which override fired.
- **`if`** (string) — natural-language condition describing when the override applies. The AI evaluates this as a JS-like expression but doesn't execute it; treat as guidance.
- **`then.tier`** (int, optional) — set the tier to this value, regardless of base.
- **`then.tier_adjust`** (int, optional) — adjust the base tier by this delta (positive = downgrade since lower tier = better).
- **`then.floor`** (int, optional) — when adjusting, don't let the result go below this tier.

Common patterns:

| Override type | Example |
|---|---|
| Hard disqualifier | `if: "geo == non_core"` → `then: {tier: 4}` |
| Soft downgrade | `if: "geo == secondary"` → `then: {tier_adjust: -1, floor: 3}` |
| Sub-type downgrade | `if: "sub_type in force_tier_3"` → `then: {tier: 3}` |

### `edge_cases` (array of strings, optional)
Free-form prose covering judgment-call edge cases the user wants the AI to handle. Examples:

- "C-suite titles should not be downgraded to Tier 3 by 'Other' bucket — minimum Tier 2"
- "Translational Scientist / Research Fellow / PI variants should be treated as scientific tier, not Other"
- "Hybrid R&D + leadership roles (VP R&D, Head of Research Ops) should elevate, not split"

These are hints to the AI, not deterministic rules. Your edge cases evolve over time as they discover new failure modes — preserve them verbatim as your team discovers them.

### `notes_to_ai` (string, optional)
Operator-authored guidance about scoring philosophy. Common content:

- Bias direction ("default to Tier 3 unless evidence is strong" vs "default to Tier 1 unless explicitly disqualifying")
- What Tier 4 means operationally ("auto-disqualified, not routed")
- Optional tie-breakers between tiers

## Worked example — Biotech-tooling SaaS

A representative scoring model for a customer selling tooling to biotech research teams:

```json
{
  "schema_version": 1,
  "object_type": "account",
  "tier_count": 4,
  "tiers": [
    {
      "tier": 1,
      "label": "Highest priority",
      "rules_text": "Core geo + 25+ researchers + ICP sub-type (Biotech, CRO, CDMO, Medical Device)"
    },
    {
      "tier": 2,
      "label": "Strong",
      "rules_text": "Core geo + <25 researchers OR Secondary geo + 11+ researchers"
    },
    {
      "tier": 3,
      "label": "Lower priority",
      "rules_text": "Anything in between; consultants and agencies forced here regardless of geo / size"
    },
    {
      "tier": 4,
      "label": "Disqualified",
      "rules_text": "Non-core geo OR Spam OR explicitly non-target"
    }
  ],
  "axes": {
    "geo": {
      "core": ["US", "CA", "GB", "DE", "FR", "AU", "NL", "CH", "SE", "IE"],
      "secondary": ["BR", "JP", "IN", "SG", "MX", "ES", "IT", "BE", "DK", "FI"]
    },
    "size": {
      "primary_metric": "researcher_count",
      "fallback_metric": "employee_count",
      "thresholds": { "large": 25, "medium": 11 }
    },
    "icp_sub_types": {
      "tier_1_eligible": ["Biotech", "CRO", "CDMO", "Medical Device"],
      "force_tier_3": ["Consultants", "Agencies"]
    }
  },
  "overrides": [
    {
      "id": "non_core_geo_disqualifier",
      "if": "geo == non_core",
      "then": { "tier": 4 }
    },
    {
      "id": "secondary_geo_downgrade",
      "if": "geo == secondary",
      "then": { "tier_adjust": -1, "floor": 3 }
    },
    {
      "id": "sub_type_force_tier_3",
      "if": "sub_type in axes.icp_sub_types.force_tier_3",
      "then": { "tier": 3 }
    }
  ],
  "edge_cases": [
    "C-suite titles (COO/CFO/CEO/CBO) should not be downgraded to Tier 3 by 'Other' bucket — minimum Tier 2",
    "Hybrid R&D + leadership roles (VP R&D, Head of Research Ops) should elevate, not split",
    "Title variants (Translational Scientist, Research Fellow, Principal Investigator, Lab Head) should be treated as scientific leadership tier, not Other",
    "Title noise / formatting issues (parentheses, separators, suffixes like 'Sr. Scientist (Contract)') should be normalized before bucketing",
    "Missing or generic titles ('Employee', 'Consultant') should NOT default to Tier 3 silently — flag with low confidence so operators can route separately"
  ],
  "notes_to_ai": "Bias toward Tier 3 (default) unless evidence is strong. Tier 4 means auto-disqualified — only apply when geo, spam, or explicit non-target signals are clear. Account-tier scoring should be independent of object type (lead vs contact); never let geo override title-driven persona quality."
}
```

## Operator workflow

1. Customer hands over a scoring doc (Google Doc, PDF, or notes).
2. Run the `convert-scoring-doc-to-model` skill against the doc URL → emits `scoring-models/account.json`.
3. Operator reviews the JSON, edits where the converter got rules wrong, commits.
4. Add `scoring: {enabled: true, ...}` to `enrichment-recipe.yaml`.
5. Compile + run; inspect tier distribution in the enriched output.

## Validation rules

The converter and the scoring plugin both validate:

- `schema_version` must equal 1 (today).
- `object_type` must be `"account"` for the account scoring plugin.
- `tier_count` must equal `len(tiers)` and be ≥ 2.
- Each `tier` value in `tiers` must be unique and form `1..tier_count` exactly.
- `axes.geo.core` and `axes.geo.secondary` (when present) must be arrays of strings; ISO alpha-2 strongly recommended but not enforced.
- `axes.size.thresholds.large` ≥ `axes.size.thresholds.medium` (when both present).
- Each `override.id` must be unique.

When validation fails, surface the errors and let the user hand-fix before saving. The scoring plugin refuses to compile a recipe whose scoring model fails validation (rather than silently producing wrong tiers).

## Future schema versions

Anticipated extensions (NOT in v1):

- **External tier source** (`tier_source: "salesforce_field"` + path) — for customers where the CRM is the source of truth and the AI just reads the field.
- **Multi-track scoring** — when one customer has multiple account types (e.g. industry AND academic) that score differently. Likely a `tracks: [...]` array with a discriminator field telling the AI which track to apply.
- **Confidence thresholds** — minimum confidence required to emit a non-default tier (handles "uncertain — default to OK").
