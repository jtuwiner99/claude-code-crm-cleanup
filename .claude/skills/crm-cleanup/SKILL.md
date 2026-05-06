---
name: crm-cleanup
description: Clean and enrich a CSV of B2B accounts. Claude Code is the orchestrator — it walks the user through setup (env, deps, Deepline CLI, optional HubSpot install), takes natural-language definitions of the properties they want enriched, assembles a Deepline playbook on the fly with those definitions baked in, runs `deepline enrich`, and (optionally) iterates against a golden dataset to surface accuracy + suggest property-definition refinements. Use whenever the user asks to enrich, clean, qualify, classify, or research a list of company accounts. Headline skill of the repo.
---

# CRM Cleanup

The headline skill. Claude Code orchestrates; Deepline runs the enrichment.

The architecture: Claude takes the user's natural-language property definitions, composes a custom `deeplineagent`-driven playbook with those definitions baked into the prompt + jsonSchema, and shells out to `deepline enrich`. The user gets the parallelism + observability + provider integrations of Deepline; the conversational ergonomics of Claude Code.

The flow has four phases:

1. **Setup check** — verify env, deps, Deepline CLI; help install what's missing.
2. **Property definition** — ask what to enrich, take NL definitions for each.
3. **Compile + run** — copy `recipes/default-cleanup-template.jsonc` to `tmp/playbook.jsonc`, customize the classify+verdict steps for the user's properties, then `deepline enrich` it. Auto-recovers from Harvest rate limits via chunked retry.
4. **Grade + report** — run `tools/qa.py` against `tmp/golden-accounts.csv` (when present) to surface a headline accuracy %, then `tools/report.py` to render `tmp/engagement-report.md` — the stakeholder-facing markdown brief that closes the session.
5. **Ship to Deepline workflow (optional)** — offer the user a one-question close: publish the validated playbook as a hosted Deepline workflow with a live DAG, shareable trace URL, and a `deepline workflows call` endpoint. Auto-runs the converter (`tools/promote_to_workflow.py`), smoke-tests against one row, and appends a "Live workflow" section to the engagement report.

User does about 60 seconds of typing across phases 1+2; phase 3 is the spectacle (Deepline session UI streams progress in parallel); phase 4 is the close — accuracy verdict + the artifact you'd hand to a CRO; phase 5 is the live demo asset they can share.

## Phase 1: Setup check

Run these checks in order. Surface only what's broken — don't ceremoniously announce everything that's working.

```bash
# 1. .env present? Required keys: ANTHROPIC + DEEPLINE.
test -f .env && grep -q "^DEEPLINE_API_KEY=" .env && grep -q "^ANTHROPIC_API_KEY=" .env

# 1a. Harvest key set? Optional but RECOMMENDED — enables exact LinkedIn employee counts.
grep -qE "^HARVEST_API_KEY=[^<\s].+" .env  # passes only on a real value (not "<your-harvest-key>" placeholder)

# 2. Python deps installed?
python3 -c "import yaml, requests" 2>&1

# 3. Deepline CLI on PATH?
which deepline

# 4. Node.js installed? The Deepline CLI shells out to a local Node-based playground backend
#    to execute playbooks — without Node, every run fails with "Missing Node.js executable".
which node && node --version

# 5. Node TLS reachability? Fresh Node installs (especially Node 25 via Homebrew) sometimes
#    ship without default trust roots, so npm subprocesses inside the Deepline CLI fail with
#    UNABLE_TO_GET_ISSUER_CERT_LOCALLY when fetching the agent skills package.
node -e "require('https').get('https://registry.npmjs.org/', r => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))" 2>/dev/null

# 6. Deepline credit balance — small but non-zero check. The first run plus retry on
#    50 sample rows costs ~$0.05–0.10 of credits; a fresh free-tier balance covers it.
deepline billing balance 2>&1 | grep -oE '[0-9]+(\.[0-9]+)?' | head -1
```

Branch on results:

- **No `.env`**: `cp .env.example .env`, then ask the user to fill `DEEPLINE_API_KEY` and `ANTHROPIC_API_KEY` (and ideally `HARVEST_API_KEY` — see next branch). Wait for confirmation, then re-run the check.
- **Missing deps**: `pip install -r requirements.txt`. Confirm success before proceeding.
- **No `deepline` CLI**: `curl -s 'https://code.deepline.com/api/v2/cli/install' | bash`. Verify `deepline --version` works after.
- **No Node.js (`which node` empty / version missing)**: explain plainly:

  > Say (verbatim or close to it): *"Heads up — you don't have Node.js installed. The Deepline CLI uses a local Node-based 'playground backend' to execute playbooks; without Node, every run fails immediately with 'Missing Node.js executable'. Easiest fix on macOS is `brew install node` (~60s, ~80MB). On Linux: `sudo apt install nodejs` or via your package manager. On Windows: nodejs.org installer. Want me to run `brew install node` now?"*

  Branch:
  - **User says yes**: run `brew install node` (or the platform equivalent). Note: this is a system-wide install requiring user authorization in some Claude Code setups — if denied, fall back to asking the user to run it themselves with `! brew install node` in the prompt.
  - **User wants to install themselves**: wait for confirmation, re-run check 4.

- **Node SSL fails** (check 5 returns non-zero, OR a run later errors with `UNABLE_TO_GET_ISSUER_CERT_LOCALLY`): explain and fix:

  > Say (verbatim or close to it): *"Your Node install can't verify TLS certificates against the public CA bundle — happens often on fresh Homebrew Node 25 installs. The Deepline CLI fails when it tries to npm-fetch its agent skills package. Quick fix: point Node at the system CA bundle via `NODE_EXTRA_CA_CERTS` in your `.env`. Should I add it?"*

  Branch:
  - **User says yes**: detect the CA bundle path (`brew --prefix ca-certificates 2>/dev/null` → typical `<prefix>/cert.pem`; on some systems `/etc/ssl/cert.pem` works). Append `NODE_EXTRA_CA_CERTS=<path>` to `.env`. `tools/enrich.py` loads `.env` via dotenv, so this propagates to the deepline CLI's npm subprocess automatically. Verify check 5 passes after.
  - **User declines**: continue, but flag that the first run will likely fail with an SSL error and we'll loop back here.

- **Deepline credit balance below ~1 credit** (check 6): warn:

  > Say (verbatim or close to it): *"Your Deepline credit balance is very low ({balance}). A 50-row sample run with retries needs ~5–10 credits ($0.50–$1.00). Top up at https://deepline.ai/billing before running, otherwise rows will fail with 'Insufficient credits'."*

  Don't block — let the user proceed if they want. If a subsequent run fails with `Insufficient credits`, loop back here with a stronger nudge.
- **No `HARVEST_API_KEY` (optional but strongly recommended — proactively nudge once)**: if the value is missing or still the `<your-harvest-key>` placeholder, ask the user before moving on:

  > Say (verbatim or close to it): *"Quick optional add — `HARVEST_API_KEY` isn't set. With it, `numberofemployees` does a **live LinkedIn scrape via the Harvest API** and returns the exact integer (e.g. 1,113). Without it, the playbook falls back to whatever the AI agent reads from LinkedIn search snippets — usually only a public band like '1,001-5,000', floored to 1001. The playbook works either way; Harvest just sharpens accuracy meaningfully. Get a key at https://harvest-api.com/admin/api-keys (paid, ~$0.005/row). Want to add it now or skip and use the band fallback?"*

  Branch on the answer:
  - **Add now**: tell the user to paste the key into `.env` after the `HARVEST_API_KEY=` line (suggest `! sed -i '' 's/^HARVEST_API_KEY=.*/HARVEST_API_KEY=hak_their_key/' .env` on macOS so the value never lands in your tool output). Wait for confirmation, re-run the 1a check.
  - **Skip**: continue. Note in the Phase 3 run summary that `numberofemployees` will be band lower-bounds, not Harvest-exact integers, and surface this in the `employee_source` column on every row.

  Mention this nudge ONCE per session. The compile step (`tools/enrich.py`) substitutes `<HARVEST_API_KEY>` in `tmp/playbook.jsonc` from `.env` and surfaces unresolved placeholders as warnings — without the key, Harvest calls 401 cleanly and the verdict step falls back to the agent's tier-2 result.

- **HubSpot path (recommended for real-data use)**: if `tmp/hubspot-properties.csv` does NOT already exist AND the user hasn't already pointed at a CSV path, **proactively suggest** the install:

  > Say (verbatim or close to it): *"To run this on your real CRM data, install Sculpted's HubSpot app — one OAuth, takes ~30 seconds, no API keys to manage. Or you can use the bundled `tmp/sample-accounts.csv` (50 well-known companies) for a quick demo. Which do you want?"*

  Branch on the answer:
  - **HubSpot install**: run `python tools/install_hubspot.py`. The CLI handles the OAuth flow; CSV lands at `tmp/hubspot-properties.csv`. Once complete, set this as the input path for Phase 2 automatically.
  - **Sample CSV**: proceed with `tmp/sample-accounts.csv`.
  - **User has their own CSV**: accept the path they provide and skip both options.

  Salesforce / other CRM users: tell them the native installer isn't shipped yet and to manually export their accounts to a CSV with `domain` + `company_name` columns. Save to `tmp/your-accounts.csv` and use that as the Phase 2 input.

  Only mention this nudge ONCE per session. If the user already has a real-data CSV (anything other than the bundled sample), don't keep pushing.

If everything is set up, just say "Setup ✓" and move on.

## Phase 2: Property definition (the user's 60 seconds)

Ask two questions:

1. **Input CSV path.** Default: `tmp/sample-accounts.csv`. If the user has their own (e.g. `tmp/hubspot-properties.csv` from the install flow), use that.
2. **What properties to enrich.** Open question — list in natural language.

Example exchange:

```
You: What properties do you want to enrich for each account?

User: Industry, employee count tier, whether they've been acquired, and a
      one-sentence pitch description.
```

For each property, ask one clarifying question to pin the definition:

```
You: Got it — four properties. Quick pins:

  • industry — fixed taxonomy (e.g. "B2B SaaS / E-commerce / FinTech /
    Hardware / Services / Other") or freeform string?
  • employee_count_tier — what buckets? "1-50 / 51-500 / 501+"?
  • is_acquired — just true/false, or include the acquirer name when true?
  • pitch — one sentence describing what they sell, or one sentence on
    their target market?
```

Take the user's answers. Build a property schema in memory like this:

```yaml
properties:
  - name: industry
    description: >
      Industry classification. One of: B2B SaaS, E-commerce, FinTech,
      Hardware, Services, Other. Pick the closest match based on what the
      company sells. Conservative — when uncertain between two, prefer
      "Services" over "Other".
    type: string
    enum: [B2B SaaS, E-commerce, FinTech, Hardware, Services, Other]
  - name: employee_count_tier
    description: >
      Approximate company size bucket: 1-50, 51-500, or 501+. Use LinkedIn
      employee count when available; fall back to web-research signals
      (Crunchbase, About page) otherwise.
    type: string
    enum: ["1-50", "51-500", "501+"]
  - name: is_acquired
    description: >
      Has this company been acquired by or merged into a structurally
      different parent? Default false on weak evidence. Distinguish from
      a DBA / rebrand (same legal entity, new name) — those are NOT
      acquired.
    type: boolean
  - name: acquirer_name
    description: >
      When is_acquired=true, the parent company's primary brand name.
      Null otherwise.
    type: ["string", "null"]
  - name: pitch
    description: >
      One sentence describing what the company sells.
    type: string
  - name: reasoning
    description: >
      1-2 sentences citing specific evidence behind the most surprising /
      non-default verdict on this row.
    type: string
```

Save this to `tmp/recipe.yaml` so the user can review/edit before the run kicks off. Show them the path. Tell them to glance at it; offer to make tweaks if the schema doesn't capture their intent.

## Phase 3: Compile + run (the spectacle)

### 3a. Compile playbook

Start from `recipes/default-cleanup-template.jsonc` — the canonical 6-step playbook (every line has been debugged against real Deepline runs; the inline comments call out every empirical gotcha). Copy it to `tmp/playbook.jsonc` and customize the per-run bits.

The structural spine is **invariant** — never change the alias names, step order, or auto-unwrap-aware JS in the verdict. The bits that change per run are clearly marked in the template:

```
1. inputs        — domain normalization (JS)              [keep as-is]
2. lookup        — apollo_enrich_company                  [keep as-is]
3. harvest_url   — Harvest URL builder (JS)               [keep as-is]
4. harvest       — Harvest /linkedin/company GET          [keep as-is]
5. classify      — deeplineagent (haiku-4.5)              [<USER_PROPERTIES> — rewrite per run]
6. verdict       — flat output row composition (JS)       [<USER_PROPERTIES> — extend output shape]
```

For the **classify** step, rewrite `system` + `prompt` + `jsonSchema` to reflect the user's NL property definitions from `tmp/recipe.yaml`. Keep the "DO NOT call any tools" instruction in the system prompt — without it, deeplineagent occasionally fans out to web search and returns raw SSE-stream as the result instead of structured object output.

For the **verdict** step, extend the `return { ... }` payload to include each property the user asked for. The order of keys in the return statement determines the column order in the flat CSV — match it to the recipe's property declaration order.

For `<USER_PROPERTY_JSON_SCHEMA>`, build a JSON Schema object with `properties` mapping each user-defined property to its type/enum constraint. **`required` MUST list every property name from `properties`** (deeplineagent rejects schemas with partial required arrays — see Deepline gotchas below).

When the user defines properties that need *new* upstream signals (e.g. funding stage, recent news), add a step *between* `harvest` and `classify` — typically another `deeplineagent` step or a provider call. Don't put new logic inside `verdict` — that step's job is composition, not enrichment.

### Deepline gotchas — write the playbook this way

Empirically verified patterns. Any deviation from these tends to produce silent skips or 100%-row failures. Every row below has a real session attached — deviating from one cost real money before the rule was learned.

| Pattern | Right | Wrong | Why |
|---|---|---|---|
| Reading a column's value via *chained* access | `row.inputs.domain_clean` | `row.inputs.result.domain_clean` | run_javascript auto-unwraps `.result` for `row.<col>.<field>` chained access |
| Reading a column's value after *assignment* | `const x = unwrap(row.harvest); x.ok` (where `unwrap = (v) => v && v.result || v`) | `const x = row.harvest; x.ok // undefined!` | The auto-unwrap only triggers on chained property access. Once you assign `row.<col>` to a const, you've captured the raw `{result, __dl}` wrapper — `.result.X` access stops working as expected. The canonical playbook ships with an inline `unwrap()` helper for this. |
| Reading deeplineagent output | `row.classify.object.company_type` | `row.classify.company_type` | deeplineagent wraps as `{text, object, finishReason}`; structured JSON is at `.object` |
| Templating into a URL or prompt | `https://{{inputs.domain_clean}}` | `https://{{inputs.result.domain_clean}}` | `{{alias.field}}` templates auto-unwrap to the result, same as chained run_javascript access |
| `jsonSchema.required` for deeplineagent | List **every** property from `properties` | Partial list of just the "core" required ones | Deepline's deeplineagent integration rejects schemas where required ≠ properties keyset |
| `run_if_js` gates | **Don't use them.** Skip them entirely. | Any expression-form gate like `Boolean(row.X)` | run_if_js semantics are inconsistent across deepline versions; gates that look correct often return false silently and skip every row. For per-run playbooks, you don't need gates. |
| Marking nullable fields in jsonSchema | `"type": ["string", "null"]` | `"type": "string"` + omit from required | deepline wants every property in required; nullable fields use the array type form |
| Apollo company enrichment alias | `"tool": "apollo_enrich_company"` | `"tool": "enrich_company"` | Two providers (apollo + deepline_native) declare the bare alias `enrich_company`. The compiler resolves to apollo *but* throws "operation does not match canonical operation" because of the operationId mismatch. Always be explicit. |
| Reading Apollo's LinkedIn URL | `row.lookup.data.organization.linkedin_url` | `row.lookup.data.output.company.linkedin_url` | Apollo's response shape is `{data: {organization: {...}}}`; only deepline_native uses `output.company`. |
| Reading Harvest's HQ address | `element.locations[]` (array; find entry with `headquarter:true`) | `element.headquarter` | Harvest returns *multiple* locations; the HQ is flagged inside that array. `element.headquarter` is always null in current Harvest API. The canonical playbook iterates `locations[]`. |
| Detecting Harvest rate-limit (the silent killer) | Check `body.error === "code_22"` (or regex `/code_22/`) — body has `{error, status: 429, data: null}` even though the HTTP outer status is 200 OK | Trust HTTP status_code === 200 to mean success | Harvest masks rate limits as 200-OK with the failure reported in the JSON body. The canonical playbook checks for this in the verdict step and surfaces `harvest_rate_limited: true`; `tools/enrich.py` auto-runs `tools/retry_harvest_chunked.py` when it detects ≥2 such rows. |
| Harvest concurrency | Run no more than ~5 concurrent calls per API key | Let Deepline's default 24-concurrent fan-out hit Harvest | Harvest's per-key cap is ~5. Above that, every excess row gets `code_22`. The chunked retry tool batches 5-at-a-time with 2s gaps. |

Use the Edit tool or Write tool to produce `tmp/playbook.jsonc`. Validate parseability with:

```bash
python3 -c "import json, re; raw = open('tmp/playbook.jsonc').read(); data = json.loads(re.sub(r'^\s*//.*$', '', raw, flags=re.MULTILINE)); print(f'OK: {len(data[\"commands\"])} commands')"
```

### 3b. Run

```bash
python tools/enrich.py <user_csv> --playbook tmp/playbook.jsonc --output tmp/enriched.csv
```

The runner streams Deepline's progress; the user sees per-row processing in the Deepline session UI (URL printed mid-run). When complete, `tmp/enriched.csv` lands.

**Auto rate-limit recovery.** `tools/enrich.py` post-processes the enriched CSV by scanning the `harvest` column for `body.error === "code_22"` (Harvest's silent 429). If ≥2 rows hit it, the runner automatically invokes `tools/retry_harvest_chunked.py` with chunk-size 5 and a 2-second delay between chunks — pushing the typical 60–80% Harvest hit rate up to 90+%. The user sees the recovery happen in real time without needing to know about it. Pass `--no-auto-retry` to opt out (e.g. for CI).

Print a quick summary:
- Total rows enriched
- Counts per enum value (e.g. `industry: B2B SaaS=23, FinTech=4, Services=12, ...`)
- Anything notable (acquired counts, large-bucket counts, dead-domain count)
- **`employee_source` breakdown** when Harvest is in the loop — e.g. `harvest_linkedin_exact: 38, agent_linkedin_band_or_exact: 9, none: 3`. This tells the user how many rows got the live-scraped exact integer vs the band fallback. If `HARVEST_API_KEY` was unset, expect every row to be `agent_linkedin_band_or_exact` or `none` — flag this and remind the user the Harvest top-up is the smallest accuracy lever they have.
- **Harvest rate-limit final state** (post-retry): `Harvest 429s recovered: X→0` if auto-retry ran. If any rows are still rate-limited after the retry, that's the user's signal to top up Harvest credits or extend `--delay-sec`.
- Path to enriched CSV (and the auto-emitted flat companion at `tmp/enriched-flat.csv`)
- Deepline session URL (preserve from runner output)

## Phase 4: Grade + report (the close)

Two scripted steps. Both produce markdown artifacts the user reads on screen.

### 4a. Grade against the golden (if one exists)

If `tmp/golden-accounts.csv` exists, run:

```bash
python tools/qa.py
```

The grader auto-detects `EXPECTED_<col>` columns in the golden, joins to `tmp/enriched-flat.csv` by normalized domain, and writes `tmp/qa-report.md`:

- Headline accuracy % (the demo punchline)
- Per-field pass/total breakdown
- Failing rows with expected vs got + grader reasoning (Claude-Haiku-4.5 semantic-grades long-form fields like `reasoning`; everything else is exact-match)

The shipped golden (`tmp/golden-accounts.csv`) has 15 hero rows and `EXPECTED_*` columns matching the canonical 6-property cleanup baseline (`company_name / company_linkedin_url / employee_count / state / country / company_type`). If the user's run-time recipe enriches a different property set, `tools/qa.py` only grades the columns that overlap — call out the gap aloud (*"the golden was authored against the default cleanup baseline; only X of your Y properties have a comparison anchor"*).

If accuracy is below ~90% and there's a recurring failure mode (e.g. `company_type` consistently mislabels payment infrastructure as SaaS when the user's recipe expects FinTech), propose ONE refinement: *"The model is calling Stripe 'SaaS' instead of 'FinTech'. Want me to add 'FinTech' to the `company_type` enum and tighten the rule to 'payment infrastructure → FinTech'? I'll regenerate the playbook and you can re-run on the same input."*

If the user agrees: update the property's NL description in `tmp/recipe.yaml`, regenerate `tmp/playbook.jsonc` (re-copy from `recipes/default-cleanup-template.jsonc` and apply the customizations), re-run from Phase 3, then re-grade. Show the accuracy delta.

### 4b. Render the engagement report (always)

```bash
python tools/report.py --client-name "<the user's company name, or 'your accounts'>"
```

Reads `tmp/enriched-flat.csv` + `tmp/recipe.yaml` + `tmp/qa-report.md` (when present) and writes `tmp/engagement-report.md` — a stakeholder-facing markdown brief with headline + auto-extracted findings + 5 sample rows + next steps. End the session by reading the report file directly; let the markdown speak for itself.

**Don't auto-re-run after a refinement.** Always confirm with the user before triggering a new Deepline run — each run costs real Deepline credits.

## Phase 5: Ship to Deepline workflow (optional)

The validated playbook from Phase 3 + the engagement report from Phase 4 are the local deliverable. Phase 5 promotes the same playbook to a hosted Deepline workflow so the user gets a live DAG view, persistent run history with shareable trace URLs, and a `deepline workflows call` endpoint their CRM/ops can hit on inbound leads.

**Always ask before deploying.** Per `docs/best-practices/deepline-best-practices.md`: *"Don't auto-deploy on every CSV run — workflow inventory pollution is a real cost."* Use the verbatim copy below; if the user says no, stop cleanly.

> Say (verbatim or close to it): *"Recipe is locked, run is graded, report rendered. One last optional step — want me to publish this as a hosted Deepline workflow? You get: a live DAG you can share, persistent run history with trace URLs, and a `deepline workflows call` endpoint your CRM can hit on inbound leads. Takes ~30 seconds and ~5 credits for the deploy + 1-row smoke test. Skip if you're just doing a one-shot batch."*

Branch:

- **Yes**: run the converter + deploy + smoke-test in one step:

  ```bash
  python tools/promote_to_workflow.py \
    --playbook tmp/playbook.compiled.jsonc \
    --smoke-domain stripe.com --smoke-company-name Stripe
  ```

  The script handles all four CSV-to-hosted gotchas (template envelope rewrites, bracket-form lint, `.result` wrap rules, cron refusal — see `docs/best-practices/deepline-best-practices.md` for the spec). Emits `tmp/workflows/<slug>/{apply.json,apply-result.json,smoke-test-payload.json,smoke-test-run.json,convert-warnings.md}` and updates `tmp/workflows/latest-workflow.json` (the pointer downstream tools read).

  After deploy: re-run `python tools/report.py` to append a "Live workflow" section to `tmp/engagement-report.md` with the workflow URL, ID, and smoke-test verdict. Read the live URL aloud — *"that's your hosted workflow; share the URL and your prospect can see the run trace."*

- **No**: print *"Stopping here. The compiled playbook stays at tmp/playbook.jsonc; you can ship later via `/iterate-and-ship-enrichment`."*

**Default smoke-test row.** `--smoke-domain stripe.com --smoke-company-name Stripe` is the bundled default — it's a known-clean account where the verdict is reproducible across runs (employee_count≈15086, country=US, company_type=SaaS). Override only if the user has a specific account they want to demo against.

**Defaults the converter applies.** `--trigger api` (the only sensible choice for a demo deploy — webhook needs CRM-side wiring; cron is rejected because the playbook is row-driven). `--workflow-name` auto-generates `crm_cleanup_<YYYYMMDD>_v<N>` if not supplied.

**When the smoke test fails or the live URL doesn't render the verdict that matches local enrichment.** The most common cause is a CSV-mode-only template that didn't get rewritten — inspect `tmp/workflows/<slug>/convert-warnings.md` for the rewrite trail, then `deepline workflows runs --workflow-id <id> --run-id <id>` for the trace. Fix in the template-rewriter before re-deploying.

**Cleanup.** Test-deploys with `_test_` in the name should be deleted post-demo (`deepline workflows delete --workflow-id <id>`). Workflow inventory pollution is a real cost.

## Critical guidelines

- **Always run setup check first.** Don't skip it even if the user seems impatient.
- **Generate the playbook to `tmp/playbook.jsonc`.** The user's per-run playbook is ephemeral.
- **Always include a `reasoning` field in the user's property schema.** Required for the iteration loop and for visible per-row evidence on camera.
- **Validate the playbook JSON before invoking deepline.** A malformed jsonc fails Deepline's static analyzer with cryptic errors; better to catch parse errors locally first.
- **Don't auto-re-run after a refinement.** Always confirm with the user before triggering a new Deepline run — each run costs real Deepline credits.
- **Output column order should match property declaration order.** The user expects to scan the CSV in the order they listed properties.

## Source artifacts in this repo

- `tmp/sample-accounts.csv` — 50-row synthetic dataset with hero rows (acquired, subsidiary, dead domain, geo mismatches, win row)
- `tmp/golden-accounts.csv` — eval set with `EXPECTED_*` columns per property (rebuilt 2026-05-05 to match the canonical 6-property cleanup baseline)
- `recipes/default-cleanup-template.jsonc` — **the canonical playbook the skill clones from**. 6-step pipeline (inputs → apollo lookup → harvest_url → harvest → classify → verdict) with every gotcha annotated inline.
- `recipes/default-cleanup-recipe.yaml` — YAML companion describing the default 6 properties + diagnostic columns. Read alongside the template above.
- `recipes/default-account-enrichment.yaml` — older teaching reference: what an account-enrichment recipe looks like at the conceptual level, top-down. Less hands-on than the cleanup template above.
- `runner/deepline_runner.py` — Python wrapper around `deepline enrich` (handles credit accounting, session URL capture, error reporting)
- `tools/enrich.py` — CLI you invoke to run a playbook against a CSV (`python tools/enrich.py <csv> --playbook tmp/playbook.jsonc`). Auto-detects Harvest rate-limit and triggers chunked retry.
- `tools/retry_harvest_chunked.py` — chunked Harvest retry (default 5-at-a-time, 2s gaps). Invoked automatically by `tools/enrich.py` when `≥2` rows hit `code_22`.
- `tools/flatten.py` — flat-CSV emitter (one column per output property; readable in spreadsheets/CRM imports).
- `tools/qa.py` — auto-detect-EXPECTED grader: enriched CSV + golden CSV → `tmp/qa-report.md` (Phase 4a). Exact-match for short fields/enums; semantic Claude-Haiku grading for long-form prose.
- `tools/report.py` — stakeholder engagement-report renderer: enriched CSV + recipe + QA + (optional) workflow pointer → `tmp/engagement-report.md` (Phase 4b)
- `tools/promote_to_workflow.py` — converter + apply orchestrator (Phase 5). Handles the four CSV-to-hosted gotchas, calls `deepline workflows apply`, smoke-tests, archives to `tmp/workflows/<slug>/`, updates `tmp/workflows/latest-workflow.json`.
- `tools/install_hubspot.py` — OAuth device-code flow for pulling HubSpot property catalog (schema only, never records — privacy-by-design)
- `examples/acme-saas/` — frozen worked example (fictional client + real well-known accounts): full ICP → recipe → input CSV → expected output → scoring model. Read top-down without running anything.
- `enrichment-functions/` — production-grade reusable building blocks (Latitude-managed prompts, multi-tier waterfalls); reference, not used by this skill's per-run playbooks
- `docs/best-practices/` — Deepline patterns + provider preferences (`deepline-best-practices.md`, `provider-preferences.md`)
- `docs/schemas/` — schema references for scoring models + classification research signals
- `reference/deepline-schema.json` + `reference/tools/*.json` — Deepline tool definitions for advanced playbook authoring

## Pro upgrade paths (mention only if the user asks)

- **For exact LinkedIn employee counts**: already wired in. `tmp/playbook.jsonc` includes a `harvest_call` step that hits the Harvest API directly when `HARVEST_API_KEY` is set in `.env`. See the Phase 1 Harvest nudge above.
- **For deterministic LinkedIn-URL discovery (instead of having the AI agent surface it)**: layer in `enrichment-functions/linkedin_url_verified/` ahead of Harvest — uses Lusha tier-1 (cheap domain → URL + firmographics with AI fuzzy-match verification) and falls back to deeplineagent web research. Closes the gap on the long tail where the agent fails to find a verifiable LinkedIn URL.
- **For prompt iteration to ~100% accuracy**: route through Latitude (see `enrichment-functions/*_via_latitude/` — pro-path Deepline functions with prompt versioning + dataset-driven regression). The full course covers the swap pattern.
- **For production-scale runs at hundreds-of-thousands of rows**: layer in provider waterfalls (Lusha → PDL → Crustdata → Apollo), scoring models calibrated to your ICP, async stakeholder collaboration via Sheets for property scoping, and a manual QA review loop. That's the system Sculpted runs for B2B SaaS revenue teams who want this at production scale — [hire Sculpted](https://sculpted.agency) if you want a hand wiring it up.
