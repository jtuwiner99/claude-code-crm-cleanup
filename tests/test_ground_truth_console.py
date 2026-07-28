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

# Mirrors the real raw_results.csv shape: domain, tier, provider, count, band,
# linkedin_url, error, payload_bytes. Provider names and counts are
# deliberately distinctive strings so a test can assert they never leak.
RAW_RESULTS_CSV = """domain,tier,provider,count,band,linkedin_url,error,payload_bytes
stripe.com,well-known,peopledatalabs,999999,1001-5000,linkedin.com/company/stripe,,30932
stripe.com,well-known,crustdata,777777,5001-10000,https://www.linkedin.com/company/Stripe/,,4495
stripe.com,well-known,datagma,,,,null-payload,0
shopify.com,well-known,crustdata,555555,,https://www.linkedin.com/company/devsincmea,,4200
"""

# Mirrors the real ourplay_results.csv shape: domain, count, band,
# identity_method, linkedin_url.
OURPLAY_RESULTS_CSV = """domain,count,band,identity_method,linkedin_url
stripe.com,888888,5001-10000,website-match,https://www.linkedin.com/company/stripe/
shopify.com,444444,,website-match,https://www.linkedin.com/company/shopify/
"""


def write(path, text):
    path.write_text(text)
    return path


# --------------------------------------------------------------------------
# domains.csv loading + resume + append-only + last-row-wins
# --------------------------------------------------------------------------

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


def _correct_record(domain, tier="well-known", **overrides):
    kwargs = dict(
        identity_verdict="correct",
        chosen_linkedin_url="https://www.linkedin.com/company/stripe/",
        linkedin_people_count=9000,
    )
    kwargs.update(overrides)
    return gtc.make_record(domain, tier, **kwargs)


def test_pending_skips_already_recorded_domains(tmp_path):
    csv_path = write(tmp_path / "domains.csv", DOMAINS_CSV)
    domains = gtc.load_domains(csv_path)
    rows = [_correct_record("stripe.com")]
    todo = gtc.pending(domains, rows)
    assert [d["domain"] for d in todo] == ["segment.com"]


def test_pending_with_no_ground_truth_row_is_also_skipped(tmp_path):
    csv_path = write(tmp_path / "domains.csv", DOMAINS_CSV)
    domains = gtc.load_domains(csv_path)
    rows = [gtc.make_record("stripe.com", "well-known", identity_verdict="no-ground-truth")]
    todo = gtc.pending(domains, rows)
    assert "stripe.com" not in {d["domain"] for d in todo}


def test_pending_with_no_rows_returns_everything(tmp_path):
    csv_path = write(tmp_path / "domains.csv", DOMAINS_CSV)
    domains = gtc.load_domains(csv_path)
    assert gtc.pending(domains, []) == domains


def test_append_record_is_append_only_and_crash_safe(tmp_path):
    out_path = tmp_path / "ground_truth.jsonl"
    r1 = _correct_record("stripe.com")
    r2 = _correct_record("segment.com", tier="hard",
                          chosen_linkedin_url="https://www.linkedin.com/company/twilio/",
                          linkedin_people_count=500)
    gtc.append_record(out_path, r1)
    gtc.append_record(out_path, r2)
    lines = out_path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["domain"] == "stripe.com"
    assert json.loads(lines[1])["domain"] == "segment.com"


def test_append_record_creates_parent_dirs(tmp_path):
    out_path = tmp_path / "nested" / "dir" / "ground_truth.jsonl"
    gtc.append_record(out_path, gtc.make_record("stripe.com", "well-known", identity_verdict="no-ground-truth"))
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
    first = _correct_record("stripe.com", linkedin_people_count=9000)
    correction = _correct_record("stripe.com", linkedin_people_count=9500, note="corrected after re-check")
    gtc.append_record(out_path, first)
    gtc.append_record(out_path, correction)
    rows = gtc.load_ground_truth(out_path)
    latest = gtc.latest_by_domain(rows)
    assert latest["stripe.com"]["linkedin_people_count"] == 9500
    assert latest["stripe.com"]["note"] == "corrected after re-check"
    # And the domain should NOT reappear in the pending queue after correction.
    domains = [{"domain": "stripe.com", "tier": "well-known", "note": ""}]
    assert gtc.pending(domains, rows) == []


# --------------------------------------------------------------------------
# make_record: identity_verdict-driven invariants
# --------------------------------------------------------------------------

def test_make_record_correct_requires_count_and_url():
    with pytest.raises(ValueError):
        gtc.make_record("stripe.com", "well-known", identity_verdict="correct",
                         chosen_linkedin_url="https://www.linkedin.com/company/stripe/")
    with pytest.raises(ValueError):
        gtc.make_record("stripe.com", "well-known", identity_verdict="correct",
                         linkedin_people_count=9000)


def test_make_record_correct_stores_both_fields():
    rec = _correct_record("stripe.com")
    assert rec["identity_verdict"] == "correct"
    assert rec["linkedin_people_count"] == 9000
    assert rec["chosen_linkedin_url"] == "https://www.linkedin.com/company/stripe/"


def test_make_record_wrong_nulls_linkedin_fields_even_if_passed():
    rec = gtc.make_record("stripe.com", "well-known", identity_verdict="wrong",
                           chosen_linkedin_url="https://www.linkedin.com/company/stripe/",
                           linkedin_people_count=9000)
    assert rec["identity_verdict"] == "wrong"
    assert rec["chosen_linkedin_url"] == ""
    assert rec["linkedin_people_count"] is None


def test_make_record_wrong_keeps_independent_fields():
    rec = gtc.make_record("stripe.com", "well-known", identity_verdict="wrong",
                           independent_count=8500,
                           independent_citation_url="https://stripe.com/newsroom/about")
    assert rec["independent_count"] == 8500
    assert rec["independent_citation_url"] == "https://stripe.com/newsroom/about"


def test_make_record_no_ground_truth_nulls_everything():
    rec = gtc.make_record("nowhere.example", "hard", identity_verdict="no-ground-truth",
                           chosen_linkedin_url="https://www.linkedin.com/company/x/",
                           linkedin_people_count=999,
                           independent_count=999,
                           independent_citation_url="https://example.com")
    assert rec["identity_verdict"] == "no-ground-truth"
    assert rec["chosen_linkedin_url"] == ""
    assert rec["linkedin_people_count"] is None
    assert rec["independent_count"] is None
    assert rec["independent_citation_url"] == ""


def test_make_record_rejects_bad_identity_verdict():
    with pytest.raises(ValueError):
        gtc.make_record("stripe.com", "well-known", identity_verdict="maybe")


def test_make_record_rejects_non_integer_linkedin_people_count():
    with pytest.raises(ValueError):
        gtc.make_record("stripe.com", "well-known", identity_verdict="correct",
                         chosen_linkedin_url="https://www.linkedin.com/company/stripe/",
                         linkedin_people_count="a lot")


def test_make_record_rejects_non_integer_independent_count():
    with pytest.raises(ValueError):
        gtc.make_record("stripe.com", "well-known", identity_verdict="wrong",
                         independent_count="a lot")


def test_make_record_independent_count_optional_and_defaults_none():
    rec = _correct_record("stripe.com")
    assert rec["independent_count"] is None
    assert rec["independent_citation_url"] == ""


# --------------------------------------------------------------------------
# LinkedIn slug normalization + URL builders
# --------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("linkedin.com/company/stripe", "stripe"),
    ("https://www.linkedin.com/company/stripe/", "stripe"),
    ("https://www.linkedin.com/company/Stripe", "stripe"),
    ("https://linkedin.com/company/twilio-inc-", "twilio-inc-"),
    ("", None),
    (None, None),
    ("https://example.com/not-linkedin", None),
])
def test_normalize_linkedin_slug(url, expected):
    assert gtc.normalize_linkedin_slug(url) == expected


def test_linkedin_company_and_people_urls():
    assert gtc.linkedin_company_url("stripe") == "https://www.linkedin.com/company/stripe/"
    assert gtc.linkedin_people_url("stripe") == "https://www.linkedin.com/company/stripe/people/"


def test_linkedin_search_url_is_linkedin_only_and_domain_scoped():
    url = gtc.linkedin_search_url("stripe.com")
    assert "linkedin.com" in url
    assert "stripe.com" in url


# --------------------------------------------------------------------------
# Candidate building from raw_results.csv / ourplay_results.csv -- blindness
# is the whole point of this section.
# --------------------------------------------------------------------------

def _write_results(tmp_path):
    raw = write(tmp_path / "raw_results.csv", RAW_RESULTS_CSV)
    ourplay = write(tmp_path / "ourplay_results.csv", OURPLAY_RESULTS_CSV)
    return raw, ourplay


def test_candidate_slugs_dedupe_across_both_files(tmp_path):
    raw, ourplay = _write_results(tmp_path)
    slugs = gtc.candidate_slugs_for_domain("stripe.com", raw, ourplay)
    # peopledatalabs, crustdata, and ourplay all point at the same slug for
    # stripe.com -- one candidate, not three.
    assert sorted(slugs) == ["stripe"]


def test_candidate_slugs_keep_real_disagreement(tmp_path):
    raw, ourplay = _write_results(tmp_path)
    slugs = gtc.candidate_slugs_for_domain("shopify.com", raw, ourplay)
    # crustdata says devsincmea, ourplay says shopify -- a real 2-way split.
    assert sorted(slugs) == ["devsincmea", "shopify"]


def test_candidate_order_is_deterministic_across_calls(tmp_path):
    raw, ourplay = _write_results(tmp_path)
    first = gtc.candidate_slugs_for_domain("shopify.com", raw, ourplay)
    second = gtc.candidate_slugs_for_domain("shopify.com", raw, ourplay)
    assert first == second


def test_candidate_order_differs_per_domain_seed(tmp_path):
    # Same two-slug set, different domain strings as the shuffle seed. This
    # exact pair (stripe.com vs shopify.com) is verified to land on different
    # permutations of a 2-item list under the domain-seeded RNG; it is not a
    # universal law (some domain pairs do collide on a 2-item list), it just
    # pins down that the seed is domain-derived rather than a constant.
    raw = write(tmp_path / "raw_results.csv",
                "domain,tier,provider,count,band,linkedin_url,error,payload_bytes\n"
                "stripe.com,well-known,peopledatalabs,1,,https://www.linkedin.com/company/aaa/,,1\n"
                "stripe.com,well-known,crustdata,1,,https://www.linkedin.com/company/bbb/,,1\n"
                "shopify.com,well-known,peopledatalabs,1,,https://www.linkedin.com/company/aaa/,,1\n"
                "shopify.com,well-known,crustdata,1,,https://www.linkedin.com/company/bbb/,,1\n")
    ourplay = write(tmp_path / "ourplay_results.csv", "domain,count,band,identity_method,linkedin_url\n")
    order_a = gtc.candidate_slugs_for_domain("stripe.com", raw, ourplay)
    order_b = gtc.candidate_slugs_for_domain("shopify.com", raw, ourplay)
    assert set(order_a) == set(order_b) == {"aaa", "bbb"}
    assert order_a != order_b


def test_candidates_for_domain_has_no_slug_missing_domain(tmp_path):
    raw, ourplay = _write_results(tmp_path)
    assert gtc.candidate_slugs_for_domain("nowhere.example", raw, ourplay) == []


def test_candidates_for_domain_shape(tmp_path):
    raw, ourplay = _write_results(tmp_path)
    cands = gtc.candidates_for_domain("stripe.com", raw, ourplay)
    assert cands == [{
        "company_url": "https://www.linkedin.com/company/stripe/",
        "people_url": "https://www.linkedin.com/company/stripe/people/",
    }]


def test_candidates_never_leak_provider_name_or_count(tmp_path):
    raw, ourplay = _write_results(tmp_path)
    for domain in ("stripe.com", "shopify.com"):
        blob = json.dumps(gtc.candidates_for_domain(domain, raw, ourplay))
        for leak in ("peopledatalabs", "crustdata", "datagma", "provider",
                     "999999", "777777", "555555", "888888", "444444",
                     "identity_method", "website-match", "band", "payload_bytes"):
            assert leak not in blob, f"{leak!r} leaked into candidates for {domain}"


def test_row_context_never_leaks_provider_name_count_or_result_filenames(tmp_path):
    raw, ourplay = _write_results(tmp_path)
    ctx = gtc.row_context_for("stripe.com", raw, ourplay)
    blob = json.dumps(ctx)
    for leak in ("peopledatalabs", "crustdata", "datagma", "provider",
                 "999999", "777777", "555555", "888888", "444444",
                 "raw_results", "ourplay_results"):
        assert leak not in blob, f"{leak!r} leaked into row context"
    assert "linkedin" not in ctx["homepage_url"].lower()
    assert "linkedin" not in ctx["google_about_url"].lower()
    assert "linkedin" not in ctx["google_filing_url"].lower()


def test_row_context_missing_result_files_returns_no_candidates(tmp_path):
    # Files not present yet (e.g. before the benchmark run) -- graceful empty
    # candidate list, not an error.
    ctx = gtc.row_context_for("stripe.com", tmp_path / "nope1.csv", tmp_path / "nope2.csv")
    assert ctx["candidates"] == []


# --------------------------------------------------------------------------
# Homepage framing helpers (safe_public_url, strip_frame_guards) -- these are
# the only pieces of the qa-console-style proxy that don't need a live
# network call, so they're what gets unit tested.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("http://127.0.0.1/", False),        # loopback
    ("http://10.0.0.5/", False),         # private
    ("http://169.254.1.1/", False),      # link-local
    ("http://224.0.0.1/", False),        # multicast
    ("ftp://example.com/", False),       # bad scheme
    ("not a url", False),                # no hostname
    ("http://93.184.216.34/", True),     # public unicast IP literal, no DNS needed
])
def test_safe_public_url(url, expected):
    assert gtc.safe_public_url(url) is expected


def test_strip_frame_guards_removes_csp_and_xfo_meta_and_injects_base():
    html = ('<html><head><meta http-equiv="X-Frame-Options" content="DENY">'
            '<meta http-equiv="Content-Security-Policy" content="frame-ancestors none">'
            '<title>x</title></head><body>hi</body></html>')
    out = gtc.strip_frame_guards(html, "https://stripe.com/")
    assert "x-frame-options" not in out.lower()
    assert "content-security-policy" not in out.lower()
    assert '<base href="https://stripe.com/">' in out
    assert out.index("<base") < out.index("<title>")


def test_strip_frame_guards_handles_missing_head_tag():
    html = "<body>no head here</body>"
    out = gtc.strip_frame_guards(html, "https://stripe.com/")
    assert out.startswith('<base href="https://stripe.com/">')
