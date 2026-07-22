---
name: crm-report-card
description: Scan a CRM CSV export for duplicates, missing critical fields, contradictions, junk records, stale data, and dead domains, then render a shareable report card that reveals scope and severity without delivering the fix. Use when someone asks "how messy is my CRM", wants a free CRM audit/report card, or wants a lead-gen teaser tool for a data-quality offer.
---

# CRM Report Card

## 1. What this is, and why

This is a Tier 0 lead-magnet tool. It takes a CRM CSV export and produces a
report card: an overall letter grade plus six deterministic FACTs (duplicates,
missing critical fields, contradictions, junk records, stale records, dead
domains) and one clearly-labeled, unverified ESTIMATE (percent likely
"qualified" against the user's ICP).

The point is to reveal scope and severity, and demonstrate a verified taste of
what a real fix looks like. It is **not** a cleanup tool. It never writes back
to a CRM, never deletes or merges records, and never claims to have fixed
anything. Every number it shows is either a FACT (computed deterministically
from the data, reproducible, no model involved) or an ESTIMATE (a single-pass
model guess, explicitly marked NOT VERIFIED). The report card ends with a
locked teaser section that names what a real engagement would unlock next,
and a CTA to talk to a human. Nothing past the report card is delivered here.

Everything runs locally on stdlib Python. No API keys, no network calls except
the optional domain-liveness HEAD pings (which only touch domains that are
already in the user's own CSV). Rows never leave the machine running this
skill.

## 2. Intake: ask three questions, then write run-config.json

Before running anything, ask the user:

1. **Who is your ICP, in plain English?** (for example: "US-based B2B SaaS
   companies, 50 to 500 employees, using a modern tech stack"). This becomes
   `icp_nl` and is also what step 4's AI baseline scores against.
2. **Which properties actually matter to you?** In particular: which fields
   would you consider critical, such that a blank value on that field means
   the record is basically useless to you? This becomes `critical_properties`
   (a list of canonical roles: `company_name`, `domain`, `contact_name`,
   `email`, `company_size`, `last_activity`).
3. **Name 3 to 5 of your favorite/best customers.** These are not used by the
   deterministic checks, but they anchor the AI baseline step and the
   locked-teaser copy in "customers who look like X" terms. Store them as
   `favorite_customers`.

Then load the user's CSV headers, run the auto field-mapper
(`crm_report_card.field_mapping.auto_map`), and **show the user the detected
mapping so they can confirm or correct it** before you write it down. Auto-map
matches common header synonyms (for example `Website`/`URL`/`Domain` all map
to the `domain` role); always confirm rather than assume, especially for
`company_size` and `last_activity`, which have looser synonym matching.

Write the confirmed answers to `run-config.json` in the working directory:

```json
{
  "icp_nl": "US-based B2B SaaS companies, 50-500 employees, using a modern tech stack",
  "critical_properties": ["email", "company_size"],
  "field_mapping": {
    "domain": "Website",
    "last_activity": "Last Activity"
  },
  "favorite_customers": ["Acme Robotics", "Brightgate Software", "Pinebrook Cloud"],
  "contact_email": "you@yourcompany.com",
  "booking_url": "https://cal.example/you"
}
```

Notes on the schema:
- `field_mapping` only needs entries for roles the auto-mapper got wrong or
  could not detect; anything already auto-mapped correctly can be omitted.
- `contact_email` and `booking_url` are the user's own contact details, used
  in the rendered report card's CTA and mailto summary. Ask for these too if
  not already known.

## 3. Run the scan (deterministic, no model)

The package uses relative imports, so invoke it as a module with the package
on `PYTHONPATH`, from the repo root:

```bash
PYTHONPATH=scripts python3 -m crm_report_card.cli scan \
  --config run-config.json \
  --csv <path-to-crm-export.csv> \
  --out metrics.json
```

This prints the terminal reveal (see step 6) and writes `metrics.json`
containing `counts`, `facts` (one block per check, each with a computed rate
and a letter grade), `overall_grade`, a `decay` projection, and an empty
`ai_baseline: null` placeholder.

Domain-liveness checks make a real HTTPS HEAD request to each unique domain in
the CSV, so this step touches the network for that one purpose only. If you
need a fully offline run (for example against a fixture with invented
domains), set `CRM_RC_SKIP_LIVENESS=1` before the command; every domain will
be reported dead rather than pinged.

## 4. AI baseline: read a sample, score it, patch metrics.json

The scan never calls a model. This step is where you, the assistant, add the
one ESTIMATE line. It is a single pass over a small sample and must never be
presented as a measurement.

1. Read a sample of the loaded CSV (roughly 20 to 50 rows).
2. Follow `assets/icp-scorer-prompt.md` exactly: derive rules from `icp_nl`,
   score the sample, and produce `{qualified_estimate, reasons, sample_size}`.
3. Patch `metrics.json`'s `ai_baseline` using the validator, so the schema and
   the forced `verified: false` are guaranteed correct:

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

Replace the `qualified_estimate`/`reasons`/`sample_size` values with what you
actually derived in steps 1 to 2.

## 5. Render the report card

```bash
PYTHONPATH=scripts python3 -m crm_report_card.cli render \
  --metrics metrics.json \
  --config run-config.json \
  --out crm-report-card.html
```

This writes a single self-contained HTML file (inline CSS, no external
requests) with the overall grade, the six FACT rows, the ESTIMATE row (or "not
run" if step 4 was skipped), the locked teaser rows, and a `mailto:` CTA
pre-filled with the summary plus a booking-link button.

## 6. Show the reveal, open the HTML, explain FACT vs ESTIMATE

Both `scan` and `render` print the same terminal reveal to stdout, for example:

```
Scanning 40 records...

  [FACT] Duplicates ........ 15.0%  (D)
  [FACT] Missing critical .. 5.0%  (C)
  [FACT] Contradictions .... 10.0%  (D)
  [FACT] Junk .............. 22.5%  (F)
  [FACT] Stale ............. 15.0%  (D)
  [FACT] Dead domains ...... 69.7%  (bot-blocked: 0)  (F)
  [ESTIMATE: NOT VERIFIED] Qualified ~ 35%  (single-pass guess, accuracy unmeasured)

OVERALL GRADE: D
```

Walk the user through it live, then open `crm-report-card.html` in a browser
(or attach it) so they can see the same numbers laid out with the locked
teaser rows below the fold. Explain the distinction plainly:

- **FACT** rows are deterministic: same CSV in, same number out, every time,
  no model involved. They are the trustworthy part of this report.
- **ESTIMATE** rows are a single-pass model guess, always labeled "NOT
  VERIFIED", with the `reasons` spelling out exactly why it should not be
  trusted as a measurement (no evidence grounding, no test bench, no
  production QA).
- The **locked rows** (segment by each critical property, custom fit scoring,
  market-by-segment) are named but not delivered here. They describe what a
  real engagement adds on top of this scan; they are the reason the CTA exists.

## 7. Tier 1 upgrade pointer (stub)

This Tier 0 report card never verifies its ESTIMATE row against real evidence.
Turning that single-pass guess into a verified, defensible number needs a
verified sample: enrichment against a live provider (a Deepline key) plus a
locked test bench and a human QA pass on a sample of records, so the
"qualified %" line stops being a guess and becomes a measured, sourced number.
That full Tier 1 build (verified sample, evidence-linked scoring, production
QA loop) ships in a separate plan; this skill stops at the report card.
