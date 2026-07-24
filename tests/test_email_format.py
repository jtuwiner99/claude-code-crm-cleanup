from crm_report_card.checks.email_format import check_email_format


def test_blank_email_not_invalid():
    recs = [{"record_id": "0", "email": ""}, {"record_id": "1"}]
    out = check_email_format(recs)
    assert out["invalid_count"] == 0
    assert out["invalid_rate"] == 0.0


def test_bad_format_email_counted_invalid():
    recs = [
        {"record_id": "0", "email": "jane@acme.com"},
        {"record_id": "1", "email": "not-an-email"},
        {"record_id": "2", "email": "missing-domain@"},
    ]
    out = check_email_format(recs)
    assert out["invalid_count"] == 2
    assert out["invalid_rate"] == 2 / 3


def test_no_records_is_zero():
    out = check_email_format([])
    assert out["invalid_count"] == 0
    assert out["invalid_rate"] == 0.0
