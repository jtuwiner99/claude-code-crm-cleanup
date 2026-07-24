from crm_report_card.checks.contradictions import check_contradictions


def test_size_vs_contact_count_contradiction():
    recs = [
        {"record_id": "0", "domain": "tiny.co", "company_size": "1", "email": "a@tiny.co"},
        {"record_id": "1", "domain": "tiny.co", "company_size": "1", "email": "b@tiny.co"},
        {"record_id": "2", "domain": "tiny.co", "company_size": "1", "email": "c@tiny.co"},
    ]
    out = check_contradictions(recs)
    assert out["count"] == 3
    assert len(out["examples"]) >= 1
    assert len(out["examples"]) <= 12
    assert len(out["offending_ids"]) == out["count"]
    assert set(out["offending_ids"]) == {"0", "1", "2"}
    ex = out["examples"][0]
    assert set(ex.keys()) == {"record_id", "label", "detail"}
    assert ex["label"] == "tiny.co"
    assert "size says 1 but 3 distinct contacts" in ex["detail"]


def test_no_contradiction_when_size_large():
    recs = [
        {"record_id": "0", "domain": "big.co", "company_size": "5000", "email": "a@big.co"},
        {"record_id": "1", "domain": "big.co", "company_size": "5000", "email": "b@big.co"},
    ]
    out = check_contradictions(recs)
    assert out["count"] == 0
    assert out["offending_ids"] == []
    assert out["examples"] == []
