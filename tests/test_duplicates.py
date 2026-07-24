from crm_report_card.checks.duplicates import check_duplicates


def test_exact_domain_dupes():
    recs = [
        {"record_id": "0", "domain": "acme.com", "company_name": "Acme Inc"},
        {"record_id": "1", "domain": "acme.com", "company_name": "Acme Incorporated"},
        {"record_id": "2", "domain": "globex.io", "company_name": "Globex"},
    ]
    out = check_duplicates(recs)
    assert out["total_records"] == 3
    assert out["exact_domain_dupes"] == 1
    assert out["duplicate_records"] == 1
    assert abs(out["duplicate_rate"] - 1 / 3) < 1e-9
    assert len(out["offending_ids"]) == out["duplicate_records"]
    assert out["offending_ids"] == ["1"]
    assert len(out["examples"]) <= 12
    assert len(out["examples"]) == 1
    ex = out["examples"][0]
    assert set(ex.keys()) == {"record_id", "label", "detail"}
    assert ex["record_id"] == "1"
    assert "acme.com" in ex["detail"]


def test_fuzzy_name_dupes_when_no_domain():
    recs = [
        {"record_id": "0", "domain": "", "company_name": "Northwind Traders"},
        {"record_id": "1", "domain": "", "company_name": "Northwind Traders LLC"},
    ]
    out = check_duplicates(recs)
    assert out["fuzzy_name_dupes"] == 1
    assert out["duplicate_records"] == 1
    assert len(out["offending_ids"]) == out["duplicate_records"]
    assert out["offending_ids"] == ["1"]
    assert len(out["examples"]) == 1
    assert out["examples"][0]["record_id"] == "1"
    assert "Northwind Traders" in out["examples"][0]["detail"]


def test_no_dupes_empty():
    out = check_duplicates([])
    assert out["duplicate_rate"] == 0.0
    assert out["offending_ids"] == []
    assert out["examples"] == []


def test_suffix_variants_are_dupes():
    recs = [
        {"record_id": "0", "domain": "", "company_name": "Acme"},
        {"record_id": "1", "domain": "", "company_name": "Acme Inc"},
        {"record_id": "2", "domain": "", "company_name": "Acme Incorporated"},
        {"record_id": "3", "domain": "", "company_name": "Acme LLC"},
    ]
    assert check_duplicates(recs)["fuzzy_name_dupes"] == 3


def test_distinct_companies_not_dupes():
    recs = [
        {"record_id": "0", "domain": "", "company_name": "Northwind Traders"},
        {"record_id": "1", "domain": "", "company_name": "Southwind Freight"},
    ]
    assert check_duplicates(recs)["fuzzy_name_dupes"] == 0


def test_leading_legal_word_not_stripped():
    recs = [
        {"record_id": "0", "domain": "", "company_name": "Co Star"},
        {"record_id": "1", "domain": "", "company_name": "Star"},
    ]
    # 'co' is a leading word here, not a trailing legal suffix; must not merge these
    assert check_duplicates(recs)["fuzzy_name_dupes"] == 0


def test_contact_mode_unique_emails_same_domain_not_dupes():
    # Regression: five real distinct people at @acme.com must not be flagged
    # as duplicates in contact mode (dedup is on email identity, not domain).
    recs = [
        {"record_id": "0", "domain": "acme.com", "company_name": "Acme", "email": "jane@acme.com"},
        {"record_id": "1", "domain": "acme.com", "company_name": "Acme", "email": "john@acme.com"},
        {"record_id": "2", "domain": "acme.com", "company_name": "Acme", "email": "sue@acme.com"},
        {"record_id": "3", "domain": "acme.com", "company_name": "Acme", "email": "bob@acme.com"},
        {"record_id": "4", "domain": "acme.com", "company_name": "Acme", "email": "amy@acme.com"},
    ]
    out = check_duplicates(recs, object_type="contact")
    assert out["duplicate_records"] == 0
    assert out["exact_domain_dupes"] == 0
    assert out["fuzzy_name_dupes"] == 0
    assert out["offending_ids"] == []
    assert out["examples"] == []


def test_contact_mode_repeated_email_is_dupe():
    recs = [
        {"record_id": "0", "domain": "acme.com", "company_name": "Acme", "email": "jane@acme.com"},
        {"record_id": "1", "domain": "acme.com", "company_name": "Acme", "email": "Jane@Acme.com "},
    ]
    out = check_duplicates(recs, object_type="contact")
    assert out["duplicate_records"] == 1
    assert abs(out["duplicate_rate"] - 0.5) < 1e-9
    assert len(out["offending_ids"]) == out["duplicate_records"]
    assert out["offending_ids"] == ["1"]
    assert len(out["examples"]) == 1
    assert out["examples"][0]["label"] == "jane@acme.com"
    assert "jane@acme.com" in out["examples"][0]["detail"]


def test_all_suffix_name_falls_back():
    recs = [
        {"record_id": "0", "domain": "", "company_name": "Company Inc"},
        {"record_id": "1", "domain": "", "company_name": "Company Inc"},
    ]
    # all-suffix name falls back to full normalized form instead of empty -> still a dupe
    assert check_duplicates(recs)["fuzzy_name_dupes"] == 1
