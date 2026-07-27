"""Fill-rate for the critical fields the user named."""
from __future__ import annotations

_MAX_EXAMPLES = 12


def check_fill_rate(records: list[dict], critical_properties: list[str]) -> dict:
    total = len(records)
    per_field: dict[str, dict] = {}
    missing_cells = 0
    for role in critical_properties:
        filled = sum(1 for r in records if (r.get(role) or "").strip())
        missing = total - filled
        missing_cells += missing
        per_field[role] = {
            "filled": filled,
            "missing": missing,
            "fill_rate": (filled / total) if total else 0.0,
        }
    denom = total * len(critical_properties)

    offending_ids: list[str] = []
    examples: list[dict] = []
    for rec in records:
        missing_fields = [role for role in critical_properties if not (rec.get(role) or "").strip()]
        if not missing_fields:
            continue
        rid = rec.get("record_id", "")
        offending_ids.append(rid)
        if len(examples) < _MAX_EXAMPLES:
            label = (rec.get("company_name") or "").strip() or (rec.get("email") or "").strip() or rid
            examples.append({
                "record_id": rid,
                "label": label,
                "detail": f"missing: {', '.join(missing_fields)}",
            })

    return {
        "per_field": per_field,
        "overall_missing_rate": (missing_cells / denom) if denom else 0.0,
        "examples": examples,
        "offending_ids": offending_ids,
    }
