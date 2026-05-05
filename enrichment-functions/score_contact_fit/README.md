# score_contact_fit

Aggregate already-classified contact signals (still_there + persona + seniority) into a fit verdict (`ideal | acceptable | not_ideal`) using a customer-supplied scoring rules JSON. Pure deterministic JS — no AI, no provider calls.

## Why this exists

The typical contact-fit definition is "in target persona AND at or above seniority threshold AND still at the company." That's pure aggregation over categoricals. Burning a Latitude call to compute a Boolean lookup wastes credits and obscures audit trails (every row's verdict is now an AI trace instead of a JS rule). This function is the deterministic alternative.

## Why not always use Latitude (account-side parity)

`score_account_via_latitude` (account-side) IS Latitude-based, for one specific reason: customer account-scoring docs are prose-heavy. Geo overrides, ICP sub-type rules, with ~10 named edge cases (geo overrides, sub-type forcing, C-suite handling) — judging that requires AI. Contact scoring inputs are already AI-resolved categoricals (persona, seniority both come from `classify_multi_dim_via_latitude`); there's no prose left to judge.

The agency principle: AI for classification (the messy step), deterministic for aggregation (the clean step that runs over already-classified outputs). This function is the aggregation step.

If your scoring doc DOES require narrative contact judgment (rare — usually only when complex C-suite edge cases need to override the basic rules), use a future `score_contact_via_latitude` opt-in. The naming distinction (`_fit` deterministic vs `_via_latitude` AI) makes your expectation clear.

## When to use

- Any contact-cleanup recipe that needs to gate downstream CRM writes / segmentation / outbound on contact fit.
- Default placement in the recipe: AFTER `classify_multi_dim_via_latitude` and `detect_job_change`, BEFORE any CRM writeback or segmentation step.

## When NOT to use

- The your scoring rules require prose judgment (edge cases, narrative overrides). Build a `score_contact_via_latitude` instead.
- You haven't classified persona + seniority yet. This function is aggregation; classification is the prerequisite.
- You want a numeric tier (1-4) instead of a categorical (`ideal | acceptable | not_ideal`). The output is intentionally categorical to match how the typical outbound segmentation pattern works; numeric tiers would be a different function.

## Scoring rules (`tier_rules_json`)

Loaded from `your-recipe-folder/scoring-models/contact.json` (parallel to the existing `account.json` for `score_account_via_latitude`). Schema v1:

```json
{
  "schema_version": 1,
  "object_type": "contact",
  "still_there_required": true,
  "target_personas": ["sales", "revenue_operations", "marketing", "executive"],
  "seniority_floor": "director",
  "seniority_ladder": ["ic", "senior_ic", "manager", "director", "vp_or_head", "c_level", "founder"]
}
```

Field semantics:

| Field | Required | Meaning |
|---|---|---|
| `schema_version` | yes | Always `1` for this schema. Future schema changes bump this. |
| `object_type` | yes | Always `"contact"`. Validates that the file is a contact-scoring model, not account. |
| `still_there_required` | no (default true) | When true, contacts whose `still_there: false` short-circuit to `not_ideal`. When false, the function ignores `still_there` and scores on persona+seniority alone. |
| `target_personas` | yes | Array of internal persona/department values. Contact's persona must be in this list to count as "in-target." |
| `seniority_floor` | yes | Internal seniority value. Contact's seniority ladder index must be >= the floor's ladder index. |
| `seniority_ladder` | yes | Ordered array, low-to-high. Index-based comparison drives the floor check. |

The ladder is customer-configurable because some customers use coarser scales (IC / Manager / Leader) and others use finer ones (separate VP and SVP). Match your `preset_categories/contact_seniority.yaml` — same `value` strings, same order, low-to-high.

## Verdict ladder

| Verdict | Conditions | Example |
|---|---|---|
| `ideal` | persona ∈ target_personas AND seniority >= floor AND (still_there OR !required) | VP RevOps still at the on-record company → ideal |
| `acceptable` | persona ∈ target_personas OR seniority >= floor (XOR with ideal) | Director of Engineering at the company (right seniority, wrong persona) → acceptable |
| `not_ideal` | identity mismatch OR !still_there OR neither persona nor seniority criteria met | Junior IC engineer at a target company (wrong both ways) → not_ideal |

Short-circuit rules:

- `identity_match === 'mismatch'` (when passed) → `not_ideal`, persona / seniority NOT evaluated.
- `still_there_required && !still_there` → `not_ideal`, persona / seniority NOT evaluated.

Both short-circuits emit a clear `score_reasoning` so downstream operators can audit why a row is `not_ideal` without re-running the function.

## Inputs / outputs

See `function.yaml`. The function's contract REQUIRES `still_there`, `persona`, `seniority`, and `tier_rules_json`. `identity_match` is optional but recommended — when passed, mismatch short-circuits scoring (guard against scoring the wrong person).

## Why no `score_contact_via_latitude` shipped today

YAGNI principle. The deterministic case covers the typical case; the AI case requires a specific scoring doc to design against. Ship `score_contact_fit` first, build `score_contact_via_latitude` when your doc demands it. The naming distinction (`_fit` vs `_via_latitude`) reserves the namespace.

## Gotchas

- **`tier_rules_json` is JSON-stringified.** The plugin loading the file MUST `JSON.stringify(rules)` before passing in. The function does the parse internally. Don't pass an object — Deepline's templating engine flattens objects in inputs and the JSON.parse will fail.
- **Seniority value not in ladder.** When `i.seniority` isn't in `seniority_ladder` (e.g. classifier emitted `"unclear"` and the ladder doesn't include it), `seniority_check.meets_floor=false`. The contact gets scored on persona alone (acceptable if persona matches, otherwise not_ideal). Recipe authors who want unclear-seniority to default-pass should add `"unclear"` to `target_personas` (no — that doesn't make sense), or extend the ladder, or handle the edge case at the recipe level via `run_if_js`.
- **Persona value not in target_personas.** Just emits `personaCheck.matched=false`. No error. Persona taxonomy drift between the scoring rules and the live classifier is the recipe author's problem to detect — `verification_signals` records the actual values for audit.
- **`still_there_required: false` + non-deterministic identity.** When `still_there_required` is off and you skip `validate_contact_identity` upstream, the function can score a confidently-classified profile that belongs to the wrong person. ALWAYS gate on `validate_contact_identity` before scoring (or pass `identity_match` to this function) when stakes are high.
- **No "weighted" scoring.** v1 schema is binary: in target or not, meets floor or not. If a customer needs weighted (e.g. "VP RevOps = 100, VP Sales = 80"), v1 doesn't model it. Either extend the schema (v2) or build `score_contact_via_latitude` and let AI handle the nuance.

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/score_contact_fit.workflow.json)"

# Ideal:
deepline workflows call --workflow-id <ID> --payload '{
  "still_there": true,
  "persona": "revenue_operations",
  "seniority": "vp_or_head",
  "tier_rules_json": "{\"schema_version\":1,\"object_type\":\"contact\",\"still_there_required\":true,\"target_personas\":[\"sales\",\"revenue_operations\",\"marketing\"],\"seniority_floor\":\"director\",\"seniority_ladder\":[\"ic\",\"manager\",\"director\",\"vp_or_head\",\"c_level\"]}"
}'
# Expect: score="ideal", score_reasoning cites persona match + seniority floor.

# Acceptable (right seniority, wrong persona):
deepline workflows call --workflow-id <ID> --payload '{
  "still_there": true,
  "persona": "engineering",
  "seniority": "vp_or_head",
  "tier_rules_json": "<same as above>"
}'
# Expect: score="acceptable".

# Not ideal (moved companies):
deepline workflows call --workflow-id <ID> --payload '{
  "still_there": false,
  "persona": "revenue_operations",
  "seniority": "vp_or_head",
  "tier_rules_json": "<same as above>"
}'
# Expect: score="not_ideal", score_reasoning cites still_there gate.

# Not ideal (identity mismatch short-circuit):
deepline workflows call --workflow-id <ID> --payload '{
  "still_there": true,
  "persona": "revenue_operations",
  "seniority": "vp_or_head",
  "identity_match": "mismatch",
  "tier_rules_json": "<same as above>"
}'
# Expect: score="not_ideal", score_reasoning cites identity mismatch.
```

## Related

- **Upstream:** `detect_job_change` (provides `still_there`), `classify_multi_dim_via_latitude` (provides `persona` + `seniority`), `validate_contact_identity` (optional `identity_match`).
- **Sibling (account-side, AI):** `score_account_via_latitude` — different mechanism (Latitude over prose), same input/output naming convention so operators recognize the pattern.
- **Future:** `score_contact_via_latitude` opt-in — for customers whose scoring doc demands narrative judgment.
- **Per-project config:** `your-recipe-folder/scoring-models/contact.json`.
- **Schema:** `wiki/contact-scoring-model-schema.md` (to be authored alongside this function).
