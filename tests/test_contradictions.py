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


def test_no_contradiction_when_size_large():
    recs = [
        {"record_id": "0", "domain": "big.co", "company_size": "5000", "email": "a@big.co"},
        {"record_id": "1", "domain": "big.co", "company_size": "5000", "email": "b@big.co"},
    ]
    assert check_contradictions(recs)["count"] == 0
