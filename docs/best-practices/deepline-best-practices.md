# Deepline Best Practices

Opinionated rules for using [Deepline](https://deepline.io) well — captured from production CRM-cleanup engagements. This doc is about **opinionated choices**, not Deepline's capabilities.

## Waterfall ordering — the house rule

**Company firmographic waterfall** (`company_core`): Lusha → PDL → Crustdata → Apollo.

Rationale:
- **Lusha first.** Cheapest provider for LinkedIn-flavored company data (employee count, industry, HQ, LinkedIn URL). Best $/row on the firmographic basics most CRM-cleanup workflows need.
- **PDL second.** Fills long-tail domains Lusha misses (non-US, smaller cap). Richer industry taxonomy (`industry_v2`).
- **Crustdata third.** Thinnest payload but catches edge cases the prior two miss. No tech stack, no funding.
- **Apollo last.** Strong on US B2B SaaS, returns tech stack + funding, but the most expensive of the four — reserve as a long-tail fallback rather than the default.
- **Why not Adyntel.** Adyntel is ad-intelligence, not firmographic. Different problem.

> **Note:** earlier guidance put Apollo first based on US-SaaS coverage. Real-world cost analysis on multi-thousand-row runs flipped the order — Lusha returns the same fields as Apollo for substantially less per call on the typical firmographic basics. Apollo's tech-stack + funding fields are nice-to-have but rarely the gating signal in a CRM-cleanup workflow, so they don't justify the cost premium when used as primary.

**Email waterfall**: `name_and_domain_to_email_waterfall` — let Deepline's internal waterfall handle provider routing (Apollo → Hunter → Prospeo → LeadMagic → Icypeas). Don't roll your own.

**Decision-maker waterfall**: `company_to_contact_by_role_waterfall` — same logic; Deepline handles internal routing.

**HQ address**: extract from `company_core.hq` (already paid for). If empty, `deeplineagent` web-search fallback. **Do NOT** re-call a firmographic provider just for address.

## When to use `deeplineagent` vs a structured provider

**Rule: structured first, AI only for synthesis.**

- Structured provider (Apollo, PDL, Hunter, etc.) = deterministic, cheap, auditable. Use whenever the data exists as a field somewhere.
- `deeplineagent` = non-deterministic, slower, variable cost. Reserve for:
  - Classification (mapping unstructured inputs to a taxonomy)
  - Narrative summary (150-word brief from structured inputs)
  - Identity verification (three-way compare of fuzzy signals)
  - Extraction from unstructured text (not a provider hit)
  - Discovery (web-search fallback when structured providers miss)

**Never use `deeplineagent` for:** domain validation, employee count lookup, industry codes, LinkedIn URL discovery — all of these have cheaper deterministic providers.

## Qualification gates — the two-phase model

Gates filter unqualified rows before expensive steps. Because classification is the most expensive step, split gates into two phases:

- **`pre_classification`** — checks data from the `company_core` waterfall (employees, industry, HQ country, tech stack, etc.). Gates here skip summary + classification entirely on failure. This is where most gates belong.
- **`post_classification`** — checks data produced by your classification step (e.g. "must classify as SaaS"). Gates here skip deep-enrichment on failure. Post-gates automatically inherit pre-phase failures, so a row can't "pass" post by bypassing pre.

Gate fields use dot-separated paths resolved via a null-safe `get()` helper:

```
company_core.employee_count
company_core.hq.country
classify_company_type.object.company_type
```

Downstream `run_if_js` checks the appropriate phase alias:

```js
// summary + classification
return row.qualification_pre && row.qualification_pre.qualification_status === 'qualified';

// deep enrichment (when post gates exist)
return row.qualification_post && row.qualification_post.qualification_status === 'qualified';
```

If only one phase has gates, emit a single `qualification` step and use that alias everywhere — backward-compatible with simple single-phase setups.

**Never gate:**
- `domain_clean` normalization — free, downstream needs it
- `company_core` waterfall — pre-gates read from this; gating it creates a cycle
- `linkedin_verified` — feeds into gate signals, can't be gated by them

**Always gate:**
- `deeplineagent` calls (summary, classification, identity verification)
- Any Deepline waterfall (email, phone, decision-maker) — these cost credits per provider attempt
- Any writeback or outbound action

## Templating gotchas

1. **Array indexing:** `{{alias.0.field}}` usually works for first-item access. When unsure, use `run_javascript` to normalize first (e.g., pick primary contact from a decision-maker list).
2. **Null handling:** `{{alias.missing_field}}` renders as the literal string `undefined` in some contexts. Always coalesce in consumer step: `const x = row.X || null;`
3. **`extract_js` receives unwrapped output.** The function parameter is already `output_data` = what the provider returned under `result` or `result.data`. Don't double-unwrap.
4. **`run_if_js` must `return`.** Must be a function body that returns a boolean. Silent pass-through if you forget the return.
5. **`row` inside JS = the row context.** Has all prior command outputs keyed by alias, PLUS original CSV columns under their original header names (e.g. `row['Company Domain Name']`).

## Compiler-enforced invariants

A good playbook compiler refuses to emit a playbook that violates any of these:

1. **Tool whitelist.** Every `command.tool` value must exist in [`reference/deepline-tools.json`](../../reference/deepline-tools.json). Catches typos like `crustdata_company_search` (wrong) vs `crustdata_enrich_company` (correct).
2. **Alias resolution.** Every `{{alias}}` reference in a payload, `run_if_js`, or `extract_js` must refer to a prior command's alias in the same playbook. No forward references, no orphan aliases.
3. **Required payload fields.** Consult `reference/tools/{tool_id}.json` → `input_schema.required`. Reject if missing. (Example: `company_to_contact_by_role_waterfall` requires `roles`.)
4. **Schema validation.** After building the playbook dict, validate against [`reference/deepline-schema.json`](../../reference/deepline-schema.json) → `schemas.enrich_config`. Reject on any schema violation before writing to disk.
5. **extract_js syntax check.** If an `extract_js` is present, parse it as JavaScript via Node (`node --check`). Reject on syntax error.
6. **deeplineagent needs jsonSchema.** Unless the deeplineagent step's output is only consumed as free text, require `jsonSchema` in its payload. Structured output is the default.

Violations should raise at compile time, not run time. This prevents the "invented tool name" bug class.

## CSV iteration vs. hosted-workflow promotion

The same compiled `playbook.jsonc` can run two ways. Pick based on what you actually need:

**Use CSV iteration (`deepline enrich`) when:**
- Building or tweaking a recipe — fast inner loop on 50-100 row samples beats apply/call latency.
- Running a one-shot batch enrichment that you'll never re-run from the same playbook.
- Cost-sensitive bulk runs where workflow-mode dispatcher overhead would dominate.
- Debugging a specific row failure — local stdout + the compile log is more accessible than a hosted run trace.

**Use hosted workflow (`deepline workflows apply`) when:**
- The recipe is production-ready and should run on ongoing inbound triggers (CRM webhooks, lead form submissions, scheduled job-change checks).
- You need shareable trace URLs (handing a customer a Deepline run link to demonstrate the pipeline working).
- The workflow-builder DAG view matters for cinematics — public demos, video walkthroughs, deliverables.
- You need persistent run history accessible to multiple people (audit log of every enrichment).
- Compliance / audit requires structured run records with timestamps, step-level success/failure, and trace inspection.

**Recommended operator pattern.** Iterate in CSV mode until the recipe is right (typically several cycles tweaking property definitions + enrichment steps based on QA results). Once the recipe holds up on golden cases, promote to a hosted workflow. From that point forward, CSV mode is for *future* iteration on the same recipe; live invocation routes through `call-workflow` against the deployed workflow.

**Don't auto-deploy on every CSV run.** Workflow inventory pollution (`<client>_<project>_v23`-style stale workflows) is a real cost on the Deepline side. Operator-controlled deploys only.

## Four CSV-to-hosted gotchas

When converting a CSV-mode `playbook.jsonc` into a hosted-workflow apply payload, four runtime deltas trip people up. A converter must encode each — never re-discover them on the next port:

1. **Static analyzer rejects `row.<unknown>`.** The hosted runtime validates that every `row.X` reference resolves to a known column. CSV mode is permissive; hosted is strict. Solution: use bracket form `row['X']` for any column whose name has spaces or punctuation, and pre-declare any computed aliases.
2. **No `row` object inside cron-triggered runs.** Scheduled hosted workflows fire without a row context. Code that references `row` at top-level breaks. Solution: gate all row reads on `if (typeof row !== 'undefined')`, or split into two workflows.
3. **Non-uniform `.result` wrap.** Waterfalls wrap output as `{result: {data: ...}}`; simple tools wrap as `{result: ...}`; primitives like `run_javascript` return raw values. The hosted runtime is stricter than CSV about which is which. Solution: per-tool unwrap rules in the converter; never assume.
4. **`{{alias}}` template envelope semantics.** In hosted mode, `{{alias}}` resolves to the *full envelope* including the `result` wrapper, whereas CSV mode often unwraps. Solution: write `{{alias.result.field}}` explicitly in payloads destined for hosted; the converter rewrites if needed.

## When these rules change

Bump the recipe version in [house-defaults/core-account-enrichment.md](house-defaults/core-account-enrichment.md) and document the reasoning there. Stamp the recipe version into every emitted playbook so runs are reproducible.
