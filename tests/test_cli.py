import json
from crm_report_card.cli import main


def _cfg_file(tmp_path):
    p = tmp_path / "run-config.json"
    p.write_text(json.dumps({
        "icp_nl": "US B2B SaaS", "critical_properties": ["email"],
        "favorite_customers": [], "field_mapping": {},
        "contact_email": "jacob@sculpted.agency", "booking_url": "https://cal.example/jacob",
    }))
    return str(p)


def _csv_file(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("Company,Website,Email\nAcme,acme.com,jane@acme.com\nAcme2,acme.com,info@acme.com\n")
    return str(p)


def test_scan_then_render(tmp_path, capsys):
    cfg = _cfg_file(tmp_path)
    csv = _csv_file(tmp_path)
    metrics_path = str(tmp_path / "metrics.json")
    html_path = str(tmp_path / "card.html")

    rc = main(["scan", "--config", cfg, "--csv", csv, "--out", metrics_path])
    assert rc == 0
    metrics = json.loads(open(metrics_path).read())
    assert metrics["counts"]["records"] == 2
    assert "OVERALL GRADE" in capsys.readouterr().out

    rc2 = main(["render", "--metrics", metrics_path, "--config", cfg, "--out", html_path])
    assert rc2 == 0
    html = open(html_path).read()
    assert "Book a free session" in html


def test_skip_liveness_env_var_omits_the_dead_domain_row(tmp_path, monkeypatch, capsys):
    """CRM_RC_SKIP_LIVENESS is the only way to run the free scan with zero
    network. It must not invent a 100% dead-domain F to get there."""
    monkeypatch.setenv("CRM_RC_SKIP_LIVENESS", "1")
    cfg = _cfg_file(tmp_path)
    csv = _csv_file(tmp_path)
    metrics_path = str(tmp_path / "metrics.json")

    rc = main(["scan", "--config", cfg, "--csv", csv, "--out", metrics_path])
    assert rc == 0
    metrics = json.loads(open(metrics_path).read())
    assert "liveness" not in metrics["facts"]

    out = capsys.readouterr().out
    assert "Dead domains" not in out
