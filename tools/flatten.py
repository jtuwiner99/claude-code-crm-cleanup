#!/usr/bin/env python3
"""
Flatten a deepline-native enriched CSV into top-level columns.

Deepline writes one column per playbook step (e.g. `inputs`, `research`,
`verdict`, `_metadata`), each containing a JSON-encoded blob of that step's
output. That shape is right for round-tripping back into the playground UI,
but unreadable for spreadsheets, downstream Python/pandas, CRM imports, or
human review.

This script reads a deepline CSV and emits a sibling `*-flat.csv` whose
columns are the keys returned by the playbook's final `verdict` step
(plus `domain` + `company_name` from the input row, and a derived
`research_status` audit column).

Always runs as the final step of the /crm-cleanup pipeline — both
`tools/enrich.py` and `tools/retry_failed.py` invoke it automatically.
Standalone usage:

    python tools/flatten.py tmp/enriched.csv
    python tools/flatten.py tmp/enriched-final.csv --output tmp/clean.csv

Output naming: `<input>.csv` → `<input>-flat.csv` by default.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys


def _safe_load_json(blob: str) -> dict | None:
    """Parse a JSON cell; return None on any failure."""
    if not blob:
        return None
    try:
        return json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        return None


def _classify_research(research_blob: str) -> str:
    """Return 'ok' if the research step produced usable structured output, else 'failed'."""
    parsed = _safe_load_json(research_blob)
    if not isinstance(parsed, dict):
        return "failed"
    res = parsed.get("result")
    if not isinstance(res, dict):
        return "failed"
    if "error" in res:
        return "failed"
    if not res.get("object"):
        return "failed"
    return "ok"


def _verdict_fields(verdict_blob: str) -> dict:
    """Pull the flat keys out of the verdict step's `result` object."""
    parsed = _safe_load_json(verdict_blob)
    if not isinstance(parsed, dict):
        return {}
    result = parsed.get("result")
    return result if isinstance(result, dict) else {}


def flatten(input_path: pathlib.Path, output_path: pathlib.Path) -> int:
    """Read the deepline-native CSV at input_path and write the flattened CSV.

    Returns the number of rows written (excluding header).
    """
    with open(input_path, newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        output_path.write_text("")
        return 0

    # Discover verdict columns from the first row that has a parseable verdict.
    # Fallback to the canonical /crm-cleanup column order if no verdict is parseable.
    verdict_keys: list[str] = []
    for r in rows:
        v = _verdict_fields(r.get("verdict", ""))
        if v:
            verdict_keys = list(v.keys())
            break
    if not verdict_keys:
        verdict_keys = [
            "domain_clean", "company_name", "company_type", "website",
            "numberofemployees", "city", "country", "zip", "state",
            "address", "reasoning",
        ]

    # Final column order: original input identity first, then verdict outputs,
    # then research_status as the rightmost audit field. Drop verdict's
    # duplicates of `domain_clean` / `company_name` since the input columns
    # are authoritative for joining back into the source CRM.
    skip_in_verdict = {"domain_clean", "company_name"}
    fieldnames = ["domain", "company_name"]
    for k in verdict_keys:
        if k not in skip_in_verdict and k not in fieldnames:
            fieldnames.append(k)
    fieldnames.append("research_status")

    with open(output_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            verdict = _verdict_fields(r.get("verdict", ""))
            out = {"domain": r.get("domain", ""), "company_name": r.get("company_name", "")}
            for k in fieldnames:
                if k in {"domain", "company_name", "research_status"}:
                    continue
                out[k] = verdict.get(k)
            out["research_status"] = _classify_research(r.get("research", ""))
            w.writerow(out)

    return len(rows)


def default_output_path(input_path: pathlib.Path) -> pathlib.Path:
    """`tmp/foo.csv` → `tmp/foo-flat.csv`."""
    return input_path.with_name(f"{input_path.stem}-flat{input_path.suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Flatten a deepline-native enriched CSV into top-level columns.",
    )
    parser.add_argument("input", type=pathlib.Path,
                        help="Input deepline-native CSV (e.g. tmp/enriched.csv).")
    parser.add_argument("--output", type=pathlib.Path, default=None,
                        help="Output path. Default: <input>-flat.csv next to the input.")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: input not found: {args.input}", file=sys.stderr)
        return 2

    output = args.output or default_output_path(args.input)
    n = flatten(args.input, output)
    print(f"Flattened {n} rows → {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
