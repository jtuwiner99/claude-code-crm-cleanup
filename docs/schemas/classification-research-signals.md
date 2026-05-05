# Classification research-signals schema (v1)

When your classification rules can't be answered from the company summary alone — they need **specific signals** found by going to the user's website and looking for explicit evidence — use the research-signal classification path.

The your classification model lives at:

```
classification-models/<property_id>.json
```

One file per property that needs research-signal classification. Most properties don't — they continue using the existing single-prompt classifier (sheet-driven categories). Research-signals are an opt-in **upgrade for hard properties** (MSP detection, scientific-vs-business segmentation, anything where a single research-and-classify call gets it wrong too often).

## Why

MSP detection is the canonical case. Reps used to manually:

1. Visit the company's website.
2. Read the **services page**: looking for "Managed IT", "Managed Support", "Managed Services" keywords.
3. Note whether **cybersecurity** services are offered.
4. Note whether they sell **office/printer supplies**.
5. Apply rules: "managed services → MSP regardless of cybersecurity. cybersecurity-only → Cybersecurity. supplies-only → Distributor."

A single classification prompt asking "is this an MSP?" with web research baked in gets ~70% accurate. Multiple targeted research calls + a final rules-applying call gets you to ~95%. The pattern is: **fan out to find specific signals, then apply rules to the synthesized evidence**.

This is the same architectural pattern as `country_presence_verified` (cctld inference + office presence + entity legitimacy → compose).

## Schema

```json
{
  "schema_version": 1,
  "property_id": "account_type",
  "categories_source": "google_sheet",
  "research_signals": [
    {
      "name": "managed_services_offered",
      "look_for": "Does the company's services page or homepage explicitly mention 'Managed IT', 'Managed Support', 'Managed Services', or similar managed-IT-services keywords?",
      "evidence_format": "boolean + 1-2 quotes from services pages with URLs",
      "search_pages_hint": "/services, /managed-it, /it-services, homepage"
    },
    {
      "name": "cybersecurity_offered",
      "look_for": "Does the company offer cybersecurity services — penetration testing, security audits, MDR/EDR, SOC services, compliance audits?",
      "evidence_format": "boolean + 1-2 quotes",
      "search_pages_hint": "/services, /cybersecurity, /security"
    },
    {
      "name": "office_supplies_offered",
      "look_for": "Does the company sell printer supplies, toner, office supplies, copier rentals, or printing services?",
      "evidence_format": "boolean + 1-2 quotes",
      "search_pages_hint": "/products, /supplies, /printing"
    }
  ],
  "rules": "PRIORITIZE managed services as the strongest MSP signal. \n- If managed_services_offered=true → category=MSP, regardless of whether cybersecurity is also offered.\n- If managed_services_offered=false AND cybersecurity_offered=true → category=Cybersecurity.\n- If managed_services_offered=false AND cybersecurity_offered=false AND office_supplies_offered=true → category=Distributor.\n- Otherwise → category=Other (with a fallback prompt to the company_summary for any obvious mismatch).",
  "edge_cases": [
    "If a company has 'cybersecurity' in their tagline but their primary services list is managed IT, still classify as MSP — taglines don't override services-page evidence.",
    "MSPs often co-brand with vendors (Microsoft, Cisco, etc.). Vendor partnerships do not change the classification — only the services they offer.",
    "If the website is sparse (no services page, no detail), fall back to the company_summary and emit lower confidence."
  ],
  "notes_to_ai": "Bias toward MSP when managed services are offered, even partially. Cybersecurity-only is a real category but rare — most MSPs offer cybersecurity as one of many services. Don't downgrade an MSP because cybersecurity is also listed."
}
```

## Field-by-field

### `schema_version` (int, required)
Currently `1`.

### `property_id` (string, required)
The CRM property name this classification feeds. Matches the property_id in your taxonomy config. The plugin reads categories from the config for this property AND research signals + rules from this file.

### `categories_source` (string, required)
- `"google_sheet"` (default and currently only supported value) — categories live in your taxonomy config. The plugin pulls them via the existing classification machinery and merges with the research-signals from this file.
- (Future: `"inline"` would allow categories to live in this same JSON file. Out of scope for v1.)

### `research_signals` (array, required, len ≥ 1)
One entry per signal the AI should look for. Each:

- **`name`** (string) — snake_case identifier the rules reference (e.g. `managed_services_offered`).
- **`look_for`** (string) — free-form prose describing the signal. The research prompt uses this verbatim as the "what to look for" instruction. Be specific — list keywords, named services, page sections.
- **`evidence_format`** (string, optional) — what shape the AI should return evidence in (boolean only, boolean + quotes, boolean + URLs, etc.). Default: "boolean + 1-2 quotes from supporting pages with URLs".
- **`search_pages_hint`** (string, optional) — comma-separated common page paths to start with (e.g. `/services, /managed-it`). Helps the AI focus its research; not enforced.

### `rules` (string, required)
Free-form prose describing the classification rules using the signal names. The classification prompt receives the signal evidence + this rules text + the categories list, and applies the rules to pick a category.

Should be:
- **Explicit about prioritization** — when multiple signals fire, which wins?
- **Cover all category branches** — each category in the categories list should appear in the rules.
- **Use signal names verbatim** — `managed_services_offered` not "if they offer managed services" (so the final classifier prompt can pattern-match exactly).

### `edge_cases` (array of strings, optional)
Operator-authored prose for judgment-call edge cases. Same shape as scoring-model edge_cases. The classifier uses these as soft hints when the rigid rules don't cleanly apply.

### `notes_to_ai` (string, optional)
Free-form scoring philosophy / bias notes. Common: which way to default when uncertain.

## Cost shape

For each row:
- N research_signal calls (one per `research_signals[]` entry). ~$0.005 each.
- 1 final classification call. ~$0.005.

A 3-signal example: 4 calls per row, ~$0.020. Compare to existing single-prompt classify (~$0.005 with web research). 4x more expensive but materially more accurate on signal-heavy properties.

## When to use vs. existing single-prompt classifier

**Use the single-prompt classifier when:**
- The classification can be made from the company_summary alone.
- Most categories are clearly distinguishable by industry/size/description.
- Examples: SaaS vs. FinTech vs. Agency, B2B vs. B2C, public vs. private.

**Use research-signal classification when:**
- The classification requires evidence from specific website sections (services pages, products lists).
- Multiple signals combine via rules ("X and Y → A; X without Y → B").
- The single-prompt classify accuracy is below your bar (typically <85% on a golden dataset).
- Examples: MSP vs. Cybersecurity vs. Distributor; scientific-leadership-tier vs. business-tier; manufacturer vs. distributor vs. integrator.

## Operator workflow

1. Customer property `account_type` is failing classification on a ground-truth sample (>15% wrong on a 50-row sample).
2. Author `classification-models/account_type.json` (hand-author or use a converter skill).
3. Add to recipe:
   ```yaml
   classifications_with_research_signals:
     - property_id: account_type
       model_path: classification-models/account_type.json
   ```
4. Compile + run; inspect the `account_type` outputs and `research_signals_evidence` in each row's enriched output.
5. Iterate the JSON file — adjust signals or rules — based on failure patterns.

## Categories vs. signals

Important distinction — these live in different places:

- **Categories** (the candidate values: MSP, Cybersecurity, Distributor) — live in your taxonomy config, same as for the single-prompt classifier. Updated by you.
- **Research signals + rules** — live in this **JSON file**. Updated by the user as the iteration loop tightens accuracy.

This split matches the operational reality: customers care about the category list (it maps to their CRM property values); operators care about the signals + rules (the engineering knobs to make classification accurate).

## Future schema versions

- **`categories_source: "inline"`** — for customers without a Google Sheet, allow categories in the same JSON.
- **`signal_dependencies`** — when one signal's research can be skipped based on another signal's outcome (cost optimization).
- **`golden_dataset_path`** — pointer to the golden dataset for an iterate-classification-prompt skill to use.

## Pointers

- Function: [`enrichment-functions/research_signal_via_latitude/`](../../enrichment-functions/research_signal_via_latitude/)
- Composer function: [`enrichment-functions/classify_via_research_agents/`](../../enrichment-functions/classify_via_research_agents/)
- Recipe schema: [`customer-enrichment-recipe-composition.md`](customer-enrichment-recipe-composition.md) (`classifications_with_research_signals:` block)
- Existing single-prompt classifier (still the default): [`enrichment-functions/classify_via_latitude/`](../../enrichment-functions/classify_via_latitude/)
