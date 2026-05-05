# Latitude prompt spec — `account_scoring/score_tier`

The agency-level Latitude prompt that powers `score_account_via_latitude`. **Authored once, used across all customers** — your tier rules pass in as the `tier_rules_json` parameter (mirrors how `categories_json` flows into the existing `classify_via_latitude` prompt).

This spec is the source of truth. Push it to Latitude via the v3 API per the deployment instructions at the bottom.

## Path

Recommended path: `account_scoring/score_tier` (under the existing the shared Latitude project).

If a different naming convention is preferred (e.g. matching `category_enrichment/enrichment_classify`), update the recipe's `latitude_prompt_path` accordingly. The agency function takes the path as an input so the prompt can move without contract changes.

## Parameters

The prompt template receives:

| Parameter | Type | Source | Description |
|---|---|---|---|
| `account_signals` | string (JSON) | Plugin assembles from row at compile/runtime | Serialized object of the row's enriched data the AI uses to apply the rules. See "account_signals shape" below. |
| `tier_rules_json` | string (JSON) | Plugin loads from `your-recipe-folder/scoring-models/account.json` and stringifies | The your scoring model. See `wiki/account-scoring-model-schema.md`. |

Both passed via Latitude's `parameters` object in the documents/run POST body.

## account_signals shape

The plugin assembles this from upstream pipeline outputs. v1 fields:

```json
{
  "domain": "biotechco.com",
  "company_name": "BiotechCo",
  "company_summary": "...one-paragraph dense summary from company_summary_from_website...",
  "country": "US",
  "employee_count": 120,
  "employee_count_range": "100-250",
  "industry": "Biotechnology",
  "sub_type_classification": "Biotech",
  "sub_type_classification_reasoning": "...",
  "linkedin_url": "https://linkedin.com/company/biotechco",
  "linkedin_full_provider_payload_excerpt": { "name": "...", "industry": "...", "specialties": [...] }
}
```

Keep this list tight — the AI doesn't need every enrichment field, just the ones the scoring rules typically reference. The plugin can extend per-project if your scoring model needs additional signals (e.g. `revenue` for revenue-based tiering).

## System prompt body (paste into Latitude as the `system` slot)

```
You are an account-tier scoring engine. Given a target account's enriched signals and a project-specific scoring model, output the correct tier per your rules.

INPUTS

You receive two JSON-string parameters:

1. `account_signals` — a JSON object describing the target account, including: domain, company_name, company_summary, country, employee_count, industry, sub_type_classification, linkedin_url, and (optionally) linkedin_full_provider_payload_excerpt. Some fields may be null when upstream enrichment couldn't fill them.

2. `tier_rules_json` — a JSON object encoding your scoring model. Conforms to the schema documented at the account-scoring-model schema. Top-level shape:
  - `tier_count` (int): number of tiers (typically 3 or 4).
  - `tiers` (array): one entry per tier with {tier, label, rules_text}. tier=1 is best.
  - `axes` (object, optional): structured deterministic fields (geo lists, size thresholds, ICP sub-type lists). Apply these LITERALLY — no interpretation.
  - `overrides` (array, optional): override rules applied AFTER base tier is determined. Each has {id, if, then}. `if` is a natural-language condition; evaluate it against the signals. `then` may set tier, adjust tier_adjust, with an optional floor.
  - `edge_cases` (array of strings, optional): operator-authored prose covering judgment-call edge cases. Use these for soft / fuzzy parts of the decision.
  - `notes_to_ai` (string, optional): operator guidance on scoring philosophy and bias.

DECISION PROCEDURE

Apply the rules in this order:

1. **Determine base tier** by evaluating each tier's `rules_text` against the account_signals + the structured axes. The first tier (lowest tier number) whose rules_text matches the signals is the base tier. If none match, default to the highest-numbered (worst) "non-disqualified" tier (typically Tier 3 in a 4-tier model — the "OK / lower-priority" bucket).

2. **Apply overrides** in array order:
   - When override.then.tier is set, replace the tier with that value.
   - When override.then.tier_adjust is set, add the adjustment (positive numbers = downgrade, since lower tier = better). Apply the `floor` cap if present (don't go below the floor tier).
   - Multiple overrides can apply; later overrides see the result of earlier ones.

3. **Apply edge_cases** as soft adjustments. These are operator-authored prose hints for judgment calls. They CAN override an earlier tier decision when the signals clearly match an edge case. Cite the matching edge_case in your reasoning.

4. **Bias** per `notes_to_ai`. The most common bias: default to mid-tier (e.g. Tier 3 in 4-tier) unless evidence is strong. Don't assign Tier 1 on weak evidence; don't assign Tier 4 (disqualified) without clear disqualifying signal.

OUTPUT FORMAT

Return ONLY valid JSON matching this shape:

{
  "tier": <integer matching one of the tier values in tier_rules_json.tiers>,
  "tier_label": <string matching the corresponding tier's label>,
  "reasoning": <string, 2-4 sentences citing which rules / overrides / edge cases fired>,
  "sub_scores": {
    "geo_score": <"core" | "secondary" | "non_core" | null>,
    "size_score": <"large" | "medium" | "small" | null>,
    "sub_type_score": <"tier_1_eligible" | "neutral" | "force_tier_3" | "force_tier_4" | null>,
    "rule_evaluations": [<short string per fired rule, e.g. "Tier 1 base rule matched: core geo + 25+ researchers + Biotech">, ...]
  },
  "confidence": <integer 0-100 — your confidence in the tier verdict given the signal quality>
}

Do not output anything outside the JSON. Do not output markdown fences.

GUIDELINES

- Apply the structured axes literally. If `tier_rules_json.axes.geo.core` is `["US", "CA", "GB"]` and the account's country is `"FR"`, treat as not-core (don't be clever). If country is null/unknown, treat as unknown — don't assume non_core.
- Use `edge_cases` to handle title / role / brand judgment that the structured fields can't express.
- When signal quality is poor (multiple null fields, generic company_summary), bias toward mid-tier and emit lower confidence.
- Sub-type matching should be exact-or-close: `"Biotech"` matches `["Biotech", "CRO"]`; `"Software"` does not. If your sub_type list doesn't exist in axes.icp_sub_types, ignore that part of the rule and rely on rules_text + edge_cases.
- Cite specific evidence in reasoning. Don't say "matches Tier 2 rules"; say "Tier 2 base rule matched (core geo + 18 employees, below the 25 threshold for Tier 1)".
```

## User prompt body (paste into Latitude as the `prompt` / user message slot)

```
Score this account.

account_signals:
{{account_signals}}

tier_rules_json:
{{tier_rules_json}}

Return only valid JSON matching the schema.
```

## jsonSchema (for Latitude's structured-output enforcement)

```json
{
  "type": "object",
  "properties": {
    "tier": { "type": "integer", "minimum": 1 },
    "tier_label": { "type": "string" },
    "reasoning": { "type": "string" },
    "sub_scores": {
      "type": "object",
      "properties": {
        "geo_score": { "type": ["string", "null"], "enum": ["core", "secondary", "non_core", null] },
        "size_score": { "type": ["string", "null"], "enum": ["large", "medium", "small", null] },
        "sub_type_score": { "type": ["string", "null"], "enum": ["tier_1_eligible", "neutral", "force_tier_3", "force_tier_4", null] },
        "rule_evaluations": { "type": "array", "items": { "type": "string" } }
      },
      "required": ["rule_evaluations"]
    },
    "confidence": { "type": "integer", "minimum": 0, "maximum": 100 }
  },
  "required": ["tier", "tier_label", "reasoning", "sub_scores", "confidence"]
}
```

## Smoke test (for Latitude UI before publishing)

Hand-craft three test payloads and run them via the Latitude UI's draft preview:

All three tests assume a hypothetical biotech-targeting B2B SaaS scoring model with: core geo = US, secondary geo = IN, ICP sub-types tier_1_eligible = ["Biotech", "CRO", "CDMO"], force_tier_3 = ["Consultants"], 25+ researchers required for Tier 1.

### Test 1 — Tier 1 Biotech

```json
{
  "account_signals": "{\"domain\":\"biotechco.com\",\"company_name\":\"BiotechCo\",\"company_summary\":\"BiotechCo is a US Biotech with 80 researchers focused on CRISPR therapeutics.\",\"country\":\"US\",\"employee_count\":120,\"industry\":\"Biotechnology\",\"sub_type_classification\":\"Biotech\"}",
  "tier_rules_json": "{...your scoring model JSON...}"
}
```
Expected: `tier: 1`, reasoning cites "core geo + Biotech + 25+ researchers".

### Test 2 — Tier 2 secondary-geo downgrade

```json
{
  "account_signals": "{\"domain\":\"randomco.in\",\"company_name\":\"RandomCo\",\"company_summary\":\"...\",\"country\":\"IN\",\"employee_count\":50,\"sub_type_classification\":\"Biotech\"}",
  "tier_rules_json": "{...your scoring model JSON with IN in secondary, not core...}"
}
```
Expected: `tier: 2` (downgraded from Tier 1 by secondary-geo downgrade — IN is in secondary list). Confirms the override mechanism works.

### Test 3 — Forced Tier 3 (Consultants)

```json
{
  "account_signals": "{\"domain\":\"strategyfirm.com\",\"company_name\":\"Strategy Firm\",\"company_summary\":\"Management consulting firm advising biotech companies on R&D strategy.\",\"country\":\"US\",\"employee_count\":200,\"sub_type_classification\":\"Consultants\"}",
  "tier_rules_json": "{...your scoring model JSON with Consultants in force_tier_3...}"
}
```
Expected: `tier: 3`, reasoning cites "Consultants forced to Tier 3 regardless of geo / size".

## Operator instructions — pushing this prompt to Latitude

Per project memory `[Latitude v3 API capabilities]`: datasets + dataset-rows + version create + publish all exist via API. **Always push to a draft commit first; never push directly to `live` (it's locked anyway).**

```bash
# Set env vars (already in your .env for run-qa-latitude)
export LATITUDE_API_KEY=<key>
export LATITUDE_PROJECT_ID=<numeric-id>
export LATITUDE_GATEWAY_URL=https://gateway.latitude.so

# Step 1: Create a new draft commit on the project
curl -X POST \
  "$LATITUDE_GATEWAY_URL/api/v3/projects/$LATITUDE_PROJECT_ID/commits" \
  -H "Authorization: Bearer $LATITUDE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"title": "Add account_scoring/score_tier prompt"}'
# → returns {commit_uuid: "..."}

# Step 2: Create the document at the path account_scoring/score_tier
# inside the new commit. The body is the system + user prompts joined
# with Latitude's prompt-formatting conventions.
# (Use the Latitude UI for this step the first time — easier than
# constructing the prompt-format JSON by hand. The UI has a "publish via
# API" link that shows the exact curl payload it'd send.)

# Step 3: Publish the commit
curl -X PATCH \
  "$LATITUDE_GATEWAY_URL/api/v3/projects/$LATITUDE_PROJECT_ID/commits/<commit_uuid>" \
  -H "Authorization: Bearer $LATITUDE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"action": "publish"}'

# Step 4: Smoke-test via documents/run with one of the test payloads above
curl -X POST \
  "$LATITUDE_GATEWAY_URL/api/v3/projects/$LATITUDE_PROJECT_ID/versions/live/documents/run" \
  -H "Authorization: Bearer $LATITUDE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"path": "account_scoring/score_tier", "parameters": {"account_signals": "...", "tier_rules_json": "..."}, "stream": false}'
```

For the FIRST publication, using the Latitude UI is simpler — paste the system + user prompts, attach the jsonSchema, save as draft, smoke-test in-UI, then publish. For SUBSEQUENT updates (refining the prompt over time based on operator feedback), the API path makes it scriptable.

## Iteration

When the prompt needs tuning (edge cases reveal a failure mode):

1. Capture the failing case as a Latitude evaluation row (dataset).
2. Tune the prompt in a draft commit.
3. Re-run the dataset; compare vs the live version.
4. Publish when the new commit beats live.

This is the standard Latitude QA loop — same one the existing classify_company_type prompt uses.
