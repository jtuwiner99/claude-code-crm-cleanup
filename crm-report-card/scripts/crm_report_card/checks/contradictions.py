"""Internal contradictions: stated size vs. observed contact count."""
from __future__ import annotations
from collections import defaultdict

_MAX_EXAMPLES = 12


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
    offending_ids: list[str] = []
    examples: list[dict] = []
    for dom, group in groups.items():
        contacts = {(r.get("email") or "").strip().lower() for r in group if (r.get("email") or "").strip()}
        sizes = [_to_int(r.get("company_size", "")) for r in group]
        size = next((s for s in sizes if s is not None), None)
        if size is not None and len(contacts) > size:
            for r in group:
                rid = r.get("record_id", "")
                if rid not in bad_ids:
                    bad_ids.add(rid)
                    offending_ids.append(rid)
            if len(examples) < _MAX_EXAMPLES:
                examples.append({
                    "record_id": group[0].get("record_id", ""),
                    "label": dom,
                    "detail": f"size says {size} but {len(contacts)} distinct contacts",
                })

    count = len(bad_ids)
    return {
        "count": count,
        "rate": (count / total) if total else 0.0,
        "examples": examples,
        "offending_ids": offending_ids,
    }
