#!/usr/bin/env python3
"""Append sales_headcount + revops_headcount to a flat CSV by calling
Dropleads' free `dropleads_get_lead_count` endpoint per row.

Standalone: doesn't depend on the Apollo/Harvest pipeline. One call per
(row, function) — purely additive.
"""

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional


def dropleads_count(payload: dict) -> Optional[int]:
    """Invoke deepline tools execute dropleads_get_lead_count --payload <json>.
    Returns the integer count, or None on any failure."""
    cmd = [
        "deepline", "tools", "execute", "dropleads_get_lead_count",
        "--payload", json.dumps(payload),
        "--json",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if out.returncode != 0:
            return None
        body = json.loads(out.stdout)
        result = body.get("result") or {}
        data = result.get("data") or {}
        count = data.get("count")
        return count if isinstance(count, int) else None
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="tmp/enriched-flat.csv")
    ap.add_argument("--output", default="tmp/enriched-flat.csv")
    ap.add_argument("--domain-col", default="domain")
    ap.add_argument(
        "--revops-titles",
        default="Revenue Operations,Marketing Operations,Sales Operations",
        help="Comma-separated jobTitle substrings for the ops cohort."
    )
    args = ap.parse_args()

    revops_titles = [t.strip() for t in args.revops_titles.split(",") if t.strip()]
    rows = list(csv.DictReader(open(args.input)))
    if not rows:
        print(f"No rows in {args.input}", file=sys.stderr)
        sys.exit(1)

    print(f"Counting sales + revops headcount for {len(rows)} rows...\n")
    fieldnames = list(rows[0].keys())
    if "sales_headcount" not in fieldnames:
        fieldnames.append("sales_headcount")
    if "revops_headcount" not in fieldnames:
        fieldnames.append("revops_headcount")

    for i, row in enumerate(rows, 1):
        domain = (row.get(args.domain_col) or "").strip()
        if not domain:
            row["sales_headcount"] = ""
            row["revops_headcount"] = ""
            print(f"  [{i:>2}/{len(rows)}] (skip — no domain)")
            continue

        sales = dropleads_count({
            "filters": {"companyDomains": [domain], "departments": ["Sales"]}
        })
        revops = dropleads_count({
            "filters": {"companyDomains": [domain], "jobTitles": revops_titles}
        })
        row["sales_headcount"] = "" if sales is None else sales
        row["revops_headcount"] = "" if revops is None else revops
        name = (row.get("company_name") or "").strip()[:30]
        print(f"  [{i:>2}/{len(rows)}] {domain:<25} {name:<32} sales={sales}, revops={revops}")

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    sales_filled = sum(1 for r in rows if str(r.get("sales_headcount") or "").strip().isdigit())
    revops_filled = sum(1 for r in rows if str(r.get("revops_headcount") or "").strip().isdigit())
    print(f"\nWrote {len(rows)} rows → {args.output}")
    print(f"  sales_headcount filled: {sales_filled}/{len(rows)}")
    print(f"  revops_headcount filled: {revops_filled}/{len(rows)}")


if __name__ == "__main__":
    main()
