# classify_via_research_agents

Composer for signal-heavy classifications. Lives **alongside** the existing `classify_via_latitude` — recipes pick per-property which path to use.

## Status: opt-in add-on (NOT default)

Spine-only. Per-property opt-in via the recipe's `classifications_with_research_signals: []` block.

**Use this function when:**

- Single-prompt classification (`classify_via_latitude`) accuracy on the property is below ~85% on a golden dataset.
- The classification requires evidence from specific website sections (services pages, products lists) that aren't reliably in the company_summary.
- Multiple signals combine via rules (the ConnectWise pattern: managed_services + cybersecurity + office_supplies → MSP / Cybersecurity / Distributor).

**Stick with `classify_via_latitude` (existing) when:**

- The classification is clearly inferable from the company_summary alone.
- One Latitude+Perplexity call hits your accuracy target.
- Cost matters more than the last 5-10% of accuracy.

## Why this exists

ConnectWise's MSP detection is the canonical case. A single classification prompt asking "is this an MSP?" with Perplexity research baked in gets ~70% right. Multiple targeted research calls (one per signal) feeding a final rules-applying call gets ~95%. The accuracy gain comes from FOCUS: each research call has one job and uses its full Perplexity budget on it; the final classifier doesn't re-research, it applies rules to synthesized evidence.

Same architectural pattern as `country_presence_verified` (multiple AI sub-tiers + compose).

## Pipeline (N signals → 1 classification)

```
parse_signals (JS — read research_signals[] from your model)
       ↓
research_signal × N (Latitude + Perplexity, one per signal, parallel)
       ↓
assemble_evidence (JS — collect signal results into evidence JSON)
       ↓
final_classify (Latitude — apply rules to synthesized evidence; NO Perplexity)
       ↓
compose_output (JS — emit category + reasoning + per-signal audit trail)
```

The number of research_signal calls equals the number of signals in your `classification-models/<property>.json` file. Each call is independent and parallelizable. The final classifier uses a DIFFERENT Latitude prompt (`account_classification/classify_with_signals`) — agency-level, no Perplexity, just rules-applying synthesis.

## Categories vs. signals — they live in different places

- **Categories** (the candidate values like MSP, Cybersecurity, Distributor) — live in your taxonomy config, same as `classify_via_latitude`. Updated by you as the iteration loop tightens accuracy.
- **Research signals + rules + edge_cases** — live in **`your-recipe-folder/classification-models/<property_id>.json`**. Updated by you as the iteration loop tightens accuracy.

This split matches the operational reality: customers care about category VALUES (CRM property choices); operators care about HOW we get there (signals + rules — engineering knobs).

## Output shape

```json
{
  "category": "MSP",
  "category_label": "Managed Service Provider",
  "reasoning": "managed_services_offered=true (services page lists 'Managed IT Services, Managed Support, Managed Network'; high confidence). Rule fired: managed services dominate regardless of cybersecurity. cybersecurity_offered=true also but doesn't change verdict per priority.",
  "summary": "Mid-market MSP serving SMB clients with bundled managed IT, managed network, and cybersecurity offerings.",
  "signal_evidence": {
    "managed_services_offered": {"found": true, "evidence": "...", "confidence": 95, "source_pages": ["..."]},
    "cybersecurity_offered": {"found": true, "evidence": "...", "confidence": 90, "source_pages": ["..."]},
    "office_supplies_offered": {"found": false, "evidence": "...", "confidence": 85, "source_pages": ["..."]}
  },
  "confidence": 92,
  "rule_evaluations": ["managed_services_offered=true → MSP (rule: managed services dominate regardless of cybersecurity)"],
  "latitude_conversation_uuid": "uuid-of-final-classify"
}
```

The `signal_evidence` field is the auditable per-signal record — important for the iterate-classification-prompt skill (Build 2) to diagnose rule-issue vs. context-issue.

## Cost

For each row:
- N research_signal Latitude calls (~$0.005 each, with Perplexity).
- 1 final classification call (~$0.005, no Perplexity).

ConnectWise example with 3 signals: 4 calls per row, ~$0.020. Compare to existing single-prompt classify (~$0.005). 4x more expensive, but materially more accurate on signal-heavy properties.

## Smoke test (operator authors a model JSON, then runs)

Author `your-recipe-folder/classification-models/account_type.json`:

```json
{
  "schema_version": 1,
  "property_id": "account_type",
  "categories_source": "google_sheet",
  "research_signals": [
    {"name": "managed_services_offered", "look_for": "Does the services page mention Managed IT, Managed Support, Managed Services?", "evidence_format": "boolean + 1-2 quotes with URLs", "search_pages_hint": "/services, /managed-it"},
    {"name": "cybersecurity_offered", "look_for": "Does the company offer cybersecurity services...", "search_pages_hint": "/services, /security"},
    {"name": "office_supplies_offered", "look_for": "Does the company sell printer/office supplies...", "search_pages_hint": "/products, /supplies"}
  ],
  "rules": "If managed_services_offered=true → MSP regardless of cybersecurity. If managed=false AND cybersecurity=true → Cybersecurity. If managed=false AND cybersecurity=false AND supplies=true → Distributor. Otherwise → Other.",
  "edge_cases": [],
  "notes_to_ai": "When uncertain, default to Other."
}
```

Then enable in the recipe:

```yaml
classifications_with_research_signals:
  - property_id: account_type
    model_path: classification-models/account_type.json
```

Compile + run. Inspect the playbook for one `classify_with_signals_account_type__signal_<name>` command per signal + a final `classify_with_signals_account_type__final` step.

## Pointers

- Latitude prompt (final classifier): `latitude-prompt-spec.md` in this directory
- Research primitive: `enrichment-functions/research_signal_via_latitude/`
- Schema reference: `wiki/classification-research-signals-schema.md`
- Plugin adapter: `the classify_with_signals plugin`
- Recipe schema: `wiki/customer-enrichment-recipe-composition.md` (`classifications_with_research_signals:` block)
- Catalog: `skills/enrichment-functions-catalog/SKILL.md`
- Auto-iteration (Build 2, future): `iterate-classification-prompt` skill — operator-driven loop to diagnose failures + propose structural fixes.
