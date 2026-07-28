"""Tests for benchmark/ground_truth_lib.py -- the pure, standard-library-only
logic behind the ground-truth review console (benchmark/ground_truth_console.py).
Deliberately imports the lib, not the console, so this file has no Flask
anywhere in its import path and runs under plain `python3 -m pytest` even on a
machine that has never installed Flask. Runs offline in the main pytest suite
via pyproject.toml's pythonpath entry for benchmark/.
"""
import json

import pytest

import ground_truth_lib as gtc


DOMAINS_CSV = """domain,tier,note
stripe.com,well-known,
segment.com,hard,subsidiary of Twilio
,well-known,blank domain row should be skipped
"""


def write(path, text):
    path.write_text(text)
    return path


def test_load_domains_reads_rows_in_order(tmp_path):
    csv_path = write(tmp_path / "domains.csv", DOMAINS_CSV)
    rows = gtc.load_domains(csv_path)
    assert [r["domain"] for r in rows] == ["stripe.com", "segment.com"]
    assert rows[1]["tier"] == "hard"
    assert rows[1]["note"] == "subsidiary of Twilio"


def test_load_domains_skips_blank_domain_rows(tmp_path):
    csv_path = write(tmp_path / "domains.csv", DOMAINS_CSV)
    rows = gtc.load_domains(csv_path)
    assert all(r["domain"] for r in rows)


def test_pending_skips_already_recorded_domains(tmp_path):
    csv_path = write(tmp_path / "domains.csv", DOMAINS_CSV)
    domains = gtc.load_domains(csv_path)
    rows = [gtc.make_record("stripe.com", "well-known", true_employee_count=9000,
                             citation_url="https://stripe.com/about", source_type="company_page")]
    todo = gtc.pending(domains, rows)
    assert [d["domain"] for d in todo] == ["segment.com"]


def test_pending_with_no_ground_truth_row_is_also_skipped(tmp_path):
    csv_path = write(tmp_path / "domains.csv", DOMAINS_CSV)
    domains = gtc.load_domains(csv_path)
    rows = [gtc.make_record("stripe.com", "well-known", no_ground_truth=True)]
    todo = gtc.pending(domains, rows)
    assert "stripe.com" not in {d["domain"] for d in todo}


def test_pending_with_no_rows_returns_everything(tmp_path):
    csv_path = write(tmp_path / "domains.csv", DOMAINS_CSV)
    domains = gtc.load_domains(csv_path)
    assert gtc.pending(domains, []) == domains


def test_append_record_is_append_only_and_crash_safe(tmp_path):
    out_path = tmp_path / "ground_truth.jsonl"
    r1 = gtc.make_record("stripe.com", "well-known", true_employee_count=9000,
                          citation_url="https://stripe.com/about", source_type="company_page")
    r2 = gtc.make_record("segment.com", "hard", true_employee_count=500,
                          citation_url="https://twilio.com/10-k", source_type="filing")
    gtc.append_record(out_path, r1)
    gtc.append_record(out_path, r2)
    lines = out_path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["domain"] == "stripe.com"
    assert json.loads(lines[1])["domain"] == "segment.com"


def test_append_record_creates_parent_dirs(tmp_path):
    out_path = tmp_path / "nested" / "dir" / "ground_truth.jsonl"
    gtc.append_record(out_path, gtc.make_record("stripe.com", "well-known", no_ground_truth=True))
    assert out_path.exists()


def test_load_ground_truth_skips_malformed_lines(tmp_path):
    out_path = tmp_path / "ground_truth.jsonl"
    out_path.write_text('{"domain": "stripe.com", "tier": "well-known"}\nnot json\n\n')
    rows = gtc.load_ground_truth(out_path)
    assert len(rows) == 1
    assert rows[0]["domain"] == "stripe.com"


def test_load_ground_truth_missing_file_returns_empty_list(tmp_path):
    assert gtc.load_ground_truth(tmp_path / "nope.jsonl") == []


def test_last_row_wins_for_a_correction(tmp_path):
    out_path = tmp_path / "ground_truth.jsonl"
    first = gtc.make_record("stripe.com", "well-known", true_employee_count=9000,
                             citation_url="https://stripe.com/about", source_type="company_page")
    correction = gtc.make_record("stripe.com", "well-known", true_employee_count=9500,
                                  citation_url="https://stripe.com/about-2", source_type="company_page",
                                  note="corrected after re-check")
    gtc.append_record(out_path, first)
    gtc.append_record(out_path, correction)
    rows = gtc.load_ground_truth(out_path)
    latest = gtc.latest_by_domain(rows)
    assert latest["stripe.com"]["true_employee_count"] == 9500
    assert latest["stripe.com"]["note"] == "corrected after re-check"
    # And the domain should NOT reappear in the pending queue after correction.
    domains = [{"domain": "stripe.com", "tier": "well-known", "note": ""}]
    assert gtc.pending(domains, rows) == []


def test_make_record_no_ground_truth_nulls_the_value_fields():
    rec = gtc.make_record("nowhere.example", "hard", true_employee_count=999,
                           true_linkedin_url="https://linkedin.com/company/x",
                           citation_url="https://example.com", source_type="third_party",
                           no_ground_truth=True)
    assert rec["no_ground_truth"] is True
    assert rec["true_employee_count"] is None
    assert rec["true_linkedin_url"] == ""
    assert rec["citation_url"] == ""
    assert rec["source_type"] == "none"


def test_make_record_rejects_bad_source_type():
    with pytest.raises(ValueError):
        gtc.make_record("stripe.com", "well-known", source_type="linkedin")


def test_make_record_rejects_non_integer_employee_count():
    with pytest.raises(ValueError):
        gtc.make_record("stripe.com", "well-known", true_employee_count="a lot")


def test_make_record_blank_employee_count_is_none():
    rec = gtc.make_record("stripe.com", "well-known", true_employee_count="")
    assert rec["true_employee_count"] is None


def test_evidence_links_never_reference_raw_or_ourplay_results():
    ev = gtc.evidence_for("stripe.com")
    blob = json.dumps(ev)
    assert "raw_results" not in blob
    assert "ourplay_results" not in blob


def test_headcount_evidence_excludes_linkedin():
    ev = gtc.evidence_for("stripe.com")
    assert "linkedin" not in ev["site_url"].lower()
    assert "linkedin" not in ev["google_about_url"].lower()
    assert "linkedin" not in ev["google_filing_url"].lower()


def test_linkedin_search_url_is_linkedin_only():
    ev = gtc.evidence_for("stripe.com")
    assert "linkedin.com" in ev["linkedin_search_url"]
    assert "stripe.com" in ev["linkedin_search_url"]
