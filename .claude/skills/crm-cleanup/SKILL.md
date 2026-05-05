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
3. **Compile + run** — generate `tmp/playbook.jsonc` with the user's properties baked in, then `deepline enrich` it.
4. **Iteration (optional)** — if `tmp/golden-accounts.csv` exists, diff vs expected, suggest definition refinements, regenerate playbook on the user's signoff.

User does about 60 seconds of typing across phases 1+2; phase 3 is the spectacle (Deepline session UI streams progress in parallel); phase 4 is the close.

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

Generate `tmp/playbook.jsonc` from a template. Use this exact structure (the patterns below are empirically validated; deviating from them hits Deepline-side gotchas listed in section "Deepline gotchas" further down):

```jsonc
{
  "version": 1,
  "commands": [
    {
      "alias": "inputs",
      "tool": "run_javascript",
      "operation": "run_javascript",
      "payload": {
        "code": "const rawDomain = row['domain'] || row['Domain'] || row['Company Domain Name'] || ''; const domain_clean = String(rawDomain).toLowerCase().replace(/^https?:\\/\\//, '').replace(/^www\\./, '').split('/')[0].split('?')[0].trim() || null; const company_name = row['company_name'] || row['Company Name'] || null; return { domain_clean: domain_clean, company_name_clean: company_name };"
      }
    },
    {
      "alias": "research",
      "tool": "deeplineagent",
      "operation": "deeplineagent",
      "payload": {
        "model": "anthropic/claude-haiku-4.5",
        "system": "<USER_PROPERTY_SYSTEM_PROMPT>",
        "prompt": "Research this company:\n\nDomain: {{inputs.domain_clean}}\nCompany name: {{inputs.company_name_clean}}\n\nReturn structured findings only.",
        "jsonSchema": "<USER_PROPERTY_JSON_SCHEMA>"
      }
    },
    {
      "alias": "verdict",
      "tool": "run_javascript",
      "operation": "run_javascript",
      "payload": {
        "code": "<COMPOSE_OUTPUT_FROM_INPUTS_AND_RESEARCH>"
      }
    }
  ]
}
```

For `<USER_PROPERTY_SYSTEM_PROMPT>`, build a string like:

```
You are a precise CRM data-enrichment researcher. Given a company name and domain, research the company on the public web and return the requested properties as structured JSON.

Be conservative — when uncertain, prefer the less-disruptive verdict (e.g. is_acquired=false on weak evidence). Cite evidence in the reasoning field.

PROPERTIES TO RETURN:

<inline each property name + description from the recipe>

Return ONLY valid JSON. No markdown fences. No commentary outside the JSON.
```

For `<USER_PROPERTY_JSON_SCHEMA>`, build a JSON Schema object with `properties` mapping each user-defined property to its type/enum constraint. **`required` MUST list every property name from `properties`** (deeplineagent rejects schemas with partial required arrays — see Deepline gotchas below).

For `<COMPOSE_OUTPUT_FROM_INPUTS_AND_RESEARCH>`, JS code that pulls `row.inputs.domain_clean`, `row.inputs.company_name_clean`, fields from `row.research.object.*`, and emits one flat row. (Note: deeplineagent wraps its output as `{text, object, finishReason}` — read your structured fields from `.object`, not from the top of `row.research`.)

### Deepline gotchas — write the playbook this way

Empirically verified patterns. Any deviation from these tends to produce silent skips or 100%-row failures.

| Pattern | Right | Wrong | Why |
|---|---|---|---|
| Reading a column's value in run_javascript code | `row.inputs.domain_clean` | `row.inputs.result.domain_clean` | run_javascript auto-unwraps `.result` for `row.<col>` access |
| Reading deeplineagent output | `row.research.object.is_acquired` | `row.research.is_acquired` | deeplineagent wraps as `{text, object, finishReason}`; structured JSON is at `.object` |
| Templating into a URL or prompt | `https://{{inputs.domain_clean}}` | `https://{{inputs.result.domain_clean}}` | `{{alias.field}}` templates auto-unwrap to the result, same as run_javascript |
| `jsonSchema.required` for deeplineagent | List **every** property from `properties` | Partial list of just the "core" required ones | Deepline's deeplineagent integration rejects schemas where required ≠ properties keyset |
| `run_if_js` gates | **Don't use them.** Skip them entirely. | Any expression-form gate like `Boolean(row.X)` | run_if_js semantics are inconsistent across deepline versions; gates that look correct often return false silently and skip every row. For per-run playbooks, you don't need gates. |
| Marking nullable fields in jsonSchema | `"type": ["string", "null"]` | `"type": "string"` + omit from required | deepline wants every property in required; nullable fields use the array type form |

Use the Edit tool or Write tool to produce `tmp/playbook.jsonc`. Validate parseability with:

```bash
python3 -c "import json, re; raw = open('tmp/playbook.jsonc').read(); data = json.loads(re.sub(r'^\s*//.*$', '', raw, flags=re.MULTILINE)); print(f'OK: {len(data[\"commands\"])} commands')"
```

### 3b. Run

```bash
python tools/enrich.py <user_csv> --playbook tmp/playbook.jsonc --output tmp/enriched.csv
```

The runner streams Deepline's progress; the user sees per-row processing in the Deepline session UI (URL printed mid-run). When complete, `tmp/enriched.csv` lands.

Print a quick summary:
- Total rows enriched
- Counts per enum value (e.g. `industry: B2B SaaS=23, FinTech=4, Services=12, ...`)
- Anything notable (acquired counts, large-bucket counts, dead-domain count)
- **`employee_source` breakdown** when Harvest is in the loop — e.g. `harvest_linkedin_exact: 38, agent_linkedin_band_or_exact: 9, none: 3`. This tells the user how many rows got the live-scraped exact integer vs the band fallback. If `HARVEST_API_KEY` was unset, expect every row to be `agent_linkedin_band_or_exact` or `none` — flag this and remind the user the Harvest top-up is the smallest accuracy lever they have.
- Path to enriched CSV (and the auto-emitted flat companion at `tmp/enriched-flat.csv`)
- Deepline session URL (preserve from runner output)

## Phase 4: Iteration against golden dataset (optional)

If `tmp/golden-accounts.csv` exists, this dataset has expected values per property. Compare enriched output against expected:

```python
# Pseudocode — Claude executes this directly via Bash + Read
import csv
golden = {row['domain']: row for row in csv.DictReader(open('tmp/golden-accounts.csv'))}
enriched = {row['domain_clean']: row for row in csv.DictReader(open('tmp/enriched.csv'))}

for prop in ['industry', 'employee_count_tier', 'is_acquired', ...]:
    correct = sum(1 for d in golden if golden[d][f'EXPECTED_{prop}'] == enriched[d][prop])
    print(f"  {prop}: {correct}/{len(golden)} ({correct/len(golden)*100:.0f}%)")

# Surface mismatches
for d, exp in golden.items():
    for prop in [...]:
        if exp[f'EXPECTED_{prop}'] != enriched[d][prop]:
            print(f"  {d}: expected {prop}={exp[f'EXPECTED_{prop}']}, got {enriched[d][prop]}")
            print(f"      reasoning: {enriched[d]['reasoning']}")
```

After surfacing mismatches, propose ONE refinement: "The model is reading `slack.com` as 'Services' instead of 'B2B SaaS'. Want me to tighten the `industry` definition to include 'collaboration software' as a B2B SaaS signal? I'll regenerate the playbook and you can re-run on the same input."

If the user agrees: update the property's NL description in `tmp/recipe.yaml`, regenerate `tmp/playbook.jsonc`, re-run.

This is the iteration loop the demo lands on. Keep it tight — don't lecture about prompt engineering, just show one tweak.

## Critical guidelines

- **Always run setup check first.** Don't skip it even if the user seems impatient.
- **Generate the playbook to `tmp/playbook.jsonc`.** The user's per-run playbook is ephemeral.
- **Always include a `reasoning` field in the user's property schema.** Required for the iteration loop and for visible per-row evidence on camera.
- **Validate the playbook JSON before invoking deepline.** A malformed jsonc fails Deepline's static analyzer with cryptic errors; better to catch parse errors locally first.
- **Don't auto-re-run after a refinement.** Always confirm with the user before triggering a new Deepline run — each run costs real Deepline credits.
- **Output column order should match property declaration order.** The user expects to scan the CSV in the order they listed properties.

## Source artifacts in this repo

- `tmp/sample-accounts.csv` — 50-row synthetic dataset with hero rows (acquired, subsidiary, dead domain, geo mismatches, win row)
- `tmp/golden-accounts.csv` — eval set with EXPECTED_* columns per property (when added)
- `recipes/default-account-enrichment.yaml` — teaching reference: what an account-enrichment recipe looks like, top-down
- `runner/deepline_runner.py` — Python wrapper around `deepline enrich` (handles credit accounting, session URL capture, error reporting)
- `tools/enrich.py` — CLI you invoke to run a playbook against a CSV (`python tools/enrich.py <csv> --playbook tmp/playbook.jsonc`)
- `tools/install_hubspot.py` — OAuth device-code flow for pulling real HubSpot property definitions
- `enrichment-functions/` — production-grade reusable building blocks (Latitude-managed prompts, multi-tier waterfalls); reference, not used by this skill's per-run playbooks
- `docs/best-practices/` — Deepline patterns + provider preferences (`deepline-best-practices.md`, `provider-preferences.md`)
- `docs/schemas/` — schema references for scoring models + classification research signals
- `reference/deepline-schema.json` + `reference/tools/*.json` — Deepline tool definitions for advanced playbook authoring

## Pro upgrade paths (mention only if the user asks)

- **For exact LinkedIn employee counts**: already wired in. `tmp/playbook.jsonc` includes a `harvest_call` step that hits the Harvest API directly when `HARVEST_API_KEY` is set in `.env`. See the Phase 1 Harvest nudge above.
- **For deterministic LinkedIn-URL discovery (instead of having the AI agent surface it)**: layer in `enrichment-functions/linkedin_url_verified/` ahead of Harvest — uses Lusha tier-1 (cheap domain → URL + firmographics with AI fuzzy-match verification) and falls back to deeplineagent web research. Closes the gap on the long tail where the agent fails to find a verifiable LinkedIn URL.
- **For prompt iteration to ~100% accuracy**: route through Latitude (see `enrichment-functions/*_via_latitude/` — pro-path Deepline functions with prompt versioning + dataset-driven regression). The full course covers the swap pattern.
- **For production-scale runs at hundreds-of-thousands of rows**: layer in provider waterfalls (Lusha → PDL → Crustdata → Apollo), scoring models calibrated to your ICP, async stakeholder collaboration via Sheets for property scoping, and a manual QA review loop. That's the system Sculpted runs for B2B SaaS revenue teams who want this at production scale — [hire Sculpted](https://sculpted.agency) if you want a hand wiring it up.
