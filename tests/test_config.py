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


def test_cta_details_are_optional_and_default(tmp_path):
    # A prospect's run-config never carries contact_email/booking_url; the
    # "Work with Jacob" offer is baked in via defaults, not asked for.
    path = _write(tmp_path, {
        "icp_nl": "US B2B SaaS",
        "critical_properties": ["email"],
        "field_mapping": {},
    })
    cfg = load_config(path)
    assert cfg.contact_email == "jacob@sculpted.agency"
    # The real booking link, not a placeholder. It is the call-to-action button
    # on every rendered card, so a stale default is a dead button.
    assert cfg.booking_url == ("https://meetings.hubspot.com/tuwiner/"
                               "sculpted-intro-meeting")


def test_object_type_defaults_to_company(tmp_path):
    path = _write(tmp_path, {
        "icp_nl": "US B2B SaaS",
        "critical_properties": ["email"],
        "field_mapping": {},
    })
    cfg = load_config(path)
    assert cfg.object_type == "company"


def test_object_type_loads_contact_when_present(tmp_path):
    path = _write(tmp_path, {
        "icp_nl": "US B2B SaaS",
        "critical_properties": ["email"],
        "field_mapping": {},
        "object_type": "contact",
    })
    cfg = load_config(path)
    assert cfg.object_type == "contact"


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
