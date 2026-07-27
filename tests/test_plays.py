import json
import pytest
from crm_report_card.plays import (load_registry, validate_registry,
                                   eligible_plays, blocked_plays)


def _entry(**over):
    base = {
        "id": "employee-count-accuracy",
        "unlocks": "employee_count_accuracy",
        "object_type": "company",
        "label": "Employee-count accuracy, verified vs stored",
        "requires_roles": ["domain", "company_size"],
        "providers": ["peopledatalabs_enrich_company"],
        "cost_per_record_usd": 0.14,
        "default_sample": 100,
        "comparison_rule": "mismatch = stored and verified fall two or more size bands apart",
    }
    base.update(over)
    return base


def test_valid_registry_has_no_errors():
    assert validate_registry([_entry()]) == []


def test_missing_field_is_an_error():
    bad = _entry()
    del bad["comparison_rule"]
    errors = validate_registry([bad])
    assert any("comparison_rule" in e for e in errors)


def test_unknown_role_is_an_error():
    """A typo'd role would silently disable the play forever, so it fails loudly."""
    errors = validate_registry([_entry(requires_roles=["domain", "compnay_size"])])
    assert any("compnay_size" in e for e in errors)


def test_role_not_valid_on_that_object_is_an_error():
    """company_size does not exist on contacts, so a contact play cannot require it."""
    errors = validate_registry([_entry(object_type="contact",
                                       requires_roles=["email", "company_size"])])
    assert any("company_size" in e for e in errors)


def test_duplicate_unlocks_key_is_an_error():
    errors = validate_registry([_entry(), _entry(id="other")])
    assert any("duplicate" in e.lower() for e in errors)


def test_eligible_when_every_required_role_is_mapped():
    mapping = {"domain": "Company Domain Name", "company_size": "Number of Employees"}
    assert [p["id"] for p in eligible_plays([_entry()], "company", mapping)] == \
        ["employee-count-accuracy"]


def test_not_eligible_for_the_wrong_object_type():
    mapping = {"domain": "Email Domain", "email": "Email"}
    assert eligible_plays([_entry()], "contact", mapping) == []


def test_blocked_play_names_the_missing_role():
    mapping = {"domain": "Company Domain Name"}
    blocked = blocked_plays([_entry()], "company", mapping)
    assert len(blocked) == 1
    play, missing = blocked[0]
    assert play["id"] == "employee-count-accuracy"
    assert missing == ["company_size"]


def test_load_registry_reads_the_plays_key(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"plays": [_entry()]}))
    assert [p["id"] for p in load_registry(str(path))] == ["employee-count-accuracy"]
