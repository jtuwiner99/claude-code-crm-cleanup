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


from crm_report_card.plays import eligible_records, draw_sample, estimate_cost, CREDIT_USD


def _recs(n):
    return [{"record_id": str(i), "domain": f"co{i}.com", "company_size": "100"}
            for i in range(n)]


def test_eligible_records_need_every_required_role_filled():
    recs = [
        {"record_id": "0", "domain": "a.com", "company_size": "100"},
        {"record_id": "1", "domain": "", "company_size": "100"},
        {"record_id": "2", "domain": "c.com", "company_size": ""},
    ]
    out = eligible_records(recs, _entry())
    assert [r["record_id"] for r in out] == ["0"]


def test_sample_is_deterministic_for_a_seed():
    recs = _recs(50)
    a = draw_sample(recs, 10, seed=7)
    b = draw_sample(recs, 10, seed=7)
    assert [r["record_id"] for r in a] == [r["record_id"] for r in b]
    assert len(a) == 10


def test_a_different_seed_draws_a_different_sample():
    recs = _recs(50)
    a = draw_sample(recs, 10, seed=7)
    b = draw_sample(recs, 10, seed=8)
    assert [r["record_id"] for r in a] != [r["record_id"] for r in b]


def test_sample_larger_than_population_returns_everything():
    recs = _recs(5)
    assert len(draw_sample(recs, 100, seed=1)) == 5


def test_sample_does_not_mutate_the_input_order():
    recs = _recs(20)
    before = [r["record_id"] for r in recs]
    draw_sample(recs, 5, seed=3)
    assert [r["record_id"] for r in recs] == before


def test_cost_estimate_in_dollars_and_credits():
    est = estimate_cost(_entry(cost_per_record_usd=0.14), 100)
    assert est["records"] == 100
    assert est["usd"] == pytest.approx(14.0)
    assert est["credits"] == pytest.approx(140.0)
    assert CREDIT_USD == 0.10
