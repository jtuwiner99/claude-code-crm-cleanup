from crm_report_card.checks.junk import check_junk


def test_free_mail_as_company():
    recs = [{"record_id": "0", "domain": "gmail.com", "company_name": "Bob", "email": "bob@gmail.com"}]
    out = check_junk(recs)
    assert out["free_mail_as_company"] == 1
    assert out["total_junk"] == 1
    assert out["offending_ids"] == ["0"]
    assert len(out["examples"]) == 1
    ex = out["examples"][0]
    assert set(ex.keys()) == {"record_id", "label", "detail"}
    assert ex["record_id"] == "0"
    assert "free-mail domain as company" in ex["detail"]


def test_generic_contact_and_test_record():
    recs = [
        {"record_id": "0", "domain": "globex.io", "company_name": "Globex", "email": "info@globex.io"},
        {"record_id": "1", "domain": "test.com", "company_name": "Test Co", "email": "qa@test.com"},
    ]
    out = check_junk(recs)
    assert out["generic_contacts"] == 1
    assert out["test_records"] == 1
    assert out["total_junk"] == 2
    assert len(out["offending_ids"]) == out["total_junk"]
    assert set(out["offending_ids"]) == {"0", "1"}
    assert len(out["examples"]) == 2
    details = {ex["record_id"]: ex["detail"] for ex in out["examples"]}
    assert "generic inbox" in details["0"]
    assert "test/demo record" in details["1"]


def test_clean_record_not_junk():
    recs = [{"record_id": "0", "domain": "acme.com", "company_name": "Acme", "email": "jane@acme.com"}]
    out = check_junk(recs)
    assert out["total_junk"] == 0
    assert out["offending_ids"] == []
    assert out["examples"] == []


def test_legit_names_with_embedded_tokens_not_junk():
    recs = [
        {"record_id": "0", "domain": "attestation.com", "company_name": "Attestation Inc", "email": "amy@attestation.com"},
        {"record_id": "1", "domain": "democracylabs.org", "company_name": "Democracy Labs", "email": "ben@democracylabs.org"},
    ]
    out = check_junk(recs)
    assert out["test_records"] == 0
    assert out["total_junk"] == 0


def test_real_test_records_still_flagged():
    recs = [
        {"record_id": "0", "domain": "acme.com", "company_name": "Test Co", "email": "jane@acme.com"},
        {"record_id": "1", "domain": "acme.com", "company_name": "Acme", "email": "demo@example.com"},
    ]
    out = check_junk(recs)
    assert out["test_records"] == 2
