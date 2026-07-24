from urllib.parse import unquote
from crm_report_card.config import RunConfig
from crm_report_card.render_html import render_html, build_mailto, locked_rows


def _cfg(portal_id=""):
    return RunConfig(icp_nl="x", critical_properties=["company_type", "email"],
                     field_mapping={}, contact_email="jacob@sculpted.agency",
                     booking_url="https://cal.example/jacob", favorite_customers=[],
                     product_name="The CRM Report Card", portal_id=portal_id)


def _metrics(ai=None):
    return {
        "product_name": "The CRM Report Card",
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
        "ai_baseline": ai,
    }


def test_locked_rows_personalized():
    rows = locked_rows(_cfg())
    assert any("company_type" in r for r in rows)
    assert any("Custom fit scoring" in r for r in rows)


def test_build_mailto_has_grade_no_raw_rows():
    url = build_mailto(_cfg(), [{"object_type": "company", "metrics": _metrics()}])
    assert url.startswith("mailto:jacob@sculpted.agency")
    decoded = unquote(url)
    assert "Grade: D" in decoded


def test_render_html_labels_and_cta():
    html = render_html(_metrics(ai={"qualified_estimate": 0.34, "reasons": ["no bench"], "sample_size": 250, "verified": False}), _cfg())
    assert "FACT" in html
    assert "ESTIMATE" in html and "NOT VERIFIED" in html
    assert "company_type" in html            # personalized locked row
    assert "mailto:jacob@sculpted.agency" in html
    assert "cal.example/jacob" in html
    assert "GRADE" in html.upper()
    assert "Dead domains" in html


def _contact_metrics(ai=None):
    return {
        "product_name": "The CRM Report Card",
        "counts": {"records": 500},
        "facts": {
            "duplicates": {"duplicate_rate": 0.02, "grade": "B", "examples": [], "offending_ids": []},
            "fill_rate": {"overall_missing_rate": 0.15, "grade": "C", "examples": [], "offending_ids": []},
            "contradictions": {"rate": 0.01, "grade": "A", "examples": [], "offending_ids": []},
            "junk": {"junk_rate": 0.03, "grade": "B", "examples": [], "offending_ids": []},
            "staleness": {"stale_rate": 0.10, "grade": "C", "examples": [], "offending_ids": []},
            "orphaned": {"orphaned_rate": 0.08, "grade": "C", "examples": [], "offending_ids": []},
            "email_format": {"invalid_rate": 0.04, "grade": "B", "examples": [], "offending_ids": []},
        },
        "overall_grade": "C",
        "ai_baseline": ai,
    }


def test_render_html_contact_mode_renders_without_keyerror():
    cfg = RunConfig(icp_nl="x", critical_properties=["company_type", "email"],
                     field_mapping={}, contact_email="jacob@sculpted.agency",
                     booking_url="https://cal.example/jacob", favorite_customers=[],
                     product_name="The CRM Report Card", object_type="contact")
    html = render_html(_contact_metrics(), cfg)
    assert "Orphaned contacts" in html
    assert "Invalid email format" in html
    assert "Dead domains" not in html


def test_build_mailto_contact_mode_lists_contact_facts():
    url = build_mailto(_cfg(), [{"object_type": "contact", "metrics": _contact_metrics()}])
    decoded = unquote(url)
    assert "Orphaned contacts" in decoded
    assert "Invalid email format" in decoded
    assert "Dead domains" not in decoded


def test_render_html_deep_link_with_portal_id():
    html = render_html(_metrics(), _cfg(portal_id="12345"))
    assert "app.hubspot.com" in html
    assert "app.hubspot.com/contacts/12345/record/0-2/3" in html


def test_render_html_no_portal_id_falls_back_to_row():
    html = render_html(_metrics(), _cfg())
    assert "app.hubspot.com" not in html
    assert "row 3" in html
