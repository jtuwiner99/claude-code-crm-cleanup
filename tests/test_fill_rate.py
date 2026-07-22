from crm_report_card.checks.fill_rate import check_fill_rate


def test_fill_rate_counts_blanks():
    recs = [
        {"email": "a@b.co", "company_size": "10"},
        {"email": "", "company_size": "20"},
        {"email": "c@d.co", "company_size": ""},
    ]
    out = check_fill_rate(recs, ["email", "company_size"])
    assert out["per_field"]["email"]["filled"] == 2
    assert out["per_field"]["email"]["missing"] == 1
    assert abs(out["per_field"]["email"]["fill_rate"] - 2 / 3) < 1e-9
    assert abs(out["overall_missing_rate"] - 2 / 6) < 1e-9


def test_fill_rate_empty_records():
    out = check_fill_rate([], ["email"])
    assert out["overall_missing_rate"] == 0.0
