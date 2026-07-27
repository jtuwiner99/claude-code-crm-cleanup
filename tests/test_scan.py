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


def test_company_mode_scan_has_liveness_not_orphaned_or_email_format():
    recs = [
        {"record_id": "0", "domain": "acme.com", "company_name": "Acme", "email": "jane@acme.com", "company_size": "100", "last_activity": "2026-06-01"},
    ]
    metrics = run_scan(recs, _cfg(), today=date(2026, 7, 22), fetcher=lambda d: (200, False))
    assert "liveness" in metrics["facts"]
    assert "orphaned" not in metrics["facts"]
    assert "email_format" not in metrics["facts"]
    assert metrics["overall_grade"] in {"A", "B", "C", "D", "F"}


def test_contact_mode_scan_has_orphaned_and_email_format_not_liveness():
    recs = [
        {"record_id": "0", "company_name": "Acme", "email": "jane@acme.com", "last_activity": "2026-06-01"},
        {"record_id": "1", "company_name": "", "email": "not-an-email", "last_activity": "2026-06-01"},
    ]
    cfg = RunConfig(icp_nl="x", critical_properties=["email"], field_mapping={},
                     contact_email="a@b.co", booking_url="https://x",
                     favorite_customers=[], product_name="The CRM Report Card",
                     object_type="contact")
    metrics = run_scan(recs, cfg, today=date(2026, 7, 22), fetcher=lambda d: (200, False))
    assert "orphaned" in metrics["facts"]
    assert "email_format" in metrics["facts"]
    assert "liveness" not in metrics["facts"]
    assert metrics["facts"]["orphaned"]["orphaned_count"] == 1
    assert metrics["facts"]["email_format"]["invalid_count"] == 1
    assert metrics["overall_grade"] in {"A", "B", "C", "D", "F"}


def test_contradictions_is_a_company_only_check():
    """Contacts no longer carry company size, so the check has no input there.

    Running it anyway would print a flattering 0.0% (A) for a signal that was
    never measured, which is the exact failure mode we just fixed in staleness.
    """
    recs = [{"record_id": "0", "company_name": "Acme", "email": "jane@acme.com",
             "last_activity": "2026-06-01"}]
    contact_cfg = RunConfig(icp_nl="x", critical_properties=["email"], field_mapping={},
                            contact_email="a@b.co", booking_url="https://x",
                            favorite_customers=[], product_name="The CRM Report Card",
                            object_type="contact")
    contact_metrics = run_scan(recs, contact_cfg, today=date(2026, 7, 22),
                               fetcher=lambda d: (200, False))
    assert "contradictions" not in contact_metrics["facts"]

    company_recs = [{"record_id": "0", "domain": "acme.com", "company_name": "Acme",
                     "email": "jane@acme.com", "company_size": "100",
                     "last_activity": "2026-06-01"}]
    company_metrics = run_scan(company_recs, _cfg(), today=date(2026, 7, 22),
                               fetcher=lambda d: (200, False))
    assert "contradictions" in company_metrics["facts"]


def test_contradictions_omitted_when_the_export_has_no_emails_to_count():
    """A standard HubSpot companies export has no email column.

    With nothing to count against the stated size, the comparison never fires,
    so reporting it would be a structural 0.0% (A) for an unmeasured signal.
    """
    recs = [
        {"record_id": "0", "domain": "acme.com", "company_name": "Acme",
         "company_size": "100", "last_activity": "2026-06-01"},
    ]
    metrics = run_scan(recs, _cfg(), today=date(2026, 7, 22), fetcher=lambda d: (200, False))
    assert "contradictions" not in metrics["facts"]


def test_contradictions_omitted_when_no_size_is_present():
    recs = [
        {"record_id": "0", "domain": "acme.com", "company_name": "Acme",
         "email": "jane@acme.com", "last_activity": "2026-06-01"},
    ]
    metrics = run_scan(recs, _cfg(), today=date(2026, 7, 22), fetcher=lambda d: (200, False))
    assert "contradictions" not in metrics["facts"]


def test_contact_scan_ignores_a_company_size_column(tmp_path):
    """Company size on a contacts export is a company property on the wrong
    object (0.2% filled on a real book) and must not reach the records."""
    csv_text = (
        "First Name,Email,Company size,Email Domain\n"
        "Jane,jane@acme.com,100,acme.com\n"
    )
    path = tmp_path / "contacts.csv"
    path.write_text(csv_text)
    cfg = RunConfig(icp_nl="x", critical_properties=["email"], field_mapping={},
                    contact_email="a@b.co", booking_url="https://x",
                    favorite_customers=[], product_name="The CRM Report Card",
                    object_type="contact")
    records, _ = load_records(str(path), {}, object_type="contact")
    assert "company_size" not in records[0]
    assert records[0]["domain"] == "acme.com"

    metrics = scan_from_files(str(path), cfg, today=date(2026, 7, 22),
                              fetcher=lambda d: (200, False))
    assert "contradictions" not in metrics["facts"]


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


def test_metrics_carries_the_object_type():
    """A fragment cannot be safely attached to metrics that does not say what
    object it graded."""
    recs = [{"record_id": "0", "domain": "acme.com", "company_name": "Acme",
             "email": "jane@acme.com", "company_size": "100",
             "last_activity": "2026-06-01"}]
    metrics = run_scan(recs, _cfg(), today=date(2026, 7, 22), fetcher=lambda d: (200, False))
    assert metrics["object_type"] == "company"
