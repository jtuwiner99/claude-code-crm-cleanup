from crm_report_card.config import RunConfig
from crm_report_card.render_html import render_report, _accuracy_html


def _cfg():
    return RunConfig(icp_nl="x", critical_properties=["domain"], field_mapping={},
                     contact_email="a@b.co", booking_url="https://x",
                     favorite_customers=[], product_name="The CRM Report Card",
                     object_type="company", portal_id="24177200")


def _obj(with_unlock=False):
    facts = {"duplicates": {"duplicate_rate": 0.02, "grade": "B", "examples": [],
                            "offending_ids": []}}
    if with_unlock:
        facts["employee_count_accuracy"] = {
            "unlock": "employee_count_accuracy", "object_type": "company",
            "sample_size": 100, "checked": 92, "mismatched": 30, "rate": 0.326,
            "unverifiable": 8, "skipped_blank": 0, "grade": "F",
            "examples": [{"record_id": "1", "label": "acme.com",
                          "detail": "stored 10, verified 900"}],
            "offending_ids": ["1"],
            "provider": "peopledatalabs_enrich_company", "run_at": "2026-07-27",
        }
    return {"object_type": "company",
            "metrics": {"object_type": "company", "counts": {"records": 657},
                        "facts": facts, "overall_grade": "D"},
            "list_files": {}}


def test_all_three_rows_are_locked_before_any_unlock():
    html = _accuracy_html(_cfg(), [_obj()])
    assert html.count("LOCKED") == 3


def test_an_unlocked_row_renders_as_a_graded_signal():
    html = _accuracy_html(_cfg(), [_obj(with_unlock=True)])
    assert html.count("LOCKED") == 2
    assert "32.6%" in html
    assert "Employee-count accuracy" in html


def test_an_unlocked_row_carries_its_provenance():
    html = _accuracy_html(_cfg(), [_obj(with_unlock=True)])
    assert "peopledatalabs_enrich_company" in html
    assert "2026-07-27" in html
    assert "100" in html          # sample size
    assert "8" in html            # unverifiable count


def test_an_unlocked_row_keeps_the_verify_deep_link():
    html = _accuracy_html(_cfg(), [_obj(with_unlock=True)])
    assert "app.hubspot.com" in html
    assert "verify" in html


def test_render_report_substitutes_the_accuracy_block():
    html = render_report([_obj(with_unlock=True)], _cfg())
    assert "32.6%" in html
    assert "random sample of 100 records" in html


def test_accuracy_registry_stays_in_step_with_the_unlock_keys():
    """render_html and unlock name the same three signals. If one drifts, a row
    silently stops unlocking."""
    from crm_report_card.render_html import _ACCURACY_REGISTRY
    from crm_report_card.unlock import ACCURACY_UNLOCKS
    assert tuple(key for key, _label, _rate in _ACCURACY_REGISTRY) == ACCURACY_UNLOCKS
