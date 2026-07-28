#!/usr/bin/env bash
# Three-row smoke run of the employee-count-accuracy play.
#
# Run this after ANY change to the play, before any full run. It costs about
# six cents and takes a minute. A full 100-row run costs about two dollars.
#
# It exists because two separate bugs shipped that both looked identical from
# the outside: the play computed correct answers and failed to hand them back.
# A dataset column-name collision (from the play's old two-round icypeas+exa
# waterfall, since removed -- exa_answer is now the sole resolver) made the
# round-2 rescue's result invisible. A return-shape change silently truncated
# 100 rows to 20. In both cases `deepline plays check` passed, the run
# reported completed, and the only way to find out was a paid 100-row run.
#
# `plays check` validates the contract, not the plumbing. The Python suite
# covers the scorer and the pure string helpers, not whether data survives the
# trip from a dataset to the output. This script covers exactly that gap.
#
# Usage:  bash benchmark/smoke_play.sh
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
PLAY="crm-report-card/plays/employee-count-accuracy/play.ts"
DEEPLINE="${DEEPLINE:-$HOME/.local/bin/deepline}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Three domains chosen deliberately, not at random:
#   stripe.com    resolves cleanly, the happy path
#   airtable.com  exa_answer (the sole resolver as of 2026-07-28) resolves this
#                 one correctly on the measured 100-company benchmark, so a row
#                 that comes back unanswered means the resolver or the identity
#                 check regressed
#   segment.com   resolution or identity check fails, and it must come back
#                 unanswered rather than carrying a confident wrong number
cat > "$TMP/rows.json" <<'JSON'
{"rows":[
  {"record_id":"1","domain":"stripe.com","company_size":""},
  {"record_id":"2","domain":"airtable.com","company_size":""},
  {"record_id":"3","domain":"segment.com","company_size":""}
]}
JSON

echo "== contract check (free)"
if ! "$DEEPLINE" plays check "$PLAY" --json > "$TMP/check.json" 2>&1; then
  echo "FAIL: plays check errored"; tail -20 "$TMP/check.json"; exit 1
fi
python3 - "$TMP/check.json" <<'PY' || exit 1
import json, sys
s = open(sys.argv[1]).read(); i = s.find("{")
d = json.loads(s[i:]) if i >= 0 else {}
if not d.get("valid", False):
    print("FAIL: contract invalid:", json.dumps(d.get("errors"))[:400]); raise SystemExit(1)
print("  valid")
PY

echo "== 3-row live run (about six cents)"
"$DEEPLINE" plays run --file "$PLAY" --input "@$TMP/rows.json" --json > "$TMP/run.json" 2>&1 || true

RID=$(python3 - "$TMP/run.json" <<'PY'
import json, sys
s = open(sys.argv[1]).read(); i = s.find("{")
print((json.loads(s[i:]) if i >= 0 else {}).get("runId", ""))
PY
)
if [ -z "$RID" ]; then echo "FAIL: no runId"; tail -20 "$TMP/run.json"; exit 1; fi
echo "  run: $RID"

"$DEEPLINE" runs get "$RID" --json > "$TMP/get.json" 2>&1

python3 - "$TMP/get.json" <<'PY' || exit 1
import json, sys
s = open(sys.argv[1]).read(); i = s.find("{")
d = json.loads(s[i:]) if i >= 0 else {}

fails = []
if d.get("status") != "completed":
    fails.append(f"status is {d.get('status')!r}, expected completed")

handle = (d.get("outputs") or {}).get("rows") or {}

# The return must be a dataset HANDLE, not a materialized array. An inline
# array is silently capped by the run-event size limit: a 100-row run came
# back with 20 rows and nothing reported an error.
kind = handle.get("kind")
if kind == "value":
    fails.append("result.rows is an inline value, not a dataset handle. "
                 "Inline arrays truncate on a real run. Return a handle.")
elif kind != "dataset":
    fails.append(f"result.rows kind is {kind!r}, expected 'dataset'")

n = handle.get("rowCount")
if n != 3:
    fails.append(f"result.rows rowCount is {n!r}, expected 3")

# Every dataset that ran must have persisted its rows.
for ds in (d.get("datasets") or []):
    rc = (ds.get("summary") or {}).get("rowCounts") or {}
    if rc.get("failed"):
        fails.append(f"{ds.get('path')} has {rc['failed']} failed rows")

if fails:
    print("FAIL")
    for f in fails: print("  -", f)
    raise SystemExit(1)
print("  status completed, result.rows is a dataset handle with 3 rows")
PY

echo "== row-level checks"
"$DEEPLINE" runs export "$RID" --dataset result.rows --out "$TMP/rows.csv" > /dev/null 2>&1 || {
  echo "FAIL: could not export result.rows. The return is not a retrievable dataset."; exit 1; }

python3 - "$TMP/rows.csv" <<'PY' || exit 1
import csv, sys
rows = {r.get("domain", ""): r for r in csv.DictReader(open(sys.argv[1]))}
fails = []

if len(rows) != 3:
    fails.append(f"exported {len(rows)} rows, expected 3")

def count(d):
    return (rows.get(d, {}).get("verified_employee_count") or "").strip()
def method(d):
    return (rows.get(d, {}).get("identity_method") or "").strip()

# Happy path: resolution succeeds, real number.
if not count("stripe.com"):
    fails.append("stripe.com came back with no count (happy path broken)")

# exa_answer resolves airtable.com correctly on the measured benchmark. A
# missing count here means the resolver or the identity check regressed.
PASSING_METHODS = {"website-match", "website-match-name-escalated:ai-verified", "ai-verified"}
if not count("airtable.com"):
    fails.append("airtable.com has no count. The resolver or the identity "
                 "check is broken: exa_answer resolves this one correctly.")
elif method("airtable.com") not in PASSING_METHODS:
    fails.append(f"airtable.com resolved via {method('airtable.com')!r}, "
                 f"expected one of {sorted(PASSING_METHODS)}")

# Honest refusal: must decline rather than report a confident wrong number.
if count("segment.com"):
    fails.append(f"segment.com returned a count ({count('segment.com')}) but "
                 "resolution or the identity check should reject it. A wrong "
                 "number is worse than none.")

if fails:
    print("FAIL")
    for f in fails: print("  -", f)
    raise SystemExit(1)

for d in ("stripe.com", "airtable.com", "segment.com"):
    print(f"  {d:16s} count={count(d) or '(refused)':>10s}  {method(d)}")
print("\nSMOKE PASSED. Safe to run the full book.")
PY
