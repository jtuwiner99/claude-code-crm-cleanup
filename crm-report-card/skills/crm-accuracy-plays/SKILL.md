---
name: crm-accuracy-plays
description: Unlock the accuracy rows on a CRM Report Card by running a verification play on the user's own Deepline account. Use when someone has already run the free scan and wants to know whether their data is actually correct, not just filled in, or asks to unlock a LOCKED row.
---

# CRM accuracy plays

The free report card grades completeness. It cannot grade accuracy, because a
file has no ground truth to check itself against. This skill runs a small,
cheap verification play against a random sample of their book on **their own
Deepline account**, and turns one LOCKED row into a graded row.

## Ground rules

- **Never run a play without showing the cost and getting an explicit yes.**
- **Never write to their CRM.** These plays read and return numbers.
- **Sample, do not scan the whole book.** This produces a grade. Cleaning the
  whole book is the paid engagement.
- **Never chunk a run.** One `deepline plays run` over the whole sample. If a
  run dies, relaunch the same play name with the same dataset key and the same
  full list; completed rows are reused for free. Slicing the list is chunking
  and it is slower, not safer.
- The Deepline CLI prints an update banner before its JSON. Always parse from
  the first `{`, never `json.loads` of the whole output.

## Step 0: you need a finished scan

This skill starts from an existing `metrics.json` and the CSV it was built from.
If they do not exist, run the `crm-report-card` skill first. Do not re-do intake.

## Step 1: preflight, before anything is spendable

```bash
deepline auth status --json
```

Read `.status` and `.connected`. Anything other than `"claimed"` and `true`
means they are not authed. Stop and give them exactly this:

> "You'll need a Deepline account for this part, it's what actually does the
> verifying, and you pay them directly at cost. Run `deepline auth register`,
> approve it in the browser, and we'll pick up right here."

Then check they can pay for it:

```bash
deepline billing balance --json
```

Read `.balance` (credits) and `.has_payment_method`. One credit is $0.10. If the
balance is below the estimate you are about to quote and there is no payment
method, say so plainly before they commit to anything.

## Step 2: show what can run, and what it costs

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m crm_report_card.cli plays \
  --registry "${CLAUDE_PLUGIN_ROOT}/plays/registry.json" \
  --config run-config.json \
  --csv <their-export.csv> \
  --out plays.json
```

This prints the eligible plays with a real dollar and credit estimate, plus any
play that cannot run and the exact column it would need. Show them both. A play
that cannot run is not a failure, it is a missing column, and saying which one
is more useful than hiding it.

Then ask, plainly:

> "Want me to check <N> records for at most $<X>? That's <Y> Deepline credits
> on your account, and it is a ceiling, not a quote: PeopleDataLabs bills only
> when it finds a match, so misses cost nothing and the real number is usually
> lower. It's a sample, not your whole book, which is all we need for a grade."

**Wait for a yes. Do not proceed on an implied go.**

## Step 3: draw the sample

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m crm_report_card.cli sample \
  --registry "${CLAUDE_PLUGIN_ROOT}/plays/registry.json" \
  --play employee-count-accuracy \
  --config run-config.json \
  --csv <their-export.csv> \
  --out sample.csv
```

The sample is random and seeded, drawn only from records that have every column
the play needs. It is deliberately not the rows the free scan flagged: checking
the rows we already called bad would inflate the failure rate.

## Step 4: run the play

```bash
deepline plays check "${CLAUDE_PLUGIN_ROOT}/plays/employee-count-accuracy/play.ts"
deepline plays run --file "${CLAUDE_PLUGIN_ROOT}/plays/employee-count-accuracy/play.ts" \
  --input @sample-input.json --json
```

Build `sample-input.json` as `{"rows": [ ...the sample.csv rows as objects... ]}`.

If the run dies partway, relaunch the identical command. Completed rows are
reused free. Do not slice the list. If it comes back with fewer rows than you
drew, score what came back and let the sample size be the number actually
returned; do not report the number you drew.

Save the returned `rows` array to `play-rows.csv` with the headers
`record_id,domain,stored_employee_count,verified_employee_count,source`.

## Step 5: score, unlock, and re-render

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m crm_report_card.cli fragment \
  --registry "${CLAUDE_PLUGIN_ROOT}/plays/registry.json" \
  --play employee-count-accuracy \
  --rows play-rows.csv \
  --out fragment.json

PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m crm_report_card.cli unlock \
  --metrics metrics.json --fragment fragment.json --out metrics.json

PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m crm_report_card.cli report \
  --config run-config.json --out crm-report-card.html --lists-dir lists \
  --company-metrics metrics.json --company-csv <their-export.csv>
```

Then report the actual spend:

```bash
deepline billing usage --json
```

If it came in materially above the estimate, say so. Do not bury it.

## Step 6: read them the result honestly

The unlocked row shows a rate, a grade, cited records with verify deep-links,
and a provenance line. Walk them through it the same way as a FACT row, and be
precise about three things:

- **What "wrong" means here.** Two or more size bands apart. Off by a little is
  not counted.
- **`unverifiable` is not an error.** It is the number of records the provider
  had no data for. It is reported next to the rate and excluded from it.
- **This is a sample.** The rate is an estimate of the whole book, measured on
  <N> records, not a census.

If nothing came back that could be compared, the row renders as **Not
measurable** with no grade and no percentage, and `unlock` prints
`not measurable` instead of a rate. That is the correct outcome, not a bug to
work around. Tell them plainly what happened: they paid for a run, the run
completed, and the provider had no usable value for the records drawn, so there
is nothing to grade. Never re-render it as a 0% A. Offer to re-draw a different
sample or point the play at a different column if the stored values were blank.

Note that once any accuracy row is present, the card's privacy line changes on
its own: it stops saying nothing left the machine, and says instead that the
company domains in the sample went to the named providers through their own
Deepline account. That is deliberate. Do not talk around it.

The completeness grade does not change. Accuracy is its own grade, because they
are different questions.
