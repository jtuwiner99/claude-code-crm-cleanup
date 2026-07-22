"""Internal contradictions: stated size vs. observed contact count."""
from __future__ import annotations
from collections import defaultdict


def _to_int(text: str):
    try:
        val = int(float(str(text).replace(",", "").strip()))
        return val if val > 0 else None
    except (ValueError, TypeError):
        return None


def check_contradictions(records: list[dict]) -> dict:
    total = len(records)
    groups: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        dom = (rec.get("domain") or "").strip().lower()
        if dom:
            groups[dom].append(rec)

    bad_ids: set[str] = set()
    examples: list[str] = []
    for dom, group in groups.items():
        contacts = {(r.get("email") or "").strip().lower() for r in group if (r.get("email") or "").strip()}
        sizes = [_to_int(r.get("company_size", "")) for r in group]
        size = next((s for s in sizes if s is not None), None)
        if size is not None and len(contacts) > size:
            for r in group:
                bad_ids.add(r["record_id"])
            if len(examples) < 5:
                examples.append(f"{dom}: size says {size} but {len(contacts)} distinct contacts")

    count = len(bad_ids)
    return {"count": count, "rate": (count / total) if total else 0.0, "examples": examples}
