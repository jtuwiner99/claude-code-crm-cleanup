from crm_report_card.checks.orphaned import check_orphaned


def test_orphaned_counts_blank_company_name():
    recs = [
        {"record_id": "0", "company_name": "Acme"},
        {"record_id": "1", "company_name": ""},
        {"record_id": "2"},
    ]
    out = check_orphaned(recs)
    assert out["orphaned_count"] == 2
    assert out["orphaned_rate"] == 2 / 3
    assert len(out["offending_ids"]) == out["orphaned_count"]
    assert out["offending_ids"] == ["1", "2"]
    assert len(out["examples"]) == 2
    for ex in out["examples"]:
        assert set(ex.keys()) == {"record_id", "label", "detail"}
        assert ex["detail"] == "no associated company"


def test_orphaned_no_records_is_zero():
    out = check_orphaned([])
    assert out["orphaned_count"] == 0
    assert out["orphaned_rate"] == 0.0
    assert out["offending_ids"] == []
    assert out["examples"] == []


def test_orphaned_none_orphaned():
    recs = [{"record_id": "0", "company_name": "Acme"}, {"record_id": "1", "company_name": "Globex"}]
    out = check_orphaned(recs)
    assert out["orphaned_count"] == 0
    assert out["orphaned_rate"] == 0.0
    assert out["offending_ids"] == []
    assert out["examples"] == []
