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


def test_fuzzy_name_dupes_when_no_domain():
    recs = [
        {"record_id": "0", "domain": "", "company_name": "Northwind Traders"},
        {"record_id": "1", "domain": "", "company_name": "Northwind Traders LLC"},
    ]
    out = check_duplicates(recs)
    assert out["fuzzy_name_dupes"] == 1
    assert out["duplicate_records"] == 1


def test_no_dupes_empty():
    assert check_duplicates([])["duplicate_rate"] == 0.0
