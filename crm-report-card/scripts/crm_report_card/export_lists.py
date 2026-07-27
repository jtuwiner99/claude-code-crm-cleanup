"""Write one filtered CSV per flagged signal, for the report card's per-signal
"Download all as CSV" links. stdlib csv only, nothing leaves the machine."""
from __future__ import annotations
import csv
import os


def write_lists(object_type: str, metrics: dict, records: list[dict], out_dir: str) -> dict:
    """For each fact in metrics["facts"] with a non-empty offending_ids, write
    out_dir/{object_type}-{signal}.csv containing the offending rows (a leading
    flag_reason column first). Returns {signal: filename} for files written."""
    os.makedirs(out_dir, exist_ok=True)
    by_id = {rec.get("record_id", ""): rec for rec in records}
    facts = metrics.get("facts", {})
    written: dict[str, str] = {}

    for signal, fact in facts.items():
        offending_ids = fact.get("offending_ids") or []
        rows = [by_id[rid] for rid in offending_ids if rid in by_id]
        if not rows:
            continue

        detail_by_id = {
            ex.get("record_id"): ex.get("detail")
            for ex in (fact.get("examples") or [])
        }

        field_set: set[str] = set()
        for row in rows:
            field_set.update(row.keys())
        other_fields = sorted(field_set - {"record_id"})
        fieldnames = ["flag_reason", "record_id"] + other_fields

        filename = f"{object_type}-{signal}.csv"
        path = os.path.join(out_dir, filename)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for rid in offending_ids:
                row = by_id.get(rid)
                if row is None:
                    continue
                out_row = {"flag_reason": detail_by_id.get(rid) or signal, "record_id": rid}
                for field in other_fields:
                    out_row[field] = row.get(field, "")
                writer.writerow(out_row)

        written[signal] = filename

    return written
