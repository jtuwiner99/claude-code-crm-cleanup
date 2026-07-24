from datetime import date
from crm_report_card.checks.staleness import check_staleness


def test_stale_and_fresh():
    recs = [
        {"record_id": "0", "last_activity": "2021-01-01"},   # stale vs 2026
        {"record_id": "1", "last_activity": "2026-06-01"},   # fresh
        {"record_id": "2", "last_activity": ""},             # unparseable
    ]
    out = check_staleness(recs, today=date(2026, 7, 22), months=12)
    assert out["stale_count"] == 1
    assert out["unparseable"] == 1
    assert abs(out["stale_rate"] - 1 / 3) < 1e-9
    assert len(out["offending_ids"]) == out["stale_count"]
    assert out["offending_ids"] == ["0"]
    assert len(out["examples"]) == 1
    ex = out["examples"][0]
    assert set(ex.keys()) == {"record_id", "label", "detail"}
    assert ex["record_id"] == "0"
    assert "2021-01-01" in ex["detail"]


def test_no_offending_when_nothing_stale():
    recs = [{"record_id": "0", "last_activity": "2026-06-01"}]
    out = check_staleness(recs, today=date(2026, 7, 22), months=12)
    assert out["stale_count"] == 0
    assert out["offending_ids"] == []
    assert out["examples"] == []


def test_accepts_us_dates():
    recs = [{"record_id": "0", "last_activity": "01/15/2020"}]
    out = check_staleness(recs, today=date(2026, 7, 22))
    assert out["stale_count"] == 1
    assert out["offending_ids"] == ["0"]
