from datetime import date
from crm_report_card.config import RunConfig
from crm_report_card.scan import run_scan


def _cfg():
    return RunConfig(icp_nl="x", critical_properties=["email"], field_mapping={},
                     contact_email="a@b.co", booking_url="https://x",
                     favorite_customers=[], product_name="The CRM Report Card")


def test_run_scan_shape_and_grades():
    recs = [
        {"record_id": "0", "domain": "acme.com", "company_name": "Acme", "email": "jane@acme.com", "company_size": "100", "last_activity": "2026-06-01"},
        {"record_id": "1", "domain": "acme.com", "company_name": "Acme Inc", "email": "info@acme.com", "company_size": "100", "last_activity": "2020-01-01"},
    ]
    metrics = run_scan(recs, _cfg(), today=date(2026, 7, 22), fetcher=lambda d: (200, False))
    assert metrics["counts"]["records"] == 2
    assert metrics["facts"]["duplicates"]["duplicate_records"] == 1
    assert "grade" in metrics["facts"]["duplicates"]
    assert metrics["overall_grade"] in {"A", "B", "C", "D", "F"}
    assert metrics["ai_baseline"] is None
    assert metrics["decay"]["annual_rot_rate"] == 0.30
    assert metrics["product_name"] == "The CRM Report Card"
