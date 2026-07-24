"""Load a CRM CSV into normalized {role: value} records."""
from __future__ import annotations
import csv
from .field_mapping import resolve_mapping


def load_records(csv_path: str, overrides: dict[str, str],
                 extra_columns=(), object_type: str = "company") -> tuple[list[dict], dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        mapping = resolve_mapping(headers, overrides)
        has_id = "record_id" in mapping
        header_set = set(headers)
        extras = [col for col in extra_columns if col in header_set]
        records: list[dict] = []
        for idx, row in enumerate(reader):
            rec: dict[str, str] = {}
            for role, header in mapping.items():
                rec[role] = (row.get(header) or "").strip()
            for col in extras:
                rec[col] = (row.get(col) or "").strip()
            if not has_id or not rec.get("record_id"):
                rec["record_id"] = str(idx)
            if object_type == "contact" and not rec.get("domain") and "@" in rec.get("email", ""):
                rec["domain"] = rec["email"].split("@", 1)[1].strip().lower()
            records.append(rec)
    return records, mapping
