# CRM Report Card

> **Status: the free scan is complete; one accuracy play is proven, two are not
> built yet.** The offline scan is covered by 275 tests. The employee-count
> accuracy play has been run end to end against 100 companies with
> hand-confirmed ground truth: 100% correct company identification, 100%
> correct headcount on the 99 it answered, at about a cent per company. See
> [`benchmark/`](benchmark/) for the method, the raw results, and the ground
> truth. The email-deliverability and still-employed plays are named on the
> card but not yet built.

A Tier 0 CRM data-quality audit. Point it at a CRM CSV export and it produces
a report card: an overall letter grade, six deterministic FACTs (duplicates,
missing critical fields, contradictions, junk records, stale records, dead
domains), and one clearly-labeled, unverified ESTIMATE (percent likely
"qualified" against a plain-English ICP). It reveals the scope and severity of
a messy CRM and shows a verified taste of what a real fix looks like. It never
writes back to a CRM and never claims to have fixed anything.

## Install

As a plugin (recommended, gets the accuracy plays too):

    /plugin marketplace add jtuwiner99/claude-code-crm-cleanup
    /plugin install crm-report-card@sculpted-plugins

As a standalone skill (free offline scan only):

    bash scripts/build_bundle.sh
    cp -R dist/crm-report-card ~/.claude/skills/crm-report-card

## Quickstart against the bundled fixture

Run everything from the repo root. The package uses relative imports, so
invoke it as a module with `crm-report-card/scripts` on `PYTHONPATH`:

```bash
PYTHONPATH=crm-report-card/scripts python3 -m crm_report_card.cli scan \
  --config run-config.json \
  --csv fixtures/messy-crm-sample.csv \
  --out metrics.json

PYTHONPATH=crm-report-card/scripts python3 -m crm_report_card.cli render \
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
  domains already present in your own CSV. Set `CRM_RC_SKIP_LIVENESS=1` to run
  with no network at all: the dead-domain row is then skipped entirely, and it
  neither appears on the card nor counts toward the grade.
- Your CSV is read, processed, and written back to local files
  (`metrics.json`, `crm-report-card.html`) on the machine you run it on. It is
  never uploaded anywhere by this tool.

## Tests

```bash
python3 -m pytest -q
```
