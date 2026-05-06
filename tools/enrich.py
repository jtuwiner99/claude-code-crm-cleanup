#!/usr/bin/env python3
"""
Thin CLI wrapper around the Deepline runner for the giveaway repo.

Invoked by the `/crm-cleanup` skill once the conversation has produced a
playbook at `tmp/playbook.jsonc`. Can also be run directly with an explicit
--playbook path for advanced users.

Usage:
    python tools/enrich.py <csv> --playbook <playbook.jsonc>

Defaults:
    --output   tmp/enriched.csv

Requires:
    DEEPLINE_API_KEY in environment (or .env file via python-dotenv)
    `deepline` CLI on PATH — install:
        curl -s 'https://code.deepline.com/api/v2/cli/install' | bash
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from runner.deepline_runner import run_enrichment

# Repo-wide convention for secret placeholders: <UPPER_SNAKE_KEY>.
# When the playbook is compiled (right before invoking deepline), every
# occurrence of <FOO> is substituted with os.environ["FOO"] when present.
# Unmatched placeholders are passed through untouched (the Deepline CLI will
# fail loudly on them, which is the right behavior — the operator forgot to
# set a key in .env).
_PLACEHOLDER_RE = re.compile(r"<([A-Z][A-Z0-9_]+)>")

# Threshold above which we trigger an auto chunked-retry pass. Harvest's
# rate-limiter masks itself as HTTP 200 with body.error="code_22" — a single
# transient hit isn't worth a retry, but two or more usually means the
# entire batch overflowed the per-key concurrency cap.
RATE_LIMIT_AUTO_RETRY_THRESHOLD = 2


def detect_harvest_rate_limit(enriched_csv: pathlib.Path,
                              harvest_alias: str = "harvest") -> tuple[int, int]:
    """Scan the enriched CSV's harvest column and return
    (n_rate_limited, n_total_with_url). Counts rows where Harvest's body
    contained the code_22 rate-limit error — these are recoverable via
    tools/retry_harvest_chunked.py."""
    import csv
    import json

    n_rate_limited = 0
    n_with_url = 0
    try:
        with open(enriched_csv, newline="") as f:
            for row in csv.DictReader(f):
                blob = row.get(harvest_alias) or ""
                if not blob:
                    continue
                try:
                    parsed = json.loads(blob)
                except (json.JSONDecodeError, TypeError):
                    continue
                result = parsed.get("result") if isinstance(parsed, dict) else None
                if not isinstance(result, dict):
                    continue
                # Only count rows that had a real fetch (not the "?url=missing" sentinel)
                final_url = result.get("final_url") or result.get("requested_url") or ""
                if "url=missing" in final_url:
                    continue
                n_with_url += 1
                body = result.get("data") or {}
                err = body.get("error") if isinstance(body, dict) else ""
                if err and "code_22" in str(err):
                    n_rate_limited += 1
    except FileNotFoundError:
        pass
    return n_rate_limited, n_with_url


def auto_chunked_retry(enriched_csv: pathlib.Path,
                       compiled_playbook: pathlib.Path,
                       chunk_size: int = 5,
                       delay_sec: int = 2) -> int:
    """Invoke tools/retry_harvest_chunked.py as a subprocess. Returns its
    exit code (0 on success). Output streams to the parent's stdout."""
    import subprocess

    script = pathlib.Path(__file__).resolve().parent / "retry_harvest_chunked.py"
    cmd = [
        sys.executable, str(script),
        "--enriched", str(enriched_csv),
        "--playbook-compiled", str(compiled_playbook),
        "--chunk-size", str(chunk_size),
        "--delay-sec", str(delay_sec),
    ]
    print(f"  → {' '.join(cmd)}")
    return subprocess.call(cmd)


def compile_playbook(src_path: pathlib.Path, dst_path: pathlib.Path) -> dict:
    """Substitute env-var placeholders in the playbook and write the compiled
    file to disk. Returns a dict with substitution audit info."""
    raw = src_path.read_text()
    substituted: dict[str, str] = {}
    unresolved: list[str] = []

    def _replace(m: re.Match) -> str:
        key = m.group(1)
        val = os.environ.get(key)
        if val is None:
            if key not in unresolved:
                unresolved.append(key)
            return m.group(0)  # leave as-is
        substituted[key] = "set"
        return val

    compiled = _PLACEHOLDER_RE.sub(_replace, raw)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text(compiled)
    return {"substituted_keys": list(substituted), "unresolved": unresolved}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enrich a CSV using the Sculpted account-cleanup engine via Deepline.",
    )
    parser.add_argument(
        "csv_path",
        type=pathlib.Path,
        help="Input CSV (must have at least `domain` and `company_name` columns).",
    )
    parser.add_argument(
        "--playbook", type=pathlib.Path,
        required=True,
        help="Path to a compiled Deepline playbook (typically tmp/playbook.jsonc, generated by /crm-cleanup).",
    )
    parser.add_argument(
        "--output", type=pathlib.Path,
        default=ROOT / "tmp" / "enriched.csv",
        help="Where the enriched CSV should land. Defaults to tmp/enriched.csv.",
    )
    parser.add_argument(
        "--rows", type=str, default=None,
        help="Optional row range like '0:50' to pilot a subset.",
    )
    parser.add_argument(
        "--timeout", type=int, default=1800,
        help="Hard timeout (seconds) before the run is killed.",
    )
    parser.add_argument(
        "--no-auto-retry", action="store_true",
        help="Skip the auto chunked-retry pass when Harvest rate-limit is detected.",
    )
    args = parser.parse_args()

    if not os.environ.get("DEEPLINE_API_KEY"):
        print("ERROR: DEEPLINE_API_KEY not set.", file=sys.stderr)
        print("Copy .env.example to .env and fill it in. Get a key at https://deepline.ai", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Compile-step: substitute env-var placeholders (e.g. <HARVEST_API_KEY>)
    # before handing the playbook to the Deepline CLI. Compiled file lands at
    # tmp/<playbook-stem>.compiled.jsonc — gitignored.
    compiled_path = args.playbook.with_name(f"{args.playbook.stem}.compiled{args.playbook.suffix}")
    compile_audit = compile_playbook(args.playbook, compiled_path)

    print(f"Enriching: {args.csv_path}")
    print(f"Playbook:  {args.playbook}  →  {compiled_path}")
    if compile_audit["substituted_keys"]:
        print(f"Compiled:  substituted {compile_audit['substituted_keys']}")
    if compile_audit["unresolved"]:
        print(f"Compiled:  WARNING — unresolved placeholders {compile_audit['unresolved']} "
              f"(Deepline will fail when those steps run)", file=sys.stderr)
    print(f"Output:    {args.output}")
    if args.rows:
        print(f"Row range: {args.rows}")
    print()

    result = run_enrichment(
        playbook_path=compiled_path,
        csv_path=args.csv_path,
        output_path=args.output,
        row_range=args.rows,
        timeout_seconds=args.timeout,
    )

    print()
    if result["ok"]:
        print(f"Done. Enriched CSV at: {result['enriched_csv']}")
        if result.get("session_url"):
            print(f"Session UI: {result['session_url']}")
        if result.get("credits_used") is not None:
            print(f"Credits used: {result['credits_used']}")

        # Detect Harvest rate-limit (code_22) — Harvest masks 429s as 200 OK
        # with body.error="Too many queued requests (code_22)". If enough
        # rows tripped this, run tools/retry_harvest_chunked.py automatically.
        n_rl, n_url = detect_harvest_rate_limit(args.output)
        if n_rl > 0:
            print(f"\nHarvest rate-limit detected: {n_rl}/{n_url} rows hit code_22.")
            if args.no_auto_retry:
                print("  (--no-auto-retry set; skipping. Run "
                      "`python tools/retry_harvest_chunked.py` manually to recover.)")
            elif n_rl >= RATE_LIMIT_AUTO_RETRY_THRESHOLD:
                print(f"  Triggering chunked retry (threshold: "
                      f"{RATE_LIMIT_AUTO_RETRY_THRESHOLD})...\n")
                rc = auto_chunked_retry(args.output, compiled_path)
                if rc != 0:
                    print(f"  retry exit code {rc}", file=sys.stderr)
                else:
                    # Re-detect to report final state
                    n_rl_after, _ = detect_harvest_rate_limit(args.output)
                    print(f"\nPost-retry: {n_rl_after}/{n_url} rows still rate-limited.")
            else:
                print(f"  Below auto-retry threshold ({RATE_LIMIT_AUTO_RETRY_THRESHOLD}). "
                      f"Run `python tools/retry_harvest_chunked.py` to recover.")

        # Always emit a flat-column companion next to the deepline-native CSV
        try:
            sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
            from flatten import flatten, default_output_path
            flat_path = default_output_path(args.output)
            n = flatten(args.output, flat_path)
            print(f"Flat CSV:   {flat_path} ({n} rows)")
        except Exception as e:
            print(f"  (flatten step skipped: {e})", file=sys.stderr)
        return 0
    else:
        print("Run failed.", file=sys.stderr)
        for err in result.get("errors", []):
            print(f"  - {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
