"""Orphaned contact detection: a contact with no associated company."""
from __future__ import annotations


def check_orphaned(records: list[dict]) -> dict:
    total = len(records)
    orphaned_count = 0
    for rec in records:
        name = (rec.get("company_name") or "").strip()
        if not name:
            orphaned_count += 1
    return {
        "orphaned_count": orphaned_count,
        "orphaned_rate": (orphaned_count / total) if total else 0.0,
    }
