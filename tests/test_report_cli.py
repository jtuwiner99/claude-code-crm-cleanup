import json
import os
from crm_report_card.cli import main


def _cfg_file(tmp_path):
    p = tmp_path / "run-config.json"
    p.write_text(json.dumps({
        "icp_nl": "US B2B SaaS", "critical_properties": ["email"],
        "favorite_customers": [], "field_mapping": {},
        "contact_email": "jacob@sculpted.agency", "booking_url": "https://cal.example/jacob",
        "portal_id": "12345",
    }))
    return str(p)


def _company_csv(tmp_path):
    p = tmp_path / "companies.csv"
    p.write_text("Company,Website,Email\nAcme,acme.com,jane@acme.com\nAcme2,acme.com,info@acme.com\n")
    return str(p)


def _contact_csv(tmp_path):
    p = tmp_path / "contacts.csv"
    p.write_text("Company,Website,Email\nJane Ross,,jane@acme.com\nBob,,bob@acme.com\n")
    return str(p)


def _metrics(offending_ids):
    return {
        "counts": {"records": 2},
        "facts": {
            "duplicates": {
                "duplicate_rate": 0.5,
                "grade": "F",
                "examples": [{"record_id": offending_ids[0], "label": "dup", "detail": "shares domain acme.com"}],
                "offending_ids": offending_ids,
            },
        },
        "overall_grade": "F",
        "ai_baseline": None,
    }


def _metrics_file(tmp_path, name, offending_ids):
    p = tmp_path / name
    p.write_text(json.dumps(_metrics(offending_ids)))
    return str(p)


def test_report_renders_both_segments_and_writes_lists(tmp_path, capsys):
    cfg = _cfg_file(tmp_path)
    cc = _company_csv(tmp_path)
    tc = _contact_csv(tmp_path)
    cm = _metrics_file(tmp_path, "company-metrics.json", ["0", "1"])
    tm = _metrics_file(tmp_path, "contact-metrics.json", ["0", "1"])
    card = str(tmp_path / "card.html")
    lists_dir = str(tmp_path / "lists")

    rc = main([
        "report", "--config", cfg, "--out", card, "--lists-dir", lists_dir,
        "--company-metrics", cm, "--company-csv", cc,
        "--contact-metrics", tm, "--contact-csv", tc,
    ])

    assert rc == 0
    assert os.path.exists(card)
    html = open(card, encoding="utf-8").read()
    assert "<h2>Companies" in html
    assert "<h2>Contacts" in html

    written = [f for f in os.listdir(lists_dir) if f.endswith(".csv")]
    assert any(f.startswith("company-") for f in written)
    assert any(f.startswith("contact-") for f in written)

    out = capsys.readouterr().out
    assert "company" in out
    assert "contact" in out


def test_report_requires_at_least_one_object(tmp_path, capsys):
    cfg = _cfg_file(tmp_path)
    card = str(tmp_path / "card.html")
    lists_dir = str(tmp_path / "lists")

    rc = main(["report", "--config", cfg, "--out", card, "--lists-dir", lists_dir])

    assert rc == 2
    assert not os.path.exists(card)
    err = capsys.readouterr().err
    assert "error" in err.lower()
