"""Orphaned contact detection: a contact with no associated company."""
from __future__ import annotations

_MAX_EXAMPLES = 12


def check_orphaned(records: list[dict]) -> dict:
    total = len(records)
    orphaned_count = 0
    offending_ids: list[str] = []
    examples: list[dict] = []
    for rec in records:
        name = (rec.get("company_name") or "").strip()
        if not name:
            orphaned_count += 1
            rid = rec.get("record_id", "")
            offending_ids.append(rid)
            if len(examples) < _MAX_EXAMPLES:
                label = (rec.get("email") or "").strip() or rid
                examples.append({
                    "record_id": rid,
                    "label": label,
                    "detail": "no associated company",
                })
    return {
        "orphaned_count": orphaned_count,
        "orphaned_rate": (orphaned_count / total) if total else 0.0,
        "examples": examples,
        "offending_ids": offending_ids,
    }
