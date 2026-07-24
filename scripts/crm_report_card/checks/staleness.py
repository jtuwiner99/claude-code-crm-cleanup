"""Staleness: records untouched for >= N months."""
from __future__ import annotations
from datetime import date, datetime

_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S")
_MAX_EXAMPLES = 12


def _parse(text: str):
    text = (text or "").strip()
    if not text:
        return None
    for fmt in _FORMATS:
        try:
            return datetime.strptime(text[:len(text)], fmt).date() if fmt != "%Y-%m-%dT%H:%M:%S" \
                else datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    return None


def check_staleness(records: list[dict], today: date, months: int = 12) -> dict:
    total = len(records)
    cutoff_ordinal = today.toordinal() - int(months * 30.44)
    stale = 0
    unparseable = 0
    offending_ids: list[str] = []
    examples: list[dict] = []
    for rec in records:
        raw = rec.get("last_activity", "")
        parsed = _parse(raw)
        if parsed is None:
            unparseable += 1
            continue
        if parsed.toordinal() < cutoff_ordinal:
            stale += 1
            rid = rec.get("record_id", "")
            offending_ids.append(rid)
            if len(examples) < _MAX_EXAMPLES:
                label = (rec.get("company_name") or "").strip() or rid
                examples.append({
                    "record_id": rid,
                    "label": label,
                    "detail": f"last activity {raw}",
                })
    return {
        "stale_count": stale,
        "stale_rate": (stale / total) if total else 0.0,
        "cutoff_months": months,
        "unparseable": unparseable,
        "examples": examples,
        "offending_ids": offending_ids,
    }
