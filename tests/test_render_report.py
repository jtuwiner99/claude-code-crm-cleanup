from crm_report_card.config import RunConfig
from crm_report_card.render_html import render_report


def _cfg(portal_id=""):
    return RunConfig(icp_nl="x", critical_properties=["company_type"],
                     field_mapping={}, contact_email="jacob@sculpted.agency",
                     booking_url="https://cal.example/jacob", favorite_customers=[],
                     product_name="The CRM Report Card", portal_id=portal_id)


def _company_metrics():
    return {
        "counts": {"records": 100},
        "facts": {
            "duplicates": {
                "duplicate_rate": 0.10, "grade": "D",
                "examples": [{"record_id": "3", "label": "Acme", "detail": "shares domain acme.com"}],
                "offending_ids": ["3", "7"],
            },
            "fill_rate": {"overall_missing_rate": 0.41, "grade": "F", "examples": [], "offending_ids": []},
            "contradictions": {"rate": 0.0, "grade": "A", "examples": [], "offending_ids": []},
            "junk": {"junk_rate": 0.05, "grade": "C", "examples": [], "offending_ids": []},
            "staleness": {"stale_rate": 0.22, "grade": "F", "examples": [], "offending_ids": []},
            "liveness": {"dead_rate": 0.09, "bot_blocked": 4, "grade": "C", "examples": [], "offending_ids": []},
        },
        "overall_grade": "D",
        "ai_baseline": None,
    }


def _contact_metrics():
    return {
        "counts": {"records": 500},
        "facts": {
            "duplicates": {"duplicate_rate": 0.02, "grade": "B", "examples": [], "offending_ids": []},
            "fill_rate": {"overall_missing_rate": 0.15, "grade": "C", "examples": [], "offending_ids": []},
            "contradictions": {"rate": 0.01, "grade": "A", "examples": [], "offending_ids": []},
            "junk": {"junk_rate": 0.03, "grade": "B", "examples": [], "offending_ids": []},
            "staleness": {"stale_rate": 0.10, "grade": "C", "examples": [], "offending_ids": []},
            "orphaned": {
                "orphaned_rate": 0.08, "grade": "C",
                "examples": [{"record_id": "14", "label": "Jane Ross", "detail": "no associated company"}],
                "offending_ids": ["14"],
            },
            "email_format": {"invalid_rate": 0.04, "grade": "B", "examples": [], "offending_ids": []},
        },
        "overall_grade": "C",
        "ai_baseline": None,
    }


def _objects():
    return [
        {"object_type": "company", "metrics": _company_metrics()},
        {"object_type": "contact", "metrics": _contact_metrics()},
    ]


def test_render_report_renders_both_segments():
    html = render_report(_objects(), _cfg())
    assert "<h2>Companies" in html
    assert "<h2>Contacts" in html


def test_render_report_has_drilldown_panels_and_toggle_script():
    html = render_report(_objects(), _cfg())
    assert 'class="detail"' in html
    assert 'class="sig"' in html
    assert "classList.toggle('open')" in html
    # cited example evidence from both segments is present
    assert "Acme" in html
    assert "Jane Ross" in html


def test_render_report_deep_link_with_portal_id():
    html = render_report(_objects(), _cfg(portal_id="12345"))
    assert "app.hubspot.com/contacts/12345/record/0-2/3" in html   # company
    assert "app.hubspot.com/contacts/12345/record/0-1/14" in html  # contact


def test_render_report_no_portal_id_falls_back_to_row():
    html = render_report(_objects(), _cfg())
    assert "app.hubspot.com" not in html
    assert "row 3" in html
    assert "row 14" in html


def test_render_report_no_em_dash():
    html = render_report(_objects(), _cfg())
    assert "—" not in html
    assert "&mdash;" not in html
