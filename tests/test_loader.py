from crm_report_card.loader import load_records


def _csv(tmp_path, text):
    p = tmp_path / "c.csv"
    p.write_text(text)
    return str(p)


def test_load_records_maps_roles(tmp_path):
    path = _csv(tmp_path, "Company,Website,Email\nAcme, acme.com ,jane@acme.com\n")
    records, mapping = load_records(path, {})
    assert mapping["company_name"] == "Company"
    assert records[0]["company_name"] == "Acme"
    assert records[0]["domain"] == "acme.com"   # stripped
    assert records[0]["email"] == "jane@acme.com"


def test_load_records_synthesizes_record_id(tmp_path):
    path = _csv(tmp_path, "Company,Website\nAcme,acme.com\nGlobex,globex.io\n")
    records, _ = load_records(path, {})
    assert records[0]["record_id"] == "0"
    assert records[1]["record_id"] == "1"


def test_load_records_missing_cells_blank(tmp_path):
    path = _csv(tmp_path, "Company,Website\nAcme,\n")
    records, _ = load_records(path, {})
    assert records[0]["domain"] == ""


def test_load_records_keeps_extra_columns_when_requested(tmp_path):
    path = _csv(tmp_path, "Company,Website,Industry\nAcme,acme.com,SaaS\n")
    records, _ = load_records(path, {}, extra_columns=["Industry"])
    assert records[0]["Industry"] == "SaaS"

    records_default, _ = load_records(path, {})
    assert "Industry" not in records_default[0]


def test_load_records_derives_domain_from_email_for_contacts(tmp_path):
    path = _csv(tmp_path, "First Name,Email\nJane, jane@acme.com \n")
    records, _ = load_records(path, {}, object_type="contact")
    assert records[0]["domain"] == "acme.com"


def test_load_records_does_not_derive_domain_from_email_for_companies(tmp_path):
    path = _csv(tmp_path, "First Name,Email\nJane, jane@acme.com \n")
    records, _ = load_records(path, {})
    assert records[0].get("domain", "") == ""
