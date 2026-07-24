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
    # 2 records are missing at least one critical field (record 1 missing email,
    # record 2 missing company_size)
    assert len(out["offending_ids"]) == 2
    assert len(out["examples"]) <= 12
    assert len(out["examples"]) == 2
    for ex in out["examples"]:
        assert set(ex.keys()) == {"record_id", "label", "detail"}
        assert ex["detail"].startswith("missing: ")


def test_fill_rate_empty_records():
    out = check_fill_rate([], ["email"])
    assert out["overall_missing_rate"] == 0.0
    assert out["offending_ids"] == []
    assert out["examples"] == []


def test_fill_rate_offending_ids_use_record_id():
    recs = [
        {"record_id": "a1", "email": "a@b.co", "company_size": "10"},
        {"record_id": "a2", "email": "", "company_size": "20"},
    ]
    out = check_fill_rate(recs, ["email", "company_size"])
    assert out["offending_ids"] == ["a2"]
    assert out["examples"][0]["record_id"] == "a2"
    assert "email" in out["examples"][0]["detail"]
