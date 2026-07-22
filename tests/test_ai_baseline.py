# tests/test_ai_baseline.py
import pytest
from crm_report_card.ai_baseline import validate_ai_baseline, merge_ai_baseline


def test_validate_forces_unverified():
    block = validate_ai_baseline({
        "qualified_estimate": 0.34,
        "reasons": ["no evidence grounding", "no test bench"],
        "sample_size": 250,
        "verified": True,   # must be overridden
    })
    assert block["verified"] is False
    assert block["qualified_estimate"] == 0.34


def test_validate_rejects_bad_estimate():
    with pytest.raises(ValueError):
        validate_ai_baseline({"qualified_estimate": 1.5, "reasons": ["x"], "sample_size": 10})


def test_validate_rejects_empty_reasons():
    with pytest.raises(ValueError):
        validate_ai_baseline({"qualified_estimate": 0.3, "reasons": [], "sample_size": 10})


def test_merge_sets_block():
    metrics = {"ai_baseline": None}
    out = merge_ai_baseline(metrics, {"qualified_estimate": 0.3, "reasons": ["x"], "sample_size": 5})
    assert out["ai_baseline"]["verified"] is False
    assert out["ai_baseline"]["qualified_estimate"] == 0.3


def test_validate_rejects_bool_estimate():
    with pytest.raises(ValueError):
        validate_ai_baseline({"qualified_estimate": True, "reasons": ["x"], "sample_size": 10})


def test_validate_rejects_bool_sample_size():
    with pytest.raises(ValueError):
        validate_ai_baseline({"qualified_estimate": 0.3, "reasons": ["x"], "sample_size": True})
