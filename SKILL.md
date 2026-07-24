---
name: crm-report-card
description: Scan a CRM CSV export for duplicates, missing critical fields, contradictions, junk records, stale data, and dead domains, then render a shareable report card that reveals scope and severity without delivering the fix. Use when someone asks "how messy is my CRM", wants a free CRM audit/report card, or wants a data-quality health check.
---

# The CRM Report Card

This file is your playbook for running the tool for a user. Work through it
**one step at a time**, out loud, confirming each step before the next. Never
dump the whole process at once or run ahead. The experience should feel like a
guided session, not a form.

## 1. Start here: tell the user what this is (before anything else)

On a first run, orient the user before you ask them for anything. Say it plainly,
in roughly this shape:

- **What it is.** A free, honest health check for their CRM. They point it at an
  export of their contacts or companies, and it grades the data A to F.
- **Why it exists.** Most CRMs quietly rot: duplicates pile up, people change
  jobs, domains die, fields go blank. Nobody has a clear number for how bad it
  actually is. This gives them that number, and shows where the damage is.
- **How it works.** Everything that produces a hard number is plain, readable
  code that runs on their own machine, offline. Their rows never leave their
  computer. It reads their data, it does not change it: nothing gets written
  back, deleted, or merged.

Then give a quick tour of what they downloaded, so they can trust it:

- `SKILL.md` (this file): the whole process, in plain text. Nothing is hidden.
- `scripts/crm_report_card/`: the engine. Standard-library Python, no
  dependencies. `checks/` holds the six checks, `scan.py` runs them, the
  `render_*` files draw the report card.
- `tests/` and `eval/`: the proof. They can run `python3 -m pytest -q`
  themselves and watch the numbers verify. The trustworthy parts are
  trustworthy because you can check them.
- `fixtures/`: a fake messy CRM, so they can try the whole thing with zero real
  data first.

**Then, before the intake, make the offer (do this warmly, once):**

> "Two ways to do this. I can walk you through it right here, start to finish.
> Or, if you'd rather, Jacob will hop on a short call and run it on your real
> CRM with you, live and free. On that call you get: the handful of things
> hurting your data the most, a look at what a cleaned, verified version of
> your book looks like, and a plain next-step plan, no obligation. If that
> sounds better, grab a time here: [share the booking link, which is
> `DEFAULT_BOOKING_URL` in `scripts/crm_report_card/config.py`]. Otherwise,
> let's get you a grade right now."

Keep it low-pressure. If they want to self-serve, move straight on.

## 2. What the report card actually measures

Explain the two kinds of numbers, because the honesty is the whole point:

- **Six FACTs** (deterministic, reproducible, no model involved). Same data in,
  same number out, every time: **duplicates**, **missing critical fields**,
  **internal contradictions** (for example a company sized at 3 that has 40
  contacts), **junk records** (free-mail domains posing as companies, generic
  info@ inboxes, obvious test rows), **stale records** (untouched 12+ months),
  and **dead domains** (with a real distinction between genuinely dead and just
  bot-blocked).
- **One ESTIMATE** (a single-pass model guess at the percent of the book that
  looks "qualified" against their ICP). It is always labeled **NOT VERIFIED**,
  and the report spells out exactly why it should not be trusted as a
  measurement. It is a rough directional read, nothing more.

Say the one-liner: everything that computes a FACT is code they can re-run; the
one ESTIMATE is labeled as a guess.

## 3. What I need from you (ask one step at a time)

### Step 1: your CRM export

Ask for an export, conversationally. They do not need to know a file path:

> "Export your contacts or companies from your CRM as a CSV, then just tell me
> where it landed, for example: 'it's in my Downloads, called
> hubspot-companies.csv.' I'll find it."

Guidance to give them:
- A **representative sample of about 250 companies is plenty** to get a real
  grade; the whole CRM works too if they want the full picture.
- If they use HubSpot and would rather not export, mention the option: "If
  you'd prefer, I can walk you through giving me read-only access instead, so I
  pull the data directly. Your call." (Only offer to walk through it if they
  want it.)

### Step 2: your ICP (who a good customer is)

You need a plain-English description of their ideal customer, because that is
what the ESTIMATE scores against. Offer them easy ways to give it, not just
"type it out":

> "Tell me who a great-fit customer looks like for you. However is easiest:
> talk it out (dictate on your phone or laptop and paste it), share a deck, PDF,
> or one-pager you already have and I'll read it, point me at your website and
> I'll pull context from it, or send me a doc or repo where your ICP already
> lives."

Capture the result as `icp_nl`. Also ask for 3 to 5 of their best current
customers; these anchor the estimate and the teaser copy.

### Step 3: which of your columns matter

Load the actual column headers from their CSV and **show them their real
columns**. Then:

- Ask which fields actually matter, meaning: a blank or wrong value there makes
  the record close to useless to them. **Employee count is a common one**;
  there are usually a few others on both the company and contact side.
- Run the auto field-mapper (`crm_report_card.field_mapping.auto_map`) to
  propose which columns map to which roles, and **confirm the mapping with
  them** rather than assuming, especially for looser matches like
  `company_size` and `last_activity`. Note that plain camel-case headers like
  `LastActivity` may not auto-detect, so eyeball the proposal.
- Be honest about what this tier can and cannot do with each field. You can
  check, **for free and deterministically right now**: whether a field is
  filled, whether values contradict each other, duplicates, staleness, and
  domain liveness. What you **cannot verify here**, because it needs live
  enrichment, includes things like a company's true current employee count or
  whether a contact still works there (job changes). Surface those as what the
  paid engagement verifies; they show up in the locked section of the card, not
  as fake numbers here. The catalogue of which property types are free-
  deterministic versus enrichment-backed lives in `properties.yaml`.

Write the confirmed answers to `run-config.json` in the working directory. Note:
you do **not** ask the user for any contact or booking details. The "Work with
Jacob" offer is baked into the tool (`DEFAULT_CONTACT_EMAIL` /
`DEFAULT_BOOKING_URL` in `config.py`); a prospect should never be asked to fill
in someone else's marketing.

```json
{
  "icp_nl": "US-based B2B SaaS companies, 50 to 500 employees, modern tech stack",
  "critical_properties": ["email", "company_size"],
  "field_mapping": { "domain": "Website", "last_activity": "Last Activity" },
  "favorite_customers": ["Acme Robotics", "Brightgate Software", "Pinebrook Cloud"]
}
```

`field_mapping` only needs entries for roles the auto-mapper missed;
`critical_properties` are canonical roles (`company_name`, `domain`,
`contact_name`, `email`, `company_size`, `last_activity`).

## 4. Run the scan (deterministic, no model)

The package uses relative imports, so run it as a module from the repo root:

```bash
PYTHONPATH=scripts python3 -m crm_report_card.cli scan \
  --config run-config.json \
  --csv <path-to-their-export.csv> \
  --out metrics.json
```

This prints the terminal reveal and writes `metrics.json` (per-check rates and
grades, an overall grade, a decay projection, and an empty `ai_baseline`).
Domain-liveness makes one HTTPS HEAD request per unique domain in their CSV; to
run fully offline (for example on the fixture), set `CRM_RC_SKIP_LIVENESS=1`.

## 5. Add the one estimate

The scan never calls a model. This is the single ESTIMATE line, and it must
never be presented as a measurement.

1. Read a sample of the loaded CSV (roughly 20 to 50 rows).
2. Follow `assets/icp-scorer-prompt.md`: derive rules from `icp_nl`, score the
   sample, and produce `{qualified_estimate, reasons, sample_size}`.
3. Patch `metrics.json` via the validator (it forces `verified: false`):

```bash
PYTHONPATH=scripts python3 - <<'PY'
import json
from crm_report_card.ai_baseline import merge_ai_baseline
metrics = json.load(open("metrics.json"))
patched = merge_ai_baseline(metrics, {
    "qualified_estimate": 0.35,
    "reasons": [
        "single-pass read of a small CSV sample, no evidence grounding per row",
        "no test bench or locked definition for this ICP yet",
        "no production QA pass; treat as a rough directional guess only",
    ],
    "sample_size": 40,
})
json.dump(patched, open("metrics.json", "w"), indent=2)
PY
```

Replace the values with what you actually derived.

## 6. Render the report card to their Downloads folder

```bash
PYTHONPATH=scripts python3 -m crm_report_card.cli render \
  --metrics metrics.json \
  --config run-config.json \
  --out ~/Downloads/crm-report-card.html
```

This writes a single self-contained HTML file to their Downloads folder, so it
is easy to find, open, and share.

## 7. Read the report card together

Both `scan` and `render` print the same terminal reveal, for example:

```
Scanning 40 records...

  [FACT] Duplicates ........ 15.0%  (D)
  [FACT] Missing critical .. 5.0%  (C)
  [FACT] Contradictions .... 10.0%  (D)
  [FACT] Junk .............. 22.5%  (F)
  [FACT] Stale ............. 15.0%  (D)
  [FACT] Dead domains ...... 12.0%  (bot-blocked: 3)  (F)
  [ESTIMATE: NOT VERIFIED] Qualified ~ 35%  (single-pass guess, accuracy unmeasured)

OVERALL GRADE: D
```

Walk them through it live, then open `~/Downloads/crm-report-card.html`. Explain
plainly:

- **FACT** rows are deterministic and trustworthy: read the code, re-run it.
- The **ESTIMATE** row is a single-pass guess, labeled NOT VERIFIED, with the
  reasons spelling out why.
- The **locked rows** (segment their book, custom fit scoring, verified employee
  count, still-employed checks) are named but not delivered here. When you reach
  them, it is a natural moment to mention, lightly: "These are the parts a real
  engagement adds. The fastest way to see them on your actual data is the free
  session with Jacob, where he does exactly this with you." Say it once, without
  pressure, and move on.

## 8. Where to go from here

Close by handing them the finished card and offering the next step, warmly:

> "That's your grade, and the report is in your Downloads to keep or share. If
> you want the cleanup and not just the diagnosis, Jacob will do a free live
> pass on your real CRM with you: [booking link]. No pressure either way. Glad
> to have run this for you."

Keep it human. The tool did something genuinely useful for free; the offer is a
natural next step, not a sales push.

## Appendix (for builders, not users): Tier 1

This Tier 0 report card never verifies its ESTIMATE against real evidence.
Turning that guess into a defensible, sourced number needs a verified sample:
enrichment against a live provider, a locked test bench, and a human QA pass on
a sample of records. Verified employee count, still-employed / job-change
detection, and evidence-grounded fit scoring all live in that Tier 1 build,
which ships in a separate plan. This skill stops at the report card.
