import json, os
from datetime import date
from crm_report_card.config import RunConfig
from crm_report_card.loader import load_records
from crm_report_card.scan import run_scan, scan_from_files


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


FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "messy-crm-sample.csv")
EXPECTED = os.path.join(os.path.dirname(__file__), "..", "fixtures", "messy-crm-sample.expected.json")


def test_golden_fixture_matches_expected():
    records, _ = load_records(os.path.normpath(FIXTURE), {})
    metrics = run_scan(records, _cfg(), today=date(2026, 7, 22), fetcher=lambda d: (200, False))
    expected = json.loads(open(os.path.normpath(EXPECTED)).read())
    assert metrics["counts"]["records"] == expected["counts"]["records"]
    assert metrics["facts"]["duplicates"]["duplicate_records"] == expected["duplicate_records"]
    assert metrics["overall_grade"] == expected["overall_grade"]


def test_scan_from_files_checks_custom_critical_column(tmp_path):
    csv_text = (
        "Company name,Company Domain Name,Industry\n"
        "Acme,acme.com,SaaS\n"
        "Globex,globex.io,\n"
        "Initech,initech.com,Manufacturing\n"
    )
    path = tmp_path / "raw.csv"
    path.write_text(csv_text)

    cfg = RunConfig(icp_nl="x", critical_properties=["Industry"], field_mapping={},
                     contact_email="a@b.co", booking_url="https://x",
                     favorite_customers=[], product_name="The CRM Report Card")

    metrics = scan_from_files(str(path), cfg, today=date(2026, 7, 22),
                              fetcher=lambda d: (200, False))

    per_field = metrics["facts"]["fill_rate"]["per_field"]
    assert "Industry" in per_field
    assert per_field["Industry"]["filled"] == 2
    assert per_field["Industry"]["missing"] == 1


def test_scan_from_files_contact_mode_does_not_inflate_duplicates(tmp_path):
    csv_text = (
        "First Name,Company Domain Name,Email\n"
        "Jane,acme.com,jane@acme.com\n"
        "John,acme.com,john@acme.com\n"
        "Sue,acme.com,sue@acme.com\n"
    )
    path = tmp_path / "contacts.csv"
    path.write_text(csv_text)

    cfg = RunConfig(icp_nl="x", critical_properties=["email"], field_mapping={},
                     contact_email="a@b.co", booking_url="https://x",
                     favorite_customers=[], product_name="The CRM Report Card",
                     object_type="contact")

    metrics = scan_from_files(str(path), cfg, today=date(2026, 7, 22),
                              fetcher=lambda d: (200, False))

    assert metrics["facts"]["duplicates"]["duplicate_records"] == 0
