"""Score a play's per-row output into a fragment body.

The play fetches, the scorer judges. Keeping judgment here means the grading
rule is covered by the offline suite, and a provider bake-off compares
candidates through one identical scorer.
"""
from __future__ import annotations

_MAX_EXAMPLES = 12

# HubSpot-style headcount bands. A stored value and a verified value in the
# same band, or in adjacent bands, are not a contradiction. Two or more bands
# apart is.
SIZE_BANDS = (
    (1, 10, "1-10"),
    (11, 50, "11-50"),
    (51, 200, "51-200"),
    (201, 500, "201-500"),
    (501, 1000, "501-1000"),
    (1001, 5000, "1001-5000"),
    (5001, 10000, "5001-10000"),
    (10001, 10 ** 9, "10001+"),
)


def band_index(value: int) -> int:
    if value <= 0:
        return -1
    for i, (low, high, _label) in enumerate(SIZE_BANDS):
        if low <= value <= high:
            return i
    return len(SIZE_BANDS) - 1


def _to_int(text):
    try:
        val = int(float(str(text).replace(",", "").strip()))
    except (ValueError, TypeError, OverflowError):
        return None
    return val if val > 0 else None


def score_employee_count(rows: list[dict]) -> dict:
    """Compare stored headcount against the verified headcount, band to band."""
    checked = 0
    mismatched = 0
    unverifiable = 0
    skipped_blank = 0
    offending_ids: list[str] = []
    examples: list[dict] = []
    # Which provider actually produced each comparable value. A waterfall play
    # returns rows from more than one provider, so citing only the first one
    # configured would misattribute most of the sample.
    source_counts: dict[str, int] = {}

    for row in rows:
        rid = row.get("record_id", "")
        stored_raw = (row.get("stored_employee_count") or "").strip()
        verified_raw = (row.get("verified_employee_count") or "").strip()

        if not stored_raw:
            # Already counted as a completeness defect by the free scan.
            skipped_blank += 1
            continue

        stored = _to_int(stored_raw)
        verified = _to_int(verified_raw)
        if stored is None or verified is None:
            unverifiable += 1
            continue

        checked += 1
        # A blank source is not attributed to anyone: it is a comparable value
        # with no citation, never a tally for the first provider in the list.
        source = (row.get("source") or "").strip()
        if source:
            source_counts[source] = source_counts.get(source, 0) + 1
        if abs(band_index(stored) - band_index(verified)) >= 2:
            mismatched += 1
            offending_ids.append(rid)
            if len(examples) < _MAX_EXAMPLES:
                examples.append({
                    "record_id": rid,
                    "label": (row.get("domain") or row.get("company_name") or rid),
                    "detail": (f"stored {stored}, verified {verified} "
                               f"({row.get('source') or 'unknown source'})"),
                })

    return {
        "checked": checked,
        "mismatched": mismatched,
        "rate": (mismatched / checked) if checked else 0.0,
        "unverifiable": unverifiable,
        "skipped_blank": skipped_blank,
        "source_counts": source_counts,
        "examples": examples,
        "offending_ids": offending_ids,
    }


SCORERS = {
    "employee_count_accuracy": score_employee_count,
}
