from urllib.parse import unquote
from crm_report_card.config import RunConfig
from crm_report_card.render_html import render_html, build_mailto, locked_rows


def _cfg():
    return RunConfig(icp_nl="x", critical_properties=["company_type", "email"],
                     field_mapping={}, contact_email="jacob@sculpted.agency",
                     booking_url="https://cal.example/jacob", favorite_customers=[],
                     product_name="The CRM Report Card")


def _metrics(ai=None):
    return {
        "product_name": "The CRM Report Card",
        "counts": {"records": 100},
        "facts": {
            "duplicates": {"duplicate_rate": 0.10, "grade": "D"},
            "fill_rate": {"overall_missing_rate": 0.41, "grade": "F"},
            "contradictions": {"rate": 0.0, "grade": "A"},
            "junk": {"junk_rate": 0.05, "grade": "C"},
            "staleness": {"stale_rate": 0.22, "grade": "F"},
            "liveness": {"dead_rate": 0.09, "bot_blocked": 4, "grade": "C"},
        },
        "overall_grade": "D",
        "ai_baseline": ai,
    }


def test_locked_rows_personalized():
    rows = locked_rows(_cfg())
    assert any("company_type" in r for r in rows)
    assert any("Custom fit scoring" in r for r in rows)


def test_build_mailto_has_grade_no_raw_rows():
    url = build_mailto(_cfg(), _metrics())
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
    assert "OVERALL" in html.upper()
