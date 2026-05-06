#!/usr/bin/env python3
"""
Re-run the Harvest + dependent steps on `tmp/enriched.csv` in chunks of N
rows, with a small delay between chunks, so we never have more than N
concurrent `generic_http_request` calls in flight at Harvest's API.

Default aliases match the canonical /crm-cleanup playbook:
`harvest,classify,verdict` — harvest is the rate-limited HTTP step; classify
reads harvest's description so it must re-run when harvest changes; verdict
composes the final row from both. Customize via --aliases if your playbook
uses different names.

Why this exists:
    Harvest API throttles per-key concurrency at ~5. When Deepline fans out
    to all 28+ eligible rows in parallel from a single playbook run, Harvest
    returns HTTP 200 OK (deceptively!) with body
        {"error":"Too many queued requests (code_22)","status":429,"data":null}
    on most/all of them. Chunking to N=5 (default) keeps us safely under the
    per-key cap.

How:
    For each chunk of `--rows START:END`, runs:
        deepline enrich --in-place
            --input tmp/enriched.csv
            --config tmp/playbook.compiled.jsonc
            --with-force harvest,classify,verdict
            --rows START:END

    The `--with-force` flag tells Deepline to recompute the named aliases
    even though they already have values (from the prior run that hit the
    rate limit). `--rows` restricts execution to that range; everything else
    stays put. Apollo's lookup step is NOT in the force list — already-paid
    Apollo data carries forward unchanged across chunked retries.

Usage:
    python tools/retry_harvest_chunked.py
    python tools/retry_harvest_chunked.py --chunk-size 5 --delay-sec 2
    python tools/retry_harvest_chunked.py --aliases harvest_call,verdict
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_ENRICHED = ROOT / "tmp" / "enriched.csv"
DEFAULT_PLAYBOOK_COMPILED = ROOT / "tmp" / "playbook.compiled.jsonc"
DEFAULT_CHUNK_SIZE = 5
DEFAULT_DELAY_SEC = 2
DEFAULT_ALIASES = "harvest,classify,verdict"


def run_chunk(enriched: pathlib.Path, playbook: pathlib.Path,
              start: int, end: int, aliases: str) -> int:
    cmd = [
        "deepline", "enrich",
        "--in-place",
        "--input", str(enriched),
        "--config", str(playbook),
        "--with-force", aliases,
        "--rows", f"{start}:{end}",
    ]
    print(f"  → {' '.join(cmd)}")
    return subprocess.call(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Chunked Harvest retry — keeps concurrent Harvest calls under N at a time.",
    )
    parser.add_argument("--enriched", type=pathlib.Path, default=DEFAULT_ENRICHED,
                        help="CSV to retry in place (default: tmp/enriched.csv).")
    parser.add_argument("--playbook-compiled", type=pathlib.Path,
                        default=DEFAULT_PLAYBOOK_COMPILED,
                        help="Compiled playbook with HARVEST_API_KEY substituted "
                             "(default: tmp/playbook.compiled.jsonc).")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
                        help=f"Rows per chunk = max concurrent Harvest calls "
                             f"(default: {DEFAULT_CHUNK_SIZE}).")
    parser.add_argument("--delay-sec", type=int, default=DEFAULT_DELAY_SEC,
                        help=f"Sleep between chunks to let Harvest's queue drain "
                             f"(default: {DEFAULT_DELAY_SEC}s).")
    parser.add_argument("--aliases", type=str, default=DEFAULT_ALIASES,
                        help=f"Comma-separated --with-force alias list "
                             f"(default: '{DEFAULT_ALIASES}', matching the canonical "
                             f"/crm-cleanup playbook).")
    args = parser.parse_args()

    if not args.enriched.exists():
        print(f"ERROR: enriched CSV not found: {args.enriched}", file=sys.stderr)
        return 2
    if not args.playbook_compiled.exists():
        print(f"ERROR: compiled playbook not found: {args.playbook_compiled}", file=sys.stderr)
        print(f"  (the compile step in tools/enrich.py produces it; run an enrich first)",
              file=sys.stderr)
        return 2

    with open(args.enriched, newline="") as f:
        n = sum(1 for _ in csv.reader(f)) - 1  # exclude header

    print(f"Rows in {args.enriched.name}: {n}")
    print(f"Chunk size: {args.chunk_size} (max concurrent Harvest calls)")
    print(f"Delay between chunks: {args.delay_sec}s")
    print(f"Aliases re-forced: {args.aliases}")
    print()

    chunks = [(s, min(s + args.chunk_size, n)) for s in range(0, n, args.chunk_size)]
    print(f"Will run {len(chunks)} chunk(s).")

    for i, (start, end) in enumerate(chunks):
        print(f"\n=== Chunk {i+1}/{len(chunks)}: rows {start}:{end} ===")
        rc = run_chunk(args.enriched, args.playbook_compiled, start, end, args.aliases)
        if rc != 0:
            print(f"  chunk exit code {rc} — continuing to next chunk")
        if i < len(chunks) - 1:
            print(f"  sleeping {args.delay_sec}s before next chunk")
            time.sleep(args.delay_sec)

    # Re-flatten so the user sees fresh aggregate counts on the flat CSV
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        from flatten import flatten, default_output_path
        flat = default_output_path(args.enriched)
        n_out = flatten(args.enriched, flat)
        print(f"\nRe-flattened: {flat} ({n_out} rows)")
    except Exception as e:
        print(f"\n(re-flatten skipped: {e})", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
