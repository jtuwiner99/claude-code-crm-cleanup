"""Staleness: records untouched for >= N months."""
from __future__ import annotations
from datetime import date, datetime

# Ordered most-specific first. HubSpot CSV exports use a SPACE separator
# ("2026-04-24 18:02"), not the ISO "T" — omitting that silently sent every
# date to `unparseable`, which the rate then skipped, grading a fully stale
# book as A. Normalizing "T" to a space lets one set of formats cover both.
_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
)
_MAX_EXAMPLES = 12


def _parse(text: str):
    text = (text or "").strip()
    if not text:
        return None
    # Treat the ISO "T" separator and a trailing "Z" as the space-separated form.
    normalized = text.replace("T", " ", 1)
    if normalized.endswith("Z"):
        normalized = normalized[:-1].strip()
    for fmt in _FORMATS:
        try:
            return datetime.strptime(normalized, fmt).date()
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
