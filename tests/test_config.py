import json
import pytest
from crm_report_card.config import load_config, RunConfig


def _write(tmp_path, obj):
    p = tmp_path / "run-config.json"
    p.write_text(json.dumps(obj))
    return str(p)


def test_load_config_happy_path(tmp_path):
    path = _write(tmp_path, {
        "icp_nl": "US B2B SaaS, 50-500 employees",
        "critical_properties": ["company_size", "email"],
        "favorite_customers": ["acme.com"],
        "field_mapping": {"domain": "Website"},
        "contact_email": "jacob@sculpted.agency",
        "booking_url": "https://cal.example/jacob",
    })
    cfg = load_config(path)
    assert isinstance(cfg, RunConfig)
    assert cfg.product_name == "The CRM Report Card"
    assert cfg.critical_properties == ["company_size", "email"]
    assert cfg.field_mapping == {"domain": "Website"}


def test_load_config_missing_required_raises(tmp_path):
    path = _write(tmp_path, {"icp_nl": "x"})
    with pytest.raises(ValueError):
        load_config(path)


def test_load_config_empty_icp_raises(tmp_path):
    path = _write(tmp_path, {
        "icp_nl": "   ",
        "critical_properties": ["email"],
        "favorite_customers": [],
        "field_mapping": {},
        "contact_email": "a@b.co",
        "booking_url": "https://x",
    })
    with pytest.raises(ValueError):
        load_config(path)
