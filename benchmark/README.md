# The employee-count provider benchmark

Six B2B data providers, 100 public companies, one question: how many people work
here. Ground truth was hand-recorded against the live LinkedIn company page.

## Read it

- **[report.html](report.html)** the published report, including the full
  methodology appendix. This is the file published as a shareable artifact; open
  it locally or serve the directory.
- **[RESULTS.md](RESULTS.md)** the same results in markdown, with the per-provider
  failure detail.
- **[METHODOLOGY.md](METHODOLOGY.md)** the pre-registration and every amendment,
  each committed separately with its reason.

## Reproduce it

```bash
python3 benchmark/score.py            # recomputes every published figure
python3 benchmark/score.py --json out.json
```

`score.py` reads `ground_truth.jsonl` and the provider result files and prints
the tables. No figure in the report or the markdown is typed by hand.

## The data

| File | What it is |
|---|---|
| `domains.csv` | the 100 companies and their tiers, fixed before any provider ran |
| `ground_truth.jsonl` | every hand-recorded truth value, append-only, corrections included |
| `raw_results.csv` | every provider's answer per company |
| `ourplay_results.csv` | the Sculpted play's answers |
| `raw_payloads/` | full provider payloads (gitignored, local only) |

## Rebuild the harness

```bash
python3 benchmark/run_providers.py --dry-run
python3 benchmark/run_providers.py --providers <name>,<name>   # incremental, does not re-pay for others
python3 benchmark/ground_truth_console.py                      # the blind review console
```

`run_providers.py` costs real money. It calls paid providers. Check which
Deepline workspace you are in before running it.
