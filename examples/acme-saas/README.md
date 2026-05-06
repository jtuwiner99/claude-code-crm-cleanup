# Worked example: Acme SaaS

A complete, frozen engagement walkthrough you can read top-down in 10 minutes without installing anything. The 30 accounts here are real well-known companies (Slack, Mailchimp, Stripe, Atlassian, etc.) plus a handful of synthetic edge cases. The buyer (Acme SaaS) is fictional — invented to make the scoping decisions concrete.

**Read these files in order:**

1. **`icp.md`** — who Acme SaaS sells to, the tier rubric, what "good" looks like
2. **`how-this-was-built.md`** — the scoping conversation behind the recipe (the human judgment work that doesn't ship in a repo, made visible at toy scale)
3. **`recipe.yaml`** — the resulting enrichment recipe, with property definitions baked in
4. **`scoring-model.json`** — Acme's deterministic tier rules
5. **`input.csv`** — 30 raw accounts as you'd export from a CRM (just `domain` + `company_name`)
6. **`expected-output.csv`** — what `tools/enrich.py` should produce against `input.csv` (the golden snapshot)
7. **`expected-report.md`** — what `tools/report.py` produces from the enriched output (the stakeholder deliverable)

## What this example demonstrates

The hard part of CRM cleanup isn't the enrichment — it's the *scoping*: deciding what to enrich, defining each property so the model gets it right, picking a tier rubric that maps to your sales motion, and knowing what good output looks like.

This folder shows that work end-to-end on one small list. It's the same shape Sculpted runs for clients, just at toy scale, with synthetic context.

## Run it yourself

From the repo root:

```bash
# 1. Enrich
python tools/enrich.py examples/acme-saas/input.csv \
    --playbook examples/acme-saas/recipe.yaml \
    --output tmp/acme-enriched.csv

# 2. Grade against the golden
python tools/qa.py \
    --enriched tmp/acme-enriched-flat.csv \
    --golden examples/acme-saas/expected-output.csv \
    --output tmp/acme-qa.md

# 3. Render the engagement report
python tools/report.py \
    --enriched tmp/acme-enriched-flat.csv \
    --recipe examples/acme-saas/recipe.yaml \
    --qa tmp/acme-qa.md \
    --output tmp/acme-report.md \
    --client-name "Acme SaaS"
```

`recipe.yaml` here is a teaching artifact, not a runtime playbook — `tools/enrich.py` expects a compiled `playbook.jsonc`. To go from this YAML to a runnable playbook, invoke `/crm-cleanup` and feed it the property definitions verbatim from `recipe.yaml`. The skill compiles the playbook for you. This is documented step-by-step in `how-this-was-built.md`.

## What's NOT in this example

- A live enrichment run (you'd need Deepline credits to produce the actual enriched CSV)
- The Sculpted operator wrapper — async stakeholder review surface, manual QA pass, multi-customer playbook library, portal-rendered deliverables
- Provider waterfalls (Lusha → PDL → Crustdata → Apollo) — this single-call recipe uses just one `deeplineagent` research call per row

The single-call recipe matters: it's deliberately simple so the example reads top-down. Production-scale recipes layer in waterfalls, classification primitives, and per-customer scoring models. See [the agency-mode upsell](../../README.md#hiring-sculpted) for what changes at production scale.
