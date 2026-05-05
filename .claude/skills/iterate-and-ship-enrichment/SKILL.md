---
name: iterate-and-ship-enrichment
description: Use this skill when the user wants to build, iterate on, deploy, or invoke an enrichment recipe. Covers the canonical two-phase flow — iterate locally on a CSV sample via `deepline enrich`, then promote to a hosted Deepline workflow via the converter. Trigger on phrases like "iterate on enrichment for X", "test the recipe", "ship this to production", "deploy the workflow", "invoke the workflow with this payload", "check the run status", or any time enrichment work is moving between draft and production.
---

# Iterate & Ship Enrichment

The canonical two-phase flow for moving an enrichment recipe from draft to production. Both paths run off the same compiled `playbook.jsonc`; pick based on whether the recipe is being iterated on or ready to go live.

## When to invoke this skill

- User mentions iterating on, building, or refining an enrichment recipe
- User wants to ship a recipe to production / deploy the workflow / make it callable
- User wants to invoke a deployed workflow (CRM webhook, lead inbound, ad-hoc enrichment)
- User asks for run status / triage on a deployed workflow
- User says "ship it", "go live", "test against 50 rows", "deploy"
- User is preparing a demo / video that needs a hosted workflow URL

If the user is asking *which* enrichment functions to use (i.e. recipe composition), see the [`enrichment-functions-catalog`](../enrichment-functions-catalog/SKILL.md) skill instead. This skill is about the **execution loop**: iterate → ship → invoke. The catalog skill is about **what goes inside** the recipe.

## The two-phase flow

```
                  iterate                      ship
              (CSV mode)               (hosted workflow)
                   │                            │
            ┌──────▼──────┐              ┌──────▼──────┐
            │ deepline    │              │ converter + │
            │ enrich      │              │ workflows   │
            │ (CSV mode)  │              │ apply       │
            └──────┬──────┘              └──────┬──────┘
                   │                            │
            local enriched                hosted workflow
            CSV deliverable               (DAG view, traces,
            + results writeback           persistent runs,
                                          shareable URLs)
                                                │
                                         ┌──────▼──────┐
                                         │ deepline    │
                                         │ workflows   │
                                         │ call        │
                                         └─────────────┘
```

## Phase 1 — Iterate (CSV mode, fast inner loop)

**Use when:** building or tweaking a recipe, debugging a specific row failure, running a one-shot batch enrichment that won't be re-run.

```bash
# This repo's tools/enrich.py wraps deepline enrich for the bundled playbook
python tools/enrich.py path/to/input.csv --rows 0:50

# Or call deepline directly with your own playbook
deepline enrich \
  --input path/to/input.csv \
  --output path/to/enriched.csv \
  --config path/to/playbook.jsonc \
  --rows 0:50 \
  --json
```

Lands `playbook.jsonc` + an enriched CSV in your run output directory.

**Iteration cycle:** run → review failures via QA loop → edit your taxonomy config / project recipe → re-compile → re-run. Typical iteration on 50-100 rows.

## Phase 2 — Ship (hosted workflow, production-ready)

**Use when:** recipe is iterated and ready for live invocation, customer needs persistent run history / shareable trace URLs, you're preparing a demo or video.

The flow:

1. Compile the latest playbook from current scoping.
2. Convert the CSV-mode playbook → hosted-workflow `apply` payload via your converter (handles all four CSV→hosted gotchas — bracket-form input reads, waterfall vs simple-tool wrap, run_javascript shape detection, `{{<alias>}}` template envelope rewriting). See [`docs/best-practices/deepline-best-practices.md`](../../../docs/best-practices/deepline-best-practices.md) → "Four CSV-to-hosted gotchas".
3. Call `deepline workflows apply` to publish the workflow.
4. Smoke-test with a 1-row payload (e.g. `{"Company Domain Name":"stripe.com"}`).
5. Archive `apply.json`, `apply-result.json`, `smoke-test-run.json`, `convert-warnings.md` to a per-deploy directory.
6. Update a `latest-workflow.json` pointer for downstream invocations.

```bash
deepline workflows apply --workflow-name <slug>_<project>_v1 --payload-file apply.json
```

**Default trigger is `api`.** Use `webhook` or `cron` for triggered workflows.

## Live invocation (after ship)

```bash
deepline workflows call --workflow-id <id> --payload '{"Company Domain Name":"underarmour.co.uk"}'
```

Tail the run live or fire-and-forget.

**Critical:** use `deepline workflows call --workflow-id` exclusively. NEVER post to a hosted workflow's inbound webhook URL for ad-hoc invocation — that path silently drops events as `event_not_matched`. The webhook URL is for the user's CRM/lead-form integrations, not for operator-side calls.

## Run triage

```bash
# Recent runs of a workflow
deepline workflows runs list --workflow-id <id>

# One specific run's full detail
deepline workflows runs get --run-id <run_id>
```

## Decision rules

| Situation | Pick |
|---|---|
| Tweaking an existing recipe; want fast feedback on edge cases | CSV mode `--rows 0:50` |
| One-shot CSV batch I won't re-run | CSV mode (don't pollute workflow inventory) |
| Customer asked for a Deepline run link they can share | Hosted workflow (workflows have shareable trace URLs; CSV runs don't) |
| Recording a demo or video walkthrough | Hosted workflow (DAG view is photogenic; `enrich` stdout is not) |
| CRM webhook needs to enrich inbound leads in real-time | Hosted workflow with `webhook` trigger, then production system calls `workflows call` |
| Scheduled enrichment (e.g. weekly job-change check) | Hosted workflow with `cron` trigger (note: cron has no row input — recipe must source its own data) |
| Triaging why a deployed workflow run failed | `deepline workflows runs get --run-id <id>` |

## Don't auto-deploy on every CSV run

Workflow inventory pollution (`<client>_<project>_v23`-style stale workflows) is a real cost on the Deepline side. Operator-controlled deploys only.

The recommended operator pattern: **iterate with CSV mode, ship with `deploy-workflow` once the recipe is right.** The CSV path stays authoritative for batch enrichment; the hosted-workflow path is for ongoing live work (CRM webhooks, lead inbound, ad-hoc enrichment) where visibility matters more than iteration speed.

## What this skill does NOT cover

- **What to put inside the recipe** (which enrichment functions to compose, which providers to use). See [`enrichment-functions-catalog`](../enrichment-functions-catalog/SKILL.md).
- **CSV→hosted converter implementation.** The four documented gotchas are the spec — see [`docs/best-practices/deepline-best-practices.md`](../../../docs/best-practices/deepline-best-practices.md).
- **Latitude QA loop** for iterating on classification prompts. See Latitude's prompt-iteration documentation.
- **CRM writeback** of enriched rows back to the source CRM. Today: enriched CSV → manual import. Future: native writeback.
