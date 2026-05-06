#!/usr/bin/env python3
"""Apply a deterministic tier scoring model to an enriched CSV.

Reads a JSON model with rule blocks (match_all / match_any over typed
operators) and writes the input CSV back with three appended columns:
  tier, tier_label, tier_rule

Rules are evaluated top-to-bottom; first match wins. If nothing matches,
default_tier is assigned (or the highest tier if default_tier missing).
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path


def _to_number(s):
    if s is None or str(s).strip() == "":
        return None
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return None


def _match(row, field, op, value):
    actual = row.get(field, "")
    actual_str = str(actual).strip() if actual is not None else ""
    if op == "eq":
        return actual_str == str(value).strip()
    if op == "neq":
        return actual_str != str(value).strip()
    if op == "in":
        return actual_str in [str(v).strip() for v in value]
    if op == "not_in":
        return actual_str not in [str(v).strip() for v in value]
    if op in ("gt", "gte", "lt", "lte"):
        n = _to_number(actual)
        if n is None:
            return False
        return {"gt": n > value, "gte": n >= value, "lt": n < value, "lte": n <= value}[op]
    if op == "between":
        n = _to_number(actual)
        lo, hi = value
        return n is not None and lo <= n <= hi
    if op == "is_null":
        return actual_str == ""
    if op == "not_null":
        return actual_str != ""
    raise ValueError(f"unknown op: {op}")


def _evaluate_rule(row, rule):
    if "match_all" in rule:
        return all(_match(row, c["field"], c["op"], c["value"]) for c in rule["match_all"])
    if "match_any" in rule:
        return any(_match(row, c["field"], c["op"], c["value"]) for c in rule["match_any"])
    return False


def score_row(row, model):
    labels = {t["tier"]: t["label"] for t in model["tiers"]}
    for rule in model["rules"]:
        if _evaluate_rule(row, rule):
            return rule["tier"], labels.get(rule["tier"], ""), rule["id"]
    default = model.get("default_tier", model["tier_count"])
    return default, labels.get(default, ""), "default"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="tmp/enriched-flat.csv")
    ap.add_argument("--model", default="tmp/scoring-model.json")
    ap.add_argument("--output", default="tmp/scored-accounts.csv")
    args = ap.parse_args()

    model = json.loads(Path(args.model).read_text())
    rows = list(csv.DictReader(open(args.input)))
    if not rows:
        print(f"No rows in {args.input}", file=sys.stderr)
        sys.exit(1)

    tier_counts, rule_counts = Counter(), Counter()
    for row in rows:
        tier, label, rule_id = score_row(row, model)
        row["tier"] = tier
        row["tier_label"] = label
        row["tier_rule"] = rule_id
        tier_counts[tier] += 1
        rule_counts[rule_id] += 1

    fieldnames = list(rows[0].keys())
    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"Scored {len(rows)} rows → {args.output}\n")
    print("Tier distribution:")
    labels = {t["tier"]: t["label"] for t in model["tiers"]}
    for tier in sorted(tier_counts):
        pct = 100 * tier_counts[tier] / len(rows)
        print(f"  Tier {tier} ({labels.get(tier, '')}): {tier_counts[tier]} ({pct:.0f}%)")
    print("\nRule fires:")
    for rule_id, count in rule_counts.most_common():
        print(f"  {rule_id}: {count}")


if __name__ == "__main__":
    main()
