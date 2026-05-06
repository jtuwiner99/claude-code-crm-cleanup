# Project memory — claude-code-crm-cleanup

Project knowledge that future Claude sessions should pick up but isn't already in [CLAUDE.md](CLAUDE.md). Add only durable architectural / workflow / gotcha entries; ephemeral notes go in `tmp/`.

## Validated benchmarks (2026-05-05)

End-to-end run of the canonical 6-property cleanup baseline against `tmp/sample-accounts.csv` (50 well-known SaaS accounts) hit **88.9% accuracy** vs `tmp/golden-accounts.csv` (15 hero rows, 90 graded cells). Per-field:

| Property | Pass | Total |
|---|---:|---:|
| `company_name` | 13/15 | 87% |
| `company_linkedin_url` | 14/15 | 93% |
| `employee_count` | 12/15 | 80% |
| `state` | 13/15 | 87% |
| `country` | 13/15 | 87% |
| `company_type` | 15/15 | 100% |

**Cost (validated)**: ~$0.022/row for the baseline (Apollo $0.017 + Harvest $0.005). Headcount-by-function add-on (Dropleads sales + revops) is **$0/row** — `dropleads_get_lead_count` is a free purpose-built sizing endpoint. See [.claude/skills/headcount-by-function/SKILL.md](.claude/skills/headcount-by-function/SKILL.md) for the recipe.

**Auto-recovery**: Harvest 429s recover cleanly via `tools/retry_harvest_chunked.py`; on the validation run 21/50 rows hit `code_22` and 21/21 recovered.

## Known recurring failure modes

The 88.9% gap clusters on two fixable patterns. Don't try to fix them silently — the user has confirmed they prefer null-over-guess at runtime.

1. **Brand-name legal-suffix trim is incomplete.** `verdict` step in [recipes/default-cleanup-template.jsonc](recipes/default-cleanup-template.jsonc) only strips `Inc / LLC / Ltd / GmbH`. Misses `Labs` (→ Notion Labs vs Notion) and `Technologies` (→ Slack Technologies vs Slack). Cheapest accuracy lever: extend the suffix list in the verdict-step JS. Bumps run from 88.9% → ~91% on the golden.

2. **Apollo coverage gaps cascade to all downstream nulls.** When Apollo's `enrich_company` doesn't return a verifiable `linkedin_url`, the playbook (per the user's "no AI guess" contract) cascades nulls through `employee_count`, `street`, `city`, `state`, `zip`, `country`. On the golden: `notion.so` and `segment.com` hit this — both legitimate US SaaS companies that ranked Tier 4 in scoring solely because of cascade. **This is the contract working as intended**; the fix is upstream coverage (e.g. layering `enrichment-functions/linkedin_url_verified/` in the waterfall), not relaxing the contract.

## Auto-flatten contract (always emit `<input>-flat.csv`)

Originally surfaced via sim-test feedback (recovered memory: see `~/.claude/projects/-Users-JT-repositories-claude-code-crm-cleanup/memory/feedback_always_flatten_enrich_output.md`). The deepline-native enriched CSV writes one column per playbook step (`inputs`, `lookup`, `harvest`, `classify`, `verdict`) as JSON-encoded blobs — unusable in spreadsheets/pandas/CRM imports. Every script that produces a deepline-native CSV must auto-emit a flat companion at `<input>-flat.csv`.

Already wired:
- [tools/enrich.py](tools/enrich.py) — invokes `tools/flatten.py` post-run
- [tools/retry_harvest_chunked.py](tools/retry_harvest_chunked.py) — re-flattens after retry
- [tools/headcount.py](tools/headcount.py) — operates directly on the flat CSV (no separate flatten needed)

When summarizing run results to the user, **always reference `tmp/enriched-flat.csv`**, not the deepline-native `tmp/enriched.csv`.

## Tier-scoring path split — deterministic vs Latitude

Two scoring paths exist in this repo and they're not interchangeable:

- **[tools/score.py](tools/score.py) — deterministic JSON-rule scorer.** Pure pattern match (`match_all` / `match_any` over typed operators eq/in/gt/gte/between/is_null). No LLM call at scoring time, fully reproducible, free. Use when scoring rules are crisp and rule-based (e.g. "Tier 1 if SaaS + US + 50–2000 employees"). Companion: [docs/schemas/account-scoring-model.md](docs/schemas/account-scoring-model.md).

- **[enrichment-functions/score_account_via_latitude/](enrichment-functions/score_account_via_latitude/) — Latitude-managed prompt scorer.** Cloud LLM call per row with prompt versioning + dataset-driven regression. Use when scoring requires judgment (fuzzy ICP fit, edge cases, narrative inputs). Costs per row, slower, but evolvable.

The /crm-cleanup skill defaults to the deterministic path (cheap + fast for the demo flow); the Latitude path is referenced as a "Pro upgrade path" in [.claude/skills/crm-cleanup/SKILL.md](.claude/skills/crm-cleanup/SKILL.md).

## Phase-5 hosted-workflow promotion uses `--trigger api`, not cron

Recorded in [.claude/skills/crm-cleanup/SKILL.md](.claude/skills/crm-cleanup/SKILL.md) Phase 5: `tools/promote_to_workflow.py` rejects cron triggers because the playbook is row-driven (per-row inputs from CSV). API trigger is the only sensible choice for a demo deploy; webhook needs CRM-side wiring beyond the demo's scope. Smoke test default: `--smoke-domain stripe.com --smoke-company-name Stripe` (known-clean, reproducible verdict).

## Repo workflow conventions

- Direct push to `main` is **blocked** by org policy ("Pushing directly to the default branch (main) bypasses pull request review"). Use feature branches + PRs. PR #1 set the precedent; subsequent merges follow the same flow.
- `tmp/` is per-session — only `tmp/sample-accounts.csv` and `tmp/golden-accounts.csv` are committed; everything else is gitignored. After demo iterations, clear `tmp/` (keep the two committed inputs).
- HubSpot OAuth via `tools/install_hubspot.py` writes `tmp/hubspot-properties.csv` — that's user CRM data; gitignored, treat as scratch, clear post-session.
