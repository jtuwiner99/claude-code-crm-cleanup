import json
from crm_report_card.cli import main


REGISTRY = {"plays": [{
    "id": "employee-count-accuracy",
    "unlocks": "employee_count_accuracy",
    "object_type": "company",
    "label": "Employee-count accuracy, verified vs stored",
    "requires_roles": ["domain", "company_size"],
    "providers": ["peopledatalabs_enrich_company"],
    "cost_per_record_usd": 0.14,
    "default_sample": 100,
    "comparison_rule": "mismatch = stored and verified fall two or more size bands apart",
}]}

CONFIG = {"icp_nl": "x", "critical_properties": ["domain"], "field_mapping": {},
          "object_type": "company"}

CSV = ("Company name,Company Domain Name,Number of Employees\n"
       "Acme,acme.com,10\n"
       "Globex,globex.io,4000\n"
       "Initech,initech.com,\n")


def _setup(tmp_path):
    (tmp_path / "registry.json").write_text(json.dumps(REGISTRY))
    (tmp_path / "config.json").write_text(json.dumps(CONFIG))
    (tmp_path / "book.csv").write_text(CSV)
    return tmp_path


def test_plays_lists_eligible_plays_with_a_cost_estimate(tmp_path, capsys):
    p = _setup(tmp_path)
    rc = main(["plays", "--registry", str(p / "registry.json"),
               "--config", str(p / "config.json"), "--csv", str(p / "book.csv"),
               "--out", str(p / "plays.json")])
    assert rc == 0
    out = json.loads((p / "plays.json").read_text())
    assert out["eligible"][0]["id"] == "employee-count-accuracy"
    # Only two of the three rows have a stored employee count.
    assert out["eligible"][0]["eligible_records"] == 2
    assert out["eligible"][0]["estimate"]["usd"] == 0.28
    assert out["eligible"][0]["estimate"]["credits"] == 2.8


def test_sample_writes_only_eligible_records(tmp_path):
    p = _setup(tmp_path)
    rc = main(["sample", "--registry", str(p / "registry.json"),
               "--play", "employee-count-accuracy",
               "--config", str(p / "config.json"), "--csv", str(p / "book.csv"),
               "--out", str(p / "sample.csv"), "--size", "10", "--seed", "1"])
    assert rc == 0
    lines = (p / "sample.csv").read_text().strip().splitlines()
    assert lines[0] == "record_id,domain,company_size"
    assert len(lines) == 3          # header plus the two records with a stored size


def test_fragment_scores_play_rows(tmp_path):
    p = _setup(tmp_path)
    (p / "rows.csv").write_text(
        "record_id,domain,stored_employee_count,verified_employee_count,source\n"
        "0,acme.com,10,900,peopledatalabs\n"
        "1,globex.io,4000,4200,peopledatalabs\n"
    )
    rc = main(["fragment", "--registry", str(p / "registry.json"),
               "--play", "employee-count-accuracy", "--rows", str(p / "rows.csv"),
               "--out", str(p / "frag.json"), "--sample-size", "2",
               "--provider", "peopledatalabs_enrich_company", "--run-at", "2026-07-27"])
    assert rc == 0
    frag = json.loads((p / "frag.json").read_text())
    assert frag["unlock"] == "employee_count_accuracy"
    assert frag["object_type"] == "company"
    assert frag["checked"] == 2
    assert frag["mismatched"] == 1
    assert frag["offending_ids"] == ["0"]


def test_unlock_merges_into_metrics(tmp_path):
    p = _setup(tmp_path)
    (p / "metrics.json").write_text(json.dumps({
        "object_type": "company", "counts": {"records": 3},
        "facts": {}, "overall_grade": "D"}))
    (p / "frag.json").write_text(json.dumps({
        "unlock": "employee_count_accuracy", "object_type": "company",
        "sample_size": 2, "checked": 2, "mismatched": 1, "rate": 0.5,
        "unverifiable": 0, "skipped_blank": 0, "examples": [], "offending_ids": ["0"],
        "provider": "peopledatalabs_enrich_company", "run_at": "2026-07-27"}))
    rc = main(["unlock", "--metrics", str(p / "metrics.json"),
               "--fragment", str(p / "frag.json"), "--out", str(p / "metrics.json")])
    assert rc == 0
    metrics = json.loads((p / "metrics.json").read_text())
    assert metrics["facts"]["employee_count_accuracy"]["grade"] == "F"
    assert metrics["overall_grade"] == "D"


def test_unlock_reports_a_bad_fragment_without_a_traceback(tmp_path, capsys):
    p = _setup(tmp_path)
    (p / "metrics.json").write_text(json.dumps({
        "object_type": "company", "counts": {"records": 3},
        "facts": {}, "overall_grade": "D"}))
    (p / "frag.json").write_text(json.dumps({"unlock": "nope"}))
    rc = main(["unlock", "--metrics", str(p / "metrics.json"),
               "--fragment", str(p / "frag.json"), "--out", str(p / "metrics.json")])
    assert rc == 2
    assert "unknown unlock key" in capsys.readouterr().err


def test_plays_reports_a_missing_registry_without_a_traceback(tmp_path, capsys):
    p = _setup(tmp_path)
    missing = p / "does-not-exist.json"
    rc = main(["plays", "--registry", str(missing),
               "--config", str(p / "config.json"), "--csv", str(p / "book.csv"),
               "--out", str(p / "plays.json")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "error:" in err
    assert str(missing) in err


def test_plays_reports_a_malformed_registry_without_a_traceback(tmp_path, capsys):
    p = _setup(tmp_path)
    registry_path = p / "registry.json"
    registry_path.write_text("{not valid json")
    rc = main(["plays", "--registry", str(registry_path),
               "--config", str(p / "config.json"), "--csv", str(p / "book.csv"),
               "--out", str(p / "plays.json")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "invalid JSON" in err
    assert str(registry_path) in err


def test_unlock_reports_a_missing_metrics_file_without_a_traceback(tmp_path, capsys):
    p = _setup(tmp_path)
    missing = p / "does-not-exist-metrics.json"
    (p / "frag.json").write_text(json.dumps({
        "unlock": "employee_count_accuracy", "object_type": "company",
        "sample_size": 2, "checked": 2, "mismatched": 1, "rate": 0.5,
        "unverifiable": 0, "skipped_blank": 0, "examples": [], "offending_ids": ["0"],
        "provider": "peopledatalabs_enrich_company", "run_at": "2026-07-27"}))
    rc = main(["unlock", "--metrics", str(missing),
               "--fragment", str(p / "frag.json"), "--out", str(p / "out.json")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "error:" in err
    assert str(missing) in err


def test_sample_reports_an_unknown_play_id_without_a_traceback(tmp_path, capsys):
    p = _setup(tmp_path)
    rc = main(["sample", "--registry", str(p / "registry.json"),
               "--play", "no-such-play",
               "--config", str(p / "config.json"), "--csv", str(p / "book.csv"),
               "--out", str(p / "sample.csv")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "no play with id" in err
    assert "no-such-play" in err


def test_fragment_reports_an_unknown_play_id_without_a_traceback(tmp_path, capsys):
    p = _setup(tmp_path)
    (p / "rows.csv").write_text(
        "record_id,domain,stored_employee_count,verified_employee_count,source\n"
        "0,acme.com,10,900,peopledatalabs\n"
    )
    rc = main(["fragment", "--registry", str(p / "registry.json"),
               "--play", "no-such-play", "--rows", str(p / "rows.csv"),
               "--out", str(p / "frag.json")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "no play with id" in err
    assert "no-such-play" in err
