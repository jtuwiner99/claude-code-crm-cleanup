"""Orphaned contact detection: a contact with no associated company."""
from __future__ import annotations

_MAX_EXAMPLES = 12


def check_orphaned(records: list[dict]) -> dict:
    """Flag contacts with no associated company.

    Prefers the real association (`associated_company_id`) and only falls back
    to the denormalized `company_name` text field when the export has no
    association column. HubSpot contacts frequently carry a valid association
    while that text field sits blank, so grading on the name alone overstated
    the orphan rate several-fold.
    """
    total = len(records)
    # Only trust the association field if the export actually carries it.
    has_assoc_column = any((rec.get("associated_company_id") or "").strip() for rec in records)
    orphaned_count = 0
    offending_ids: list[str] = []
    examples: list[dict] = []
    for rec in records:
        if has_assoc_column:
            linked = (rec.get("associated_company_id") or "").strip()
        else:
            linked = (rec.get("company_name") or "").strip()
        if not linked:
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
