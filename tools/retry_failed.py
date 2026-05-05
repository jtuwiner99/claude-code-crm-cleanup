#!/usr/bin/env python3
"""
Retry-failed-rows pass for /crm-cleanup.

Reads tmp/enriched.csv (the output of `tools/enrich.py`), finds rows where
the `research` step errored out (transient deepline-side failures like
`fetch failed` or `Failed to execute deeplineagent.`), re-runs ONLY those
rows through the same playbook up to MAX_ATTEMPTS times, and merges
successful retry results back into a final tmp/enriched-final.csv.

Why this script exists:
    The first end-to-end run of the sample CSV produced ~16% transient
    failures (8 of 50 rows hit deepline web-tool / runtime hiccups; 1 hit
    a model JSON truncation). All of those would likely succeed on a
    second attempt — so a targeted retry pass is the cheapest way to push
    success rate from ~82% toward ~98%, without re-spending credits on
    the 41 rows that already worked.

Design:
    - Targeted, not universal: rebuild a CSV containing only the failed
      rows' inputs, point `tools/enrich.py` at it. Don't use
      `deepline enrich --in-place --with-force` because that recomputes
      every row including the successful ones (~3x credit waste).
    - Up to MAX_ATTEMPTS retry passes with RETRY_BACKOFF_SEC between them.
      Most transient errors clear on attempt 2.
    - Merge by `domain` (the natural join key — every input row has it).

Usage:
    python tools/retry_failed.py
    python tools/retry_failed.py --enriched tmp/enriched.csv --output tmp/enriched-final.csv
    python tools/retry_failed.py --max-attempts 1            # only one retry pass
    python tools/retry_failed.py --backoff-sec 60            # longer wait between passes

Exit code:
    0 if all rows resolved (or were already resolved)
    1 if some rows are still failing after MAX_ATTEMPTS — final CSV still
      written, but operator should investigate the residual failures.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_ENRICHED = ROOT / "tmp" / "enriched.csv"
DEFAULT_PLAYBOOK = ROOT / "tmp" / "playbook.jsonc"
DEFAULT_OUTPUT = ROOT / "tmp" / "enriched-final.csv"
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_BACKOFF_SEC = 30


def load_enriched(path: pathlib.Path) -> list[dict]:
    with open(path) as f:
        return list(csv.DictReader(f))


def row_failed(row: dict) -> bool:
    """A row is considered failed if the `research` step has an error."""
    raw = row.get("research")
    if not raw:
        return True
    try:
        research = json.loads(raw)
    except json.JSONDecodeError:
        return True
    res = research.get("result", {}) or {}
    return "error" in res


def write_retry_input(failed_rows: list[dict], path: pathlib.Path) -> int:
    """Write a minimal CSV (domain + company_name) containing only failed rows."""
    if not failed_rows:
        return 0
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["domain", "company_name"])
        w.writeheader()
        for r in failed_rows:
            w.writerow({
                "domain": r.get("domain", ""),
                "company_name": r.get("company_name", ""),
            })
    return len(failed_rows)


def run_enrich(input_csv: pathlib.Path, playbook: pathlib.Path, output_csv: pathlib.Path) -> int:
    """Shell out to tools/enrich.py for one retry pass. Returns exit code."""
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "enrich.py"),
        str(input_csv),
        "--playbook", str(playbook),
        "--output", str(output_csv),
    ]
    print(f"  → {' '.join(cmd)}")
    return subprocess.call(cmd)


def merge(original: list[dict], retry_rows: list[dict]) -> list[dict]:
    """
    Replace failed rows in `original` with their successful retry counterparts.
    Match by `domain`. Rows still failing after retry stay as-is (the latest
    error wins so the operator sees the most recent failure mode).
    """
    by_domain = {r["domain"]: r for r in retry_rows}
    out = []
    for r in original:
        if row_failed(r) and r["domain"] in by_domain:
            replacement = by_domain[r["domain"]]
            # Keep the original column order from `original` — the retry
            # CSV may have produced an identical schema, but defensive.
            merged = {**r, **{k: v for k, v in replacement.items() if k in r}}
            out.append(merged)
        else:
            out.append(r)
    return out


def write_csv(rows: list[dict], path: pathlib.Path) -> None:
    if not rows:
        path.write_text("")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Retry-failed-rows pass for /crm-cleanup. Targets only the "
                    "rows where the research step errored out.",
    )
    parser.add_argument("--enriched", type=pathlib.Path, default=DEFAULT_ENRICHED,
                        help="Path to the enriched CSV from the primary run "
                             "(default: tmp/enriched.csv).")
    parser.add_argument("--playbook", type=pathlib.Path, default=DEFAULT_PLAYBOOK,
                        help="Playbook to re-run (default: tmp/playbook.jsonc).")
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT,
                        help="Where to write the merged final CSV "
                             "(default: tmp/enriched-final.csv).")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS,
                        help=f"How many retry passes to run "
                             f"(default: {DEFAULT_MAX_ATTEMPTS}).")
    parser.add_argument("--backoff-sec", type=int, default=DEFAULT_BACKOFF_SEC,
                        help=f"Sleep this long between retry passes "
                             f"(default: {DEFAULT_BACKOFF_SEC}s).")
    args = parser.parse_args()

    if not args.enriched.exists():
        print(f"ERROR: enriched CSV not found: {args.enriched}", file=sys.stderr)
        return 2
    if not args.playbook.exists():
        print(f"ERROR: playbook not found: {args.playbook}", file=sys.stderr)
        return 2

    rows = load_enriched(args.enriched)
    failed = [r for r in rows if row_failed(r)]
    initial_failed = len(failed)
    print(f"Loaded {len(rows)} rows from {args.enriched}")
    print(f"Initial failures: {initial_failed}")

    if not failed:
        print("Nothing to retry — writing through to the final output.")
        write_csv(rows, args.output)
        print(f"Wrote {args.output} ({len(rows)} rows).")
        return 0

    retry_input = ROOT / "tmp" / "retry-rows.csv"
    retry_output = ROOT / "tmp" / "retry-enriched.csv"

    for attempt in range(1, args.max_attempts + 1):
        n = write_retry_input(failed, retry_input)
        print(f"\n--- Attempt {attempt}/{args.max_attempts} — retrying {n} row(s) ---")
        if attempt > 1:
            print(f"  (sleeping {args.backoff_sec}s before retry)")
            time.sleep(args.backoff_sec)

        rc = run_enrich(retry_input, args.playbook, retry_output)
        if rc != 0:
            print(f"  enrich.py exited {rc} — leaving rows in their current state.")
            continue

        if not retry_output.exists():
            print(f"  Retry produced no output file — skipping merge for this attempt.")
            continue

        retry_rows = load_enriched(retry_output)
        rows = merge(rows, retry_rows)
        failed = [r for r in rows if row_failed(r)]
        print(f"  After attempt {attempt}: {len(failed)} row(s) still failing.")

        if not failed:
            break

    write_csv(rows, args.output)
    final_failed = sum(1 for r in rows if row_failed(r))
    print(f"\nWrote {args.output} ({len(rows)} rows).")
    print(f"Final failures: {final_failed}/{len(rows)} "
          f"(was {initial_failed}/{len(rows)} before retry).")

    # Always emit a flat-column companion next to the merged final CSV
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from flatten import flatten, default_output_path
        flat_path = default_output_path(args.output)
        n = flatten(args.output, flat_path)
        print(f"Flat CSV: {flat_path} ({n} rows)")
    except Exception as e:
        print(f"  (flatten step skipped: {e})", file=sys.stderr)

    return 0 if final_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
