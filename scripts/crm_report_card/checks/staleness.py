"""Staleness: records untouched for >= N months."""
from __future__ import annotations
from datetime import date, datetime

_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S")


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
    for rec in records:
        parsed = _parse(rec.get("last_activity", ""))
        if parsed is None:
            unparseable += 1
            continue
        if parsed.toordinal() < cutoff_ordinal:
            stale += 1
    return {
        "stale_count": stale,
        "stale_rate": (stale / total) if total else 0.0,
        "cutoff_months": months,
        "unparseable": unparseable,
    }
