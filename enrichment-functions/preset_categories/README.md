# Preset Categories

Default classification taxonomies. Used as starting templates when scaffolding a new project taxonomy; consumed at runtime by `classify_via_latitude` when the caller doesn't supply project-specific categories.

## What lives here

| File | Object | Purpose | Status |
|---|---|---|---|
| `company_type.json` | company | Horizontal — what KIND of company. SaaS / E-Commerce / Digital Agency / Traditional Business / Internet Business / Other. | populated (extracted from production) |
| `company_industry.yaml` | company | Vertical — what INDUSTRY (healthcare, legal, manufacturing, etc.). | scaffold |
| `contact_department.yaml` | contact | Which department the contact belongs to (Marketing, Sales, Engineering, RevOps, etc.). | scaffold |
| `contact_seniority.yaml` | contact | Seniority band (IC, Manager, Director, VP, C-Level, Founder, etc.). | scaffold |

## Schema (per category)

Each category in a preset follows the same shape your taxonomy config produces. See the classification-schema rules for the rule-writing style guide.

```json
{
  "value": "saas",
  "label": "SaaS",
  "description": "A company that sells software via subscription...",
  "positive_signals": [
    "Subscription or seat-based pricing",
    "Self-serve sign-up or free trial for software",
    "..."
  ],
  "negative_signals": [
    "Core business is human services delivery",
    "Physical goods sold via storefront",
    "..."
  ]
}
```

A preset file is an array of these objects.

## Resolution at runtime

When a recipe calls `classify_via_latitude` with a categories source rather than inlined `categories_json`, the compiler resolves in this order:

1. **Project-level taxonomy override** (highest priority — your version-controlled source of truth)
2. **Client-level preset override** at `your-recipe-folder/preset_categories/<name>.json` (rare — used as a starting point before your taxonomy config is populated)
3. **Agency default** at this directory (lowest priority — used during onboarding, demos, or when a brand-new customer hasn't yet decided on their taxonomy)

In practice (1) is the path almost every production run uses. (2) and (3) are bootstrap material.

## Bootstrap flow

When onboarding a new customer:

1. The default preset for each in-scope classification gets copied into your taxonomy config as version 1.
2. You review the rows against your actual product/ICP and edit descriptions + signals to match.
3. A future iteration loop can regenerate rows from your kickoff context — the bundled defaults become the v1 baseline you improve on.
4. Customer iterates further via the Latitude QA loop (your QA loop).

The bundled defaults are NOT meant to be perfect for any specific use case — they.re meant to be a sensible starting point that minimizes blank-page paralysis.

## Adding a new preset

1. Identify the classification type (company-level horizontal, company-level vertical, contact-level department, etc.).
2. Decide on 4-8 mutually exclusive, collectively exhaustive (MECE) categories. Always include an `Other` catch-all.
3. Write each category per the rule-writing style guide. Verify nearest-neighbor distinguishability (no two categories' positive signals overlap >80%).
4. Add to the table above.
5. Reference the new preset in any default recipe that should classify on this property.

## Why JSON for `company_type` and YAML for the others

`company_type.json` was extracted verbatim from the production workflow's payload. The Latitude prompt currently consumes `categories_json` as a JSON string, so JSON is the closer-to-runtime format. The other presets are scaffolds that humans will edit; YAML is friendlier for that. The compiler converts to JSON before sending to Latitude either way.
