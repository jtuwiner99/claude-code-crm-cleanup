from crm_report_card.scorers import band_index, score_employee_count, SCORERS


def test_band_index_groups_hubspot_style_bands():
    assert band_index(5) == band_index(10)
    assert band_index(11) == band_index(50)
    assert band_index(10) != band_index(11)
    assert band_index(20000) == band_index(50000)


def test_one_band_apart_is_not_a_mismatch():
    """Off by a little is not wrong. Off by a lot is."""
    rows = [{"record_id": "0", "stored_employee_count": "10",
             "verified_employee_count": "12", "source": "peopledatalabs"}]
    out = score_employee_count(rows)
    assert out["checked"] == 1
    assert out["mismatched"] == 0
    assert out["rate"] == 0.0


def test_two_or_more_bands_apart_is_a_mismatch():
    rows = [{"record_id": "0", "stored_employee_count": "10",
             "verified_employee_count": "900", "source": "peopledatalabs"}]
    out = score_employee_count(rows)
    assert out["checked"] == 1
    assert out["mismatched"] == 1
    assert out["rate"] == 1.0
    assert out["offending_ids"] == ["0"]
    assert "10" in out["examples"][0]["detail"]
    assert "900" in out["examples"][0]["detail"]


def test_provider_miss_is_unverifiable_not_a_mismatch():
    """The provider having no data is a different fact from the CRM being wrong."""
    rows = [
        {"record_id": "0", "stored_employee_count": "10",
         "verified_employee_count": "", "source": ""},
        {"record_id": "1", "stored_employee_count": "10",
         "verified_employee_count": "900", "source": "peopledatalabs"},
    ]
    out = score_employee_count(rows)
    assert out["unverifiable"] == 1
    assert out["checked"] == 1
    assert out["mismatched"] == 1
    assert out["rate"] == 1.0          # 1 of 1 checked, not 1 of 2 rows
    assert out["offending_ids"] == ["1"]


def test_blank_stored_value_is_skipped_not_scored():
    rows = [{"record_id": "0", "stored_employee_count": "",
             "verified_employee_count": "900", "source": "peopledatalabs"}]
    out = score_employee_count(rows)
    assert out["skipped_blank"] == 1
    assert out["checked"] == 0
    assert out["rate"] == 0.0


def test_unparseable_values_are_unverifiable_not_zero():
    rows = [{"record_id": "0", "stored_employee_count": "about 50",
             "verified_employee_count": "n/a", "source": "peopledatalabs"}]
    out = score_employee_count(rows)
    assert out["checked"] == 0
    assert out["unverifiable"] == 1


def test_examples_are_capped_at_twelve():
    rows = [{"record_id": str(i), "stored_employee_count": "5",
             "verified_employee_count": "9000", "source": "peopledatalabs"}
            for i in range(30)]
    out = score_employee_count(rows)
    assert out["mismatched"] == 30
    assert len(out["examples"]) == 12
    assert len(out["offending_ids"]) == 30


def test_example_detail_carries_self_reported_range_and_identity_method():
    """The evidence line must show the self-reported band next to the
    associated-member count, and how identity was confirmed, so a reader who
    sees 'stored 500, verified 16848' also sees 'self-reported 5001-10000'."""
    rows = [{"record_id": "0", "stored_employee_count": "500",
             "verified_employee_count": "16848", "source": "harvestapi via apify",
             "verified_range": "5001-10000", "identity_method": "website-match"}]
    out = score_employee_count(rows)
    detail = out["examples"][0]["detail"]
    assert "500" in detail
    assert "16848" in detail
    assert "self-reported 5001-10000" in detail
    assert "website-match" in detail


def test_example_detail_handles_missing_range_and_identity_method():
    """A mismatch can still be scored even when the range/method columns are
    blank; the detail line should say so rather than rendering garbage."""
    rows = [{"record_id": "0", "stored_employee_count": "10",
             "verified_employee_count": "900", "source": "harvestapi via apify"}]
    out = score_employee_count(rows)
    detail = out["examples"][0]["detail"]
    assert "no self-reported range" in detail
    assert "unknown identity method" in detail


def test_scorer_is_registered_under_its_unlock_key():
    assert SCORERS["employee_count_accuracy"] is score_employee_count


def test_infinity_values_are_unverifiable():
    """Non-finite floats like inf/-inf/Infinity raise OverflowError in int().
    These should be treated as unverifiable, not crash the scorer."""
    rows = [
        {"record_id": "0", "stored_employee_count": "inf",
         "verified_employee_count": "100", "source": "peopledatalabs"},
        {"record_id": "1", "stored_employee_count": "50",
         "verified_employee_count": "-inf", "source": "peopledatalabs"},
        {"record_id": "2", "stored_employee_count": "Infinity",
         "verified_employee_count": "200", "source": "peopledatalabs"},
    ]
    out = score_employee_count(rows)
    assert out["checked"] == 0
    assert out["unverifiable"] == 3
    assert out["mismatched"] == 0


def test_exactly_two_bands_apart_is_a_mismatch():
    """The threshold is >= 2 bands apart. Verify exactly 2 bands is a mismatch.
    Band 0 (1-10) and Band 2 (51-200) are exactly 2 bands apart.
    band_index(10) = 0, band_index(100) = 2, abs(0-2) = 2 >= 2."""
    rows = [{"record_id": "0", "stored_employee_count": "10",
             "verified_employee_count": "100", "source": "peopledatalabs"}]
    out = score_employee_count(rows)
    assert out["checked"] == 1
    assert out["mismatched"] == 1
    assert out["rate"] == 1.0
    assert out["offending_ids"] == ["0"]


def test_band_index_out_of_range_returns_negative_one():
    """band_index is a public interface. Out-of-range values should return
    a defensible value (-1) rather than silently reporting the largest band."""
    assert band_index(0) == -1
    assert band_index(-5) == -1
    assert band_index(-1000) == -1


def test_middle_band_boundaries():
    """Verify boundaries of middle bands are correctly defined.
    Band 2: 51-200, Band 3: 201-500, Band 4: 501-1000, Band 5: 1001-5000, Band 6: 5001-10000."""
    # Band 2: 51-200
    assert band_index(50) == 1
    assert band_index(51) == 2
    assert band_index(200) == 2
    assert band_index(201) == 3
    # Band 3: 201-500
    assert band_index(200) == 2
    assert band_index(201) == 3
    assert band_index(500) == 3
    assert band_index(501) == 4
    # Band 4: 501-1000
    assert band_index(500) == 3
    assert band_index(501) == 4
    assert band_index(1000) == 4
    assert band_index(1001) == 5
    # Band 5: 1001-5000
    assert band_index(1000) == 4
    assert band_index(1001) == 5
    assert band_index(5000) == 5
    assert band_index(5001) == 6
    # Band 6: 5001-10000
    assert band_index(5000) == 5
    assert band_index(5001) == 6
    assert band_index(10000) == 6
    assert band_index(10001) == 7
