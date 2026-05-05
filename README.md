# Claude Code for CRM Cleanup

The engine Sculpted (https://sculpted.agency) uses to clean and qualify B2B CRM accounts at scale — open-sourced as a giveaway alongside the [full 2-hour video course](https://youtube.com/...).

**Architecture:** Claude Code is the orchestrator. Deepline is the runtime. You describe what you want enriched in natural language; Claude assembles a Deepline playbook with those properties baked in and runs it. No hand-coding playbooks. No fixed schemas — every run is custom to the question you're asking.

**The honest framing:** the tools below get you from CSV → enriched output. The harder part — knowing which properties to enrich, how to define them so the model gets it right, what "good" looks like in QA, and which judgment calls to make as the data surfaces edge cases — is mostly human work. That part doesn't ship in a repo. If you want this done quickly and right at production scale, [hire Sculpted](https://sculpted.agency). If you want to try it yourself first, the engine is below.

## The flow

```bash
claude
> /crm-cleanup
```

Then four phases:

1. **Setup check** (~10s) — Claude verifies your `.env`, deps, Deepline CLI; helps install whatever's missing.
2. **Property definition** (~60s) — you describe in natural language what to enrich. *"Industry, employee count tier, whether they've been acquired, and a one-sentence pitch."* Claude asks one clarifying question per property to pin the definition.
3. **Compile + run** (~30s) — Claude writes a `tmp/playbook.jsonc` with your properties baked into the deeplineagent prompt + jsonSchema, then runs `deepline enrich`. Live Deepline session UI streams progress.
4. **Iterate** (optional) — if `tmp/golden-accounts.csv` is present, diff enriched vs expected, surface misses, propose a definition tweak, regenerate playbook on your signoff.

## Use your real CRM data

The whole point is to run this against YOUR CRM. Two paths:

### HubSpot (one-click — recommended)

```bash
python tools/install_hubspot.py
```

A browser window opens, you OAuth into your HubSpot account, and ~30 seconds later `tmp/hubspot-properties.csv` lands on disk. **No API keys to manage** — Sculpted's hosted app handles tokens + state on the back-end. Use the resulting CSV directly with the `/crm-cleanup` flow.

**What we read from your HubSpot:** property definitions (the schema — what fields exist on contacts and companies) and total record counts. We **never** read or store individual contact or company records.

**What you get:** a CSV of all your HubSpot account properties + a sample of accounts ready to enrich. The install also lets Sculpted know who you are (your email + hub size) so we can follow up if you'd like a hand running this at production scale — that's how we keep the giveaway free.

### Salesforce (or any other CRM) — manual export path

A native Salesforce installer is on the roadmap but not yet shipped. In the meantime:

1. Export your accounts via **Reports → Export → CSV** (Salesforce; or the equivalent in Pipedrive, Close, Outreach, etc.)
2. Save the file as `tmp/your-accounts.csv` with at minimum a `domain` and `company_name` column (extra columns are passed through and ignored)
3. Point `/crm-cleanup` at it — same flow, same enriched output

If you want the native Salesforce install when it ships, [hire Sculpted](https://sculpted.agency) — that's a request we hear often and customers fund the work.

## Setup (Claude does most of this for you)

If you'd rather just run `claude → /crm-cleanup`, the skill handles every step below interactively. Manual setup if you want it:

```bash
git clone https://github.com/jtuwiner99/claude-code-crm-cleanup
cd claude-code-crm-cleanup
pip install -r requirements.txt
cp .env.example .env
# Fill DEEPLINE_API_KEY (free tier covers the smoke test) at https://deepline.ai
# Fill ANTHROPIC_API_KEY at https://console.anthropic.com (deeplineagent uses BYOK)
# (Optional but recommended) Fill HARVEST_API_KEY at https://harvest-api.com/admin/api-keys
#   — enables a live LinkedIn scrape for exact integer employee counts; without
#     it, `numberofemployees` falls back to the band lower-bound the AI agent
#     reads from public search snippets (e.g. "501" floored from "501-1,000").
```

Install the Deepline CLI if you don't have it:
```bash
curl -s 'https://code.deepline.com/api/v2/cli/install' | bash
```

Then in Claude Code:

```bash
claude
> /crm-cleanup
```

The skill walks you through everything else.

## What's in the box

```
claude-code-crm-cleanup/
│
├── README.md                                    ← you are here
├── LICENSE                                      ← MIT
├── .env.example                                 ← required keys (Anthropic + Deepline)
├── requirements.txt                             ← anthropic, pyyaml, requests, python-dotenv
│
├── tools/                                       ← entry-point CLIs you actually run
│   ├── enrich.py                                → invoked by `/crm-cleanup` to run a generated playbook against a CSV
│   └── install_hubspot.py                       → OAuth-installs Sculpted's HubSpot app, drops your property defs into tmp/
│
├── runner/
│   └── deepline_runner.py                       ← thin Python wrapper around `deepline enrich` (credit accounting, session URL capture, error reporting)
│
├── recipes/
│   └── default-account-enrichment.yaml          ← teaching reference: what an account-enrichment recipe looks like, top-down
│
├── tmp/                                         ← sample data + run output land here
│   ├── sample-accounts.csv                      → 50-row synthetic dataset with hero rows embedded (acquired/subsidiary/dead-domain/geo-mismatch)
│   └── golden-accounts.csv                      → 15-row eval set with EXPECTED_* columns for the iteration loop
│
├── .claude/skills/                              ← invokable as /<skill-name> in Claude Code
│   ├── crm-cleanup/                             → headline conversational flow (setup check → property definition → compile + run → iterate)
│   ├── enrichment-functions-catalog/            → reference for the 21-function library (decision tree, provider preferences)
│   ├── contact-cleanup-playbook/                → contact-side spine (find URL → scrape profile → validate identity → job change → score fit)
│   ├── ma-and-corporate-structure-playbook/     → M&A + parent-child + regional/BU divisions; the three-state model (independent / absorbed / inactive)
│   └── iterate-and-ship-enrichment/             → two-phase flow: CSV iteration via `deepline enrich` → promote to hosted Deepline workflow
│
├── docs/                                        ← best practices + JSON schemas for authoring playbooks
│   ├── best-practices/
│   │   ├── deepline-best-practices.md           → waterfall ordering, AI-vs-structured, two-phase gates, four CSV-to-hosted gotchas
│   │   └── provider-preferences.md              → property → tool mapping (Lusha → PDL → Crustdata → Apollo)
│   └── schemas/
│       ├── account-scoring-model.md             → v1 JSON schema for account-tier scoring
│       ├── contact-scoring-model.md             → v1 JSON schema for deterministic contact-fit scoring
│       └── classification-research-signals.md   → schema for hard properties (MSP detection, multi-signal classification)
│
├── reference/                                   ← machine-readable Deepline ground truth
│   ├── deepline-schema.json                     → top-level playbook JSON Schema (validates playbooks)
│   ├── deepline-tools.json                      → provider registry (44 integrations)
│   ├── tools/                                   → per-tool schemas with input/output samples + extract_js paths
│   └── example-playbook.jsonc                   → canonical reference playbook (full account-enrichment pipeline)
│
└── enrichment-functions/                        ← reusable building blocks (21 functions). Reference; the per-run playbook for `/crm-cleanup` doesn't load these — they're for advanced custom playbooks
    │
    │   — domain + identity layer —
    ├── normalize_domain_and_name/               → strip protocol/www, normalize company name (AI fallback)
    ├── verify_domain_alive/                     → 4-variant HTTP check + AI parking-page detector
    ├── linkedin_url_verified/                   → discover + verify a company's LinkedIn URL (Lusha → PDL → Crustdata waterfall)
    ├── company_core_from_linkedin/              → extract firmographics (employees, industry, founded, HQ) from LinkedIn
    ├── company_summary_from_website/            → AI-generated 150-word brief from homepage + LinkedIn description
    ├── extract_hq_address/                      → HQ from `company_core` (deterministic) → AI web-search fallback
    │
    │   — classification layer —
    ├── classify_via_latitude/                   → single-dim classification (e.g. industry, company type, contact seniority)
    ├── classify_multi_dim_via_latitude/         → multi-dim classification in one call (e.g. persona + seniority from one title)
    ├── classify_via_research_agents/            → signal-fanout classification for hard properties (MSP detection, scientific-vs-business)
    ├── research_signal_via_latitude/            → single research-signal extraction; building block for the agents-style classifier above
    │
    │   — scoring layer —
    ├── score_account_via_latitude/              → AI-judged tier scoring against your scoring-model JSON
    ├── score_contact_fit/                       → deterministic contact-fit verdict (still_there + persona + seniority → ideal | acceptable | not_ideal)
    │
    │   — M&A + corporate structure —
    ├── detect_acquisition/                      → M&A event detection + acquirer extraction + DBA/rebrand disambiguation
    ├── acquired_brand_status/                   → for an acquired company: independent / absorbed / inactive
    ├── detect_corporate_structure/              → durable parent-child relationships (independent / parent / subsidiary)
    ├── detect_company_division/                 → regional / BU branches of the SAME legal entity (H&M UK vs H&M Global)
    │
    │   — country + presence —
    ├── country_presence_verified/               → real in-country sellable entity vs marketing-only country domain
    │
    │   — contact layer (preview / experimental) —
    ├── find_contact_linkedin_url/               → contact LinkedIn URL discovery (Prospeo → Apollo waterfall)
    ├── enrich_contact_linkedin_profile/         → full profile scrape via Harvest (work history, education, headline, about)
    ├── validate_contact_identity/               → confirm the LinkedIn profile is actually the on-record contact
    ├── detect_job_change/                       → still_there / moved / unclear (deterministic, AI-free)
    │
    │   — shared —
    ├── recipes/                                 → reference recipe yamls (default contact cleanup, contact job-change loop)
    └── preset_categories/                       → default classification taxonomies (industry, persona, seniority, etc.)
```

The headline path is **`claude → /crm-cleanup`**. The skill handles setup, asks what you want enriched, generates a Deepline playbook tuned to your properties (saved at `tmp/playbook.jsonc`), runs it via `tools/enrich.py`, and lands the output at `tmp/enriched.csv`. Everything in `enrichment-functions/` is reference material — production-grade functions you compose into your own playbooks for advanced runs.

## Skills (`.claude/skills/`)

The five skills the tree above lists, with invocation context:

| Skill | When to invoke |
|---|---|
| `/crm-cleanup` | The headline interactive flow — describe properties in natural language, Claude builds and runs a Deepline playbook. |
| `/enrichment-functions-catalog` | Reference for the function library — when to use which, provider preferences, decision tree, recipe sketches. |
| `/contact-cleanup-playbook` | The contact-side spine: find LinkedIn URL → scrape profile → validate identity → detect job change → classify persona/seniority → score fit. |
| `/ma-and-corporate-structure-playbook` | M&A detection, parent-child relationships, regional/BU divisions. The three-state model (independent / absorbed / inactive) and recipe-composition patterns. |
| `/iterate-and-ship-enrichment` | The two-phase flow — iterate on a CSV sample with `deepline enrich`, then promote to a hosted Deepline workflow. |

## Try it yourself, or hire Sculpted

| Path | What you get | What it costs |
|---|---|---|
| **Try it yourself (this repo)** | Conversational property selection + custom Deepline playbook per run + golden-dataset iteration loop. Enough to run real CRM cleanup at modest scale. | `DEEPLINE_API_KEY` + `ANTHROPIC_API_KEY` (free tiers cover a small demo run). Plus your time on the judgment calls. |
| **Pro — Latitude-managed prompts** | Iterate the prompt against a labeled regression dataset; push to ~100% accuracy with versioned prompts. | `LATITUDE_API_KEY` *(the full course covers the swap pattern)* |
| **Hire Sculpted** | Someone who's done this dozens of times asks the right scoping questions, organizes your context cleanly, picks the property definitions that survive QA, and runs the manual review loop that catches the 5-10% of edge cases the model gets wrong. Idea → scope doc → implemented + QA'd much faster than a first-time-through. | [sculpted.agency](https://sculpted.agency) |

The honest read: **the point-and-click work of building Clay tables and managing Deepline pipelines has gotten dramatically easier — these tools are real and you can use them.** What hasn't gotten easier is the human judgment: picking the right property definitions, knowing what good vs bad output looks like in QA, organizing a stakeholder's context cleanly, and making the call on edge cases the model surfaces. That's what Sculpted does. Hire us if you want it done fast.

## Hero rows in the bundled CSV

The synthetic dataset is deliberately shaped to surface judgment beats on camera. Pre-validated rows:

| Domain | Expected verdict |
|---|---|
| `slack.com` | `is_acquired=true`, `acquirer_name="Salesforce"`, `routing_flag="reroute_to_acquirer"` |
| `mailchimp.com` | `is_acquired=true`, `acquirer_name="Intuit"`, `routing_flag="reroute_to_acquirer"` |
| `clearbit.com` | `is_acquired=true`, `acquirer_name="HubSpot"`, `routing_flag="reroute_to_acquirer"` |
| `segment.com` | `is_acquired=true`, `acquirer_name="Twilio"` |
| `chorus.ai` | `is_acquired=true`, `acquirer_name="ZoomInfo"` |
| `braintree.com` | `is_acquired=true`, `acquirer_name="PayPal"` |
| `linkedin.com` | `relationship_type="subsidiary"`, `parent_name="Microsoft"`, `routing_flag="verify_parent_routing"` |
| `github.com` | `relationship_type="subsidiary"`, `parent_name="Microsoft"` |
| `spotify.com` | `verified_country_code="SE"` |
| `sap.com` | `verified_country_code="DE"` |
| `right-networks-totally-not-real-domain-12345.com` | `is_live=false`, `routing_flag="drop"` |
| Most others | Clean records, `routing_flag="keep"` |

If any of these don't fire as expected on your run, that's the AI being conservative — re-run, or check the `ai_reasoning` column for what the model saw.

## Use your own CSV

Two columns required: `domain` and `company_name` (extra columns pass through). Three ways to point `/crm-cleanup` at your own data:

1. **HubSpot users** — run `python tools/install_hubspot.py` (above); the resulting `tmp/hubspot-properties.csv` is what the skill uses by default.
2. **Salesforce / other CRM** — export to CSV, save it anywhere on disk, and tell `/crm-cleanup` the path when it asks.
3. **Quick subset pilot** — once `/crm-cleanup` has generated a playbook at `tmp/playbook.jsonc`, you can re-run any subset directly:
   ```bash
   python tools/enrich.py path/to/your-accounts.csv --playbook tmp/playbook.jsonc --rows 0:10
   ```

## What this repo is NOT

- **Not the human judgment work.** The hardest part of CRM cleanup isn't the tooling — it's knowing which properties are worth enriching, defining them so the model gets it right, picking your scoring rules, knowing what good output looks like, and catching the edge cases AI surfaces during QA. None of that ships in a repo. The full course (and a Sculpted engagement) covers that part. This repo is the engine; the judgment is the work.
- **Not the operator system Sculpted runs for clients.** Sculpted's full delivery includes a Google Sheets-based collaboration surface for property scoping, an async stakeholder review loop, manual QA passes that catch the 5-10% of rows the model gets wrong, and provider waterfalls (Lusha + PDL + Crustdata + Apollo) tuned per client. That layer isn't in this repo on purpose — it's how Sculpted moves faster than someone going through this themselves for the first time.
- **Not contact-side cleanup as a default.** The skill's default flow is account-side only. Contact-side functions (`find_contact_linkedin_url`, `enrich_contact_linkedin_profile`, `validate_contact_identity`, `detect_job_change`, `score_contact_fit`) ship in `enrichment-functions/` as reference. Contact cleanup at production scale is harder than account cleanup and benefits more from Sculpted's QA loop than account does.
- **Not free at scale.** A 50-row demo run is cheap (one AI call per row). For 50K+ row jobs, the production pipeline runs HTTP + cheap provider lookups first and only invokes AI on rows that warrant it. Use this engine to learn the shape; hire Sculpted when you want to run at production scale.

## Want the full course?

The 2-hour walkthrough — `CLAUDE CODE FOR CRM CLEANUP` — covers what this repo doesn't:

- **The flagship demo** of this repo, narrated end-to-end
- **The A-Z of how Sculpted runs an engagement for clients** — from kickoff to delivery, including the Google Sheets-based property-scoping + async-stakeholder-review surface that this repo doesn't ship
- Writing your own recipes from scratch
- Adding Latitude for prompt iteration toward ~100% accuracy
- The manual QA loop — what to look for, where models reliably fail, how to set up a review pass
- Wiring HubSpot / Salesforce write-back

Watch the course to see how the engine you cloned plus a real engagement workflow actually runs at scale.

[Watch on YouTube →](https://youtube.com/...)

## Hiring Sculpted

If you want this engine wired up to your CRM with your ICP, your scoring rules, and a managed QA loop — that's what Sculpted does for B2B SaaS companies. [sculpted.agency](https://sculpted.agency)

## License

The code is open. The Sculpted name and brand are not. See LICENSE.
