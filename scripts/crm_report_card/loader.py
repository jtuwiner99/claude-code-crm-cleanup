"""Load a CRM CSV into normalized {role: value} records."""
from __future__ import annotations
import csv
from .field_mapping import resolve_mapping


def load_records(csv_path: str, overrides: dict[str, str]) -> tuple[list[dict], dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        mapping = resolve_mapping(headers, overrides)
        has_id = "record_id" in mapping
        records: list[dict] = []
        for idx, row in enumerate(reader):
            rec: dict[str, str] = {}
            for role, header in mapping.items():
                rec[role] = (row.get(header) or "").strip()
            if not has_id or not rec.get("record_id"):
                rec["record_id"] = str(idx)
            records.append(rec)
    return records, mapping
