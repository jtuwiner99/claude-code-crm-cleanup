# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A giveaway repo accompanying Sculpted's "Claude Code for CRM Cleanup" YouTube course. The headline experience is `claude → /crm-cleanup`: a conversational skill walks the user through setup, takes natural-language descriptions of the properties they want to enrich, generates a Deepline playbook ad-hoc, and runs it.

Open-source tools wrap a closed-source agency operator system. The README explicitly positions the repo as the *engine*; the human judgment work (property scoping, QA, edge cases) is what Sculpted sells as a service.

## Architecture: orchestrator → runner → runtime

Three layers, never collapsed:

1. **Claude Code (orchestrator)** — `.claude/skills/crm-cleanup/SKILL.md` is the headline skill. It conducts the user through four phases: setup check, property definition, compile + run, optional iteration against a golden dataset. **It generates `tmp/playbook.jsonc` per run** — there is no static fallback playbook.
2. **Python runner (deterministic)** — `runner/deepline_runner.py` shells out to the `deepline` CLI; `tools/enrich.py` is the thin CLI wrapper. Both are pure plumbing — no LLM calls.
3. **Deepline (runtime)** — the actual enrichment engine. Hosted; the local code only invokes its CLI. Auth is persisted by the CLI at `~/.local/deepline/.env`; the Python script separately requires `DEEPLINE_API_KEY` in the project's `.env`.

## Commands

```bash
# Headline path (the documented user flow)
claude
> /crm-cleanup

# Setup (the skill walks the user through this; manual if preferred)
pip install -r requirements.txt
cp .env.example .env  # then fill ANTHROPIC_API_KEY + DEEPLINE_API_KEY
curl -s 'https://code.deepline.com/api/v2/cli/install' | bash  # Deepline CLI

# Pull real CRM properties from a HubSpot account (OAuth device-code flow)
python tools/install_hubspot.py

# Run a generated playbook directly (advanced — `/crm-cleanup` does this for you)
python tools/enrich.py <csv> --playbook tmp/playbook.jsonc

# Pilot a row range
python tools/enrich.py <csv> --playbook tmp/playbook.jsonc --rows 0:10
```

No build step, no test suite, no lint config. Runtime correctness is verified end-to-end via real Deepline runs against `tmp/sample-accounts.csv` (50 rows with hero rows pre-validated for expected verdicts — see README "Hero rows in the bundled CSV").

## Conventions worth knowing

**No static playbook.** Every run generates a fresh `tmp/playbook.jsonc` from the user's described properties. If you find yourself wanting to add a `playbooks/` directory back as a "default", read the SKILL.md first — it explains why per-run generation is the chosen path and what gotchas make static playbooks brittle.

**Output column-name parity.** The verdict columns emitted by the per-run playbook use the same canonical field names as the per-function Latitude library in `enrichment-functions/` (e.g. `is_acquired`, `relationship_type`, `verified_country_code`, `routing_flag`). This is a deliberate drop-in upgrade path — swap a single-call playbook for the multi-function Latitude pipeline and downstream CRM write-back code doesn't change.

**Deepline-specific JS gotchas live in the SKILL.md.** Four empirically-validated patterns matter when generating playbooks (see `.claude/skills/crm-cleanup/SKILL.md` → "Deepline gotchas — write the playbook this way"):
- `row.<col>.X` auto-unwraps `.result` in `run_javascript` code
- `row.research.object.X` (not `row.research.X`) for `deeplineagent` output
- `jsonSchema.required` must list every property name in `properties` — partial required arrays are rejected
- Don't use `run_if_js` gates — gate semantics are inconsistent across deepline versions

**HubSpot OAuth is a Sculpted-hosted endpoint, not local.** `tools/install_hubspot.py` POSTs to a Supabase Edge Function at `aofpyrbquqxovunsxosb.supabase.co/functions/v1/`. The OAuth tokens never live on the user's machine; only the resulting CSV does. The repo's `.env` does not need any HubSpot credentials.

**Reference vs. loaded.** Everything in `enrichment-functions/`, `docs/`, and `reference/` is **reference material** — not loaded or invoked by `/crm-cleanup`. They exist as authoring guidance for users who want to compose custom playbooks beyond the per-run flow. The skill teaches the pattern; the reference shows the production-grade examples.

## Confidentiality

This is a public open-source repo. Pre-publication scrubs removed all client names, internal infrastructure paths, agency-engagement framing, and commercial constructs. When making changes:
- Don't reference Sculpted's internal Studio compiler, agency directives, client repos, or the Sheets-based operator surface
- Lead-gen positioning (the README's "engine Sculpted runs" framing and hire-Sculpted CTAs) is intentional — keep
- See README "What this repo is NOT" for the explicit boundary
