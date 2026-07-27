import pytest
from crm_report_card.unlock import (validate_fragment, merge_fragment,
                                    accuracy_grade, is_measurable,
                                    ACCURACY_UNLOCKS)


def _frag(**over):
    base = {
        "unlock": "employee_count_accuracy",
        "object_type": "company",
        "sample_size": 100,
        "checked": 92,
        "mismatched": 30,
        "rate": 0.326,
        "unverifiable": 8,
        "skipped_blank": 0,
        "examples": [{"record_id": "1", "label": "acme.com", "detail": "stored 10, verified 900"}],
        "offending_ids": ["1"],
        "provider": "peopledatalabs (61), exa (31)",
        "run_at": "2026-07-27",
        "comparison_rule": "mismatch = stored and verified fall two or more size bands apart",
    }
    base.update(over)
    return base


def _metrics():
    return {"object_type": "company", "counts": {"records": 657},
            "facts": {"duplicates": {"duplicate_rate": 0.02, "grade": "B"}},
            "overall_grade": "D"}


def test_valid_fragment_has_no_errors():
    assert validate_fragment(_frag()) == []


def test_unknown_unlock_key_is_rejected():
    errors = validate_fragment(_frag(unlock="not_a_real_unlock"))
    assert any("not_a_real_unlock" in e for e in errors)


def test_missing_unverifiable_is_rejected():
    """Dropping the unverifiable count would hide the provider's coverage gap."""
    bad = _frag()
    del bad["unverifiable"]
    assert any("unverifiable" in e for e in validate_fragment(bad))


def test_merge_places_the_fragment_under_its_unlock_key():
    out = merge_fragment(_metrics(), _frag())
    assert "employee_count_accuracy" in out["facts"]
    assert out["facts"]["employee_count_accuracy"]["grade"] == "F"


def test_merge_does_not_touch_the_completeness_grade():
    before = _metrics()
    out = merge_fragment(before, _frag())
    assert out["overall_grade"] == "D"
    assert out["facts"]["duplicates"]["grade"] == "B"


def test_merging_twice_does_not_double_count():
    out = merge_fragment(merge_fragment(_metrics(), _frag()), _frag())
    assert out["facts"]["employee_count_accuracy"]["mismatched"] == 30


def test_merge_rejects_a_fragment_for_the_wrong_object():
    with pytest.raises(ValueError, match="object_type"):
        merge_fragment(_metrics(), _frag(object_type="contact"))


def test_merge_rejects_metrics_with_no_object_type():
    stale = _metrics()
    del stale["object_type"]
    with pytest.raises(ValueError, match="re-run the scan"):
        merge_fragment(stale, _frag())


def test_merge_does_not_mutate_the_input_metrics():
    original = _metrics()
    merge_fragment(original, _frag())
    assert "employee_count_accuracy" not in original["facts"]


def test_accuracy_grade_is_none_before_any_unlock():
    assert accuracy_grade(_metrics()) is None


def test_accuracy_grade_averages_only_accuracy_facts():
    out = merge_fragment(_metrics(), _frag(rate=0.005))
    assert accuracy_grade(out) == "A"


def _nothing_comparable(**over):
    """The provider returned nothing usable: rate collapses to 0.0, which
    grade_rate would happily call an A."""
    base = dict(checked=0, mismatched=0, rate=0.0, unverifiable=100)
    base.update(over)
    return _frag(**base)


def test_a_fact_that_compared_nothing_is_not_measurable():
    assert is_measurable(_frag()) is True
    assert is_measurable(_nothing_comparable()) is False
    # Every stored value blank is the same failure by a different route.
    assert is_measurable(_nothing_comparable(unverifiable=0, skipped_blank=100)) is False


def test_merging_a_run_that_compared_nothing_produces_no_grade():
    """A 0.0 rate out of 0 comparisons is not an A. It is not a grade at all."""
    out = merge_fragment(_metrics(), _nothing_comparable())
    fact = out["facts"]["employee_count_accuracy"]
    assert "grade" not in fact
    assert fact["measurable"] is False


def test_a_not_measurable_fact_does_not_contribute_to_the_accuracy_grade():
    out = merge_fragment(_metrics(), _nothing_comparable())
    assert accuracy_grade(out) is None


def test_a_not_measurable_fact_cannot_lift_a_real_accuracy_grade():
    """Even carrying a stale grade key, a not-measurable fact is ignored."""
    out = merge_fragment(_metrics(), _nothing_comparable())
    out["facts"]["employee_count_accuracy"]["grade"] = "A"
    assert accuracy_grade(out) is None


def test_a_measurable_run_still_grades_normally():
    out = merge_fragment(_metrics(), _frag())
    assert out["facts"]["employee_count_accuracy"]["measurable"] is True
    assert accuracy_grade(out) == "F"


def test_missing_comparison_rule_is_rejected():
    """Without the rule the card prints a rate nobody can check."""
    bad = _frag()
    del bad["comparison_rule"]
    assert any("comparison_rule" in e for e in validate_fragment(bad))


def test_accuracy_unlock_keys_are_the_three_locked_rows():
    assert ACCURACY_UNLOCKS == ("employee_count_accuracy", "email_deliverability",
                                "still_employed")
