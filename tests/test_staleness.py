from datetime import date
from crm_report_card.checks.staleness import check_staleness


def test_stale_and_fresh():
    recs = [
        {"last_activity": "2021-01-01"},   # stale vs 2026
        {"last_activity": "2026-06-01"},   # fresh
        {"last_activity": ""},             # unparseable
    ]
    out = check_staleness(recs, today=date(2026, 7, 22), months=12)
    assert out["stale_count"] == 1
    assert out["unparseable"] == 1
    assert abs(out["stale_rate"] - 1 / 3) < 1e-9


def test_accepts_us_dates():
    recs = [{"last_activity": "01/15/2020"}]
    out = check_staleness(recs, today=date(2026, 7, 22))
    assert out["stale_count"] == 1
