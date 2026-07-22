from crm_report_card.checks.junk import check_junk


def test_free_mail_as_company():
    recs = [{"record_id": "0", "domain": "gmail.com", "company_name": "Bob", "email": "bob@gmail.com"}]
    out = check_junk(recs)
    assert out["free_mail_as_company"] == 1
    assert out["total_junk"] == 1


def test_generic_contact_and_test_record():
    recs = [
        {"record_id": "0", "domain": "globex.io", "company_name": "Globex", "email": "info@globex.io"},
        {"record_id": "1", "domain": "test.com", "company_name": "Test Co", "email": "qa@test.com"},
    ]
    out = check_junk(recs)
    assert out["generic_contacts"] == 1
    assert out["test_records"] == 1
    assert out["total_junk"] == 2


def test_clean_record_not_junk():
    recs = [{"record_id": "0", "domain": "acme.com", "company_name": "Acme", "email": "jane@acme.com"}]
    assert check_junk(recs)["total_junk"] == 0
