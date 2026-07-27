import os
from crm_report_card.plays import load_registry, validate_registry

REGISTRY = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "crm-report-card", "plays", "registry.json"))


def test_shipped_registry_is_valid():
    """A malformed registry would disable every play at once."""
    assert validate_registry(load_registry(REGISTRY)) == []


def test_shipped_registry_has_the_employee_count_play():
    entries = load_registry(REGISTRY)
    play = next(e for e in entries if e["id"] == "employee-count-accuracy")
    assert play["unlocks"] == "employee_count_accuracy"
    assert play["object_type"] == "company"
    assert play["requires_roles"] == ["domain", "company_size"]
    assert play["default_sample"] == 100


def test_every_shipped_play_has_a_scorer():
    from crm_report_card.scorers import SCORERS
    for entry in load_registry(REGISTRY):
        assert entry["unlocks"] in SCORERS, f"no scorer for {entry['unlocks']}"


def test_every_shipped_play_has_a_source_file():
    for entry in load_registry(REGISTRY):
        path = os.path.join(os.path.dirname(REGISTRY), entry["id"], "play.ts")
        assert os.path.exists(path), f"missing play source for {entry['id']}"
