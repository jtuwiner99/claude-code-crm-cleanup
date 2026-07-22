# CRM Report Card

A Tier 0 CRM data-quality audit. Point it at a CRM CSV export and it produces
a report card: an overall letter grade, six deterministic FACTs (duplicates,
missing critical fields, contradictions, junk records, stale records, dead
domains), and one clearly-labeled, unverified ESTIMATE (percent likely
"qualified" against a plain-English ICP). It reveals the scope and severity of
a messy CRM and shows a verified taste of what a real fix looks like. It never
writes back to a CRM and never claims to have fixed anything.

## Install

This ships as a Claude Code skill. Copy it into your skills directory:

```bash
cp -r crm-report-card ~/.claude/skills/crm-report-card
```

(Copy this repo's contents into a `crm-report-card/` folder first if you are
working from a checkout rather than a packaged skill directory.)

## Quickstart against the bundled fixture

Run everything from the repo root. The package uses relative imports, so
invoke it as a module with `scripts` on `PYTHONPATH`:

```bash
PYTHONPATH=scripts python3 -m crm_report_card.cli scan \
  --config run-config.json \
  --csv fixtures/messy-crm-sample.csv \
  --out metrics.json

PYTHONPATH=scripts python3 -m crm_report_card.cli render \
  --metrics metrics.json \
  --config run-config.json \
  --out crm-report-card.html
```

You'll need a `run-config.json` first; see `SKILL.md` section 2 for the schema
and the three intake questions it comes from. `scan` prints a live terminal
reveal and writes `metrics.json`; `render` turns that into a single
self-contained `crm-report-card.html` file you can open in a browser.

For the full walkthrough, including the AI-baseline step
(`assets/icp-scorer-prompt.md`) that fills in the ESTIMATE row, read
`SKILL.md`.

## No keys, runs offline, your rows never leave your machine

- stdlib Python only. No third-party dependencies, no API keys.
- The only network calls are optional domain-liveness HEAD pings against
  domains already present in your own CSV; set `CRM_RC_SKIP_LIVENESS=1` to
  skip them and run fully offline.
- Your CSV is read, processed, and written back to local files
  (`metrics.json`, `crm-report-card.html`) on the machine you run it on. It is
  never uploaded anywhere by this tool.

## Tests

```bash
python3 -m pytest -q
```
