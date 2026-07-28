from crm_report_card.config import RunConfig
from crm_report_card.render_html import render_report, _accuracy_html

RULE = "mismatch = stored and verified fall two or more size bands apart"

# The two grade columns in a segment head. Matched on their own markup, not on
# the bare word, which also appears in the stage-02 ladder chip.
COMPLETENESS_COLUMN = '<div class="gradelbl">Completeness</div>'
ACCURACY_COLUMN = '<div class="gradelbl">Accuracy</div>'


def _cfg():
    return RunConfig(icp_nl="x", critical_properties=["domain"], field_mapping={},
                     contact_email="a@b.co", booking_url="https://x",
                     favorite_customers=[], product_name="The CRM Report Card",
                     object_type="company", portal_id="24177200")


def _fact(**over):
    base = {
        "unlock": "employee_count_accuracy", "object_type": "company",
        "sample_size": 100, "checked": 92, "mismatched": 30, "rate": 0.326,
        "unverifiable": 8, "skipped_blank": 0, "measurable": True, "grade": "F",
        "examples": [{"record_id": "1", "label": "acme.com",
                      "detail": "stored 10, verified 900"}],
        "offending_ids": ["1"],
        "provider": "peopledatalabs_enrich_company", "run_at": "2026-07-27",
        "comparison_rule": RULE,
    }
    base.update(over)
    return base


def _obj(with_unlock=False, fact=None):
    facts = {"duplicates": {"duplicate_rate": 0.02, "grade": "B", "examples": [],
                            "offending_ids": []}}
    if with_unlock or fact is not None:
        facts["employee_count_accuracy"] = fact if fact is not None else _fact()
    return {"object_type": "company",
            "metrics": {"object_type": "company", "counts": {"records": 657},
                        "facts": facts, "overall_grade": "D"},
            "list_files": {}}


def _not_measurable_fact():
    """What a run looks like when the provider returned nothing usable: every
    row unverifiable, nothing comparable, rate collapses to 0.0."""
    fact = _fact(checked=0, mismatched=0, rate=0.0, unverifiable=100,
                 sample_size=100, measurable=False, examples=[], offending_ids=[])
    del fact["grade"]   # merge_fragment omits the grade key entirely
    return fact


def test_all_four_rows_are_locked_before_any_unlock():
    html = _accuracy_html(_cfg(), [_obj()])
    assert html.count("LOCKED") == 4


def test_an_unlocked_row_renders_as_a_graded_signal():
    html = _accuracy_html(_cfg(), [_obj(with_unlock=True)])
    assert html.count("LOCKED") == 3
    assert "32.6%" in html
    assert "Employee-count accuracy" in html


def test_an_unlocked_row_carries_its_provenance():
    html = _accuracy_html(_cfg(), [_obj(with_unlock=True)])
    assert "peopledatalabs_enrich_company" in html
    assert "2026-07-27" in html
    assert "100" in html          # sample size
    assert "8 unverifiable" in html  # unverifiable count (not just "8", which
                                      # also occurs inside the "&#8599;" verify
                                      # link entity and would pass vacuously)


def test_an_unlocked_row_keeps_the_verify_deep_link():
    html = _accuracy_html(_cfg(), [_obj(with_unlock=True)])
    assert "app.hubspot.com" in html
    assert "verify" in html


def test_render_report_substitutes_the_accuracy_block():
    html = render_report([_obj(with_unlock=True)], _cfg())
    assert "32.6%" in html
    assert "random sample of 100 records" in html


# --- CRITICAL 1: a run that verified nothing is not an A -------------------

def test_a_not_measurable_row_renders_no_grade_badge_and_no_percentage():
    """The failure this guards: rate = 0/0 = 0.0 grades as an A, and the card
    draws an A badge with a 0%-width bar over a run that verified nothing.
    Asserting only on the words "Not measurable" would pass a half-fix that
    still printed the badge, so assert the grade markup is ABSENT."""
    html = _accuracy_html(_cfg(), [_obj(fact=_not_measurable_fact())])
    assert 'class="grade' not in html      # no letter-grade badge
    assert 'class="barfill' not in html    # no grade bar
    assert "%" not in html                 # no rate, not even 0.0%
    assert ">A<" not in html
    assert "Not measurable" in html


def test_a_not_measurable_row_says_why_it_could_not_be_measured():
    html = _accuracy_html(_cfg(), [_obj(fact=_not_measurable_fact())])
    assert "0 comparable" in html
    assert "100 unverifiable" in html
    assert "not graded" in html


def test_a_not_measurable_row_is_not_presented_as_still_locked():
    """The user paid for this run. It renders as measured-and-ungradeable, not
    as one of the three rows they never bought."""
    html = _accuracy_html(_cfg(), [_obj(fact=_not_measurable_fact())])
    assert html.count("LOCKED") == 3
    assert "Employee-count accuracy" in html


def test_a_not_measurable_row_produces_no_accuracy_grade_on_the_card():
    html = render_report([_obj(fact=_not_measurable_fact())], _cfg())
    assert ACCURACY_COLUMN not in html     # no accuracy grade column
    assert "Not measurable" in html


# --- CRITICAL 2: the trust claim must match what actually happened ----------

FREE_SCOPE_CLAIM = "Nothing left this machine."
FREE_FOOTER_CLAIM = "Read-only. Your rows never left this machine."


def test_the_free_tier_privacy_claims_are_untouched_without_an_accuracy_fact():
    html = render_report([_obj()], _cfg())
    assert FREE_SCOPE_CLAIM in html
    assert FREE_FOOTER_CLAIM in html


def test_both_privacy_claims_change_once_an_accuracy_fact_is_present():
    """Domains in the sample went to third-party providers. The strongest trust
    claim on the page cannot keep saying otherwise."""
    html = render_report([_obj(with_unlock=True)], _cfg())
    assert FREE_SCOPE_CLAIM not in html
    assert FREE_FOOTER_CLAIM not in html
    assert "never left this machine" not in html
    assert html.count("your own Deepline account") >= 2
    assert "company domains in the verified sample" in html


def test_a_not_measurable_run_also_changes_the_privacy_claims():
    """Nothing came back, but the domains still left the machine."""
    html = render_report([_obj(fact=_not_measurable_fact())], _cfg())
    assert FREE_SCOPE_CLAIM not in html
    assert FREE_FOOTER_CLAIM not in html


# --- CRITICAL 3: the card says what "wrong" means ---------------------------

def test_the_accuracy_row_explainer_is_the_plays_comparison_rule():
    html = _accuracy_html(_cfg(), [_obj(with_unlock=True)])
    assert f'<p class="sigexp">{RULE}</p>' in html


def test_the_explainer_is_never_empty_on_an_accuracy_row():
    for fact in (_fact(), _not_measurable_fact()):
        html = _accuracy_html(_cfg(), [_obj(fact=fact)])
        assert '<p class="sigexp"></p>' not in html


# --- IMPORTANT 5: the presentation layer knows the row can unlock -----------

def test_the_card_reads_as_locked_before_any_play_has_run():
    html = render_report([_obj()], _cfg())
    assert '<div class="st">Locked</div>' in html
    assert "Neither can tell you if the data is <b>accurate</b>" in html
    assert "The accuracy grade is one step away" in html
    assert "Accuracy: unlock stage 02" in html


def test_the_card_stops_calling_accuracy_locked_once_a_play_has_run():
    html = render_report([_obj(with_unlock=True)], _cfg())
    assert "Neither can tell you if the data is <b>accurate</b>" not in html
    assert "The accuracy grade is one step away" not in html
    assert "Accuracy: unlock stage 02" not in html
    assert '<div class="st">Unlocked</div>' in html
    # The remaining three rows are still locked and still say so.
    assert _accuracy_html(_cfg(), [_obj(with_unlock=True)]).count("LOCKED") == 3
    # Stage 03 keeps its locked chip.
    assert '<div class="st">Locked</div>' in html


# --- IMPORTANT 6: the accuracy grade reaches the card ----------------------

def test_the_accuracy_grade_renders_beside_the_completeness_grade():
    html = render_report([_obj(with_unlock=True)], _cfg())
    assert COMPLETENESS_COLUMN in html
    assert ACCURACY_COLUMN in html


def test_no_accuracy_column_before_any_play_has_run():
    html = render_report([_obj()], _cfg())
    assert COMPLETENESS_COLUMN in html
    assert ACCURACY_COLUMN not in html


# --- IMPORTANT 10 + minors: what the provenance line has to disclose --------

def test_provenance_discloses_that_the_sample_includes_flagged_records():
    html = _accuracy_html(_cfg(), [_obj(with_unlock=True)])
    assert "including records other checks on this card already flagged" in html


def test_provenance_reports_records_skipped_for_a_blank_stored_value():
    html = _accuracy_html(_cfg(), [_obj(fact=_fact(skipped_blank=7))])
    assert "7 skipped because the stored value was blank" in html


def test_a_small_comparable_count_is_qualified_as_low_confidence():
    """1 of 3 comparable must not read like 33 of 100."""
    html = _accuracy_html(_cfg(), [_obj(fact=_fact(sample_size=5, checked=3,
                                                   mismatched=1, rate=1 / 3))])
    assert "33.3%" in html                      # the number is not suppressed
    assert "rough signal, not a precise measurement" in html


def test_a_large_comparable_count_is_not_qualified():
    html = _accuracy_html(_cfg(), [_obj(with_unlock=True)])
    assert "rough signal" not in html


def test_accuracy_registry_stays_in_step_with_the_unlock_keys():
    """render_html and unlock name the same three signals. If one drifts, a row
    silently stops unlocking."""
    from crm_report_card.render_html import _ACCURACY_REGISTRY
    from crm_report_card.unlock import ACCURACY_UNLOCKS
    assert tuple(key for key, _label, _rate in _ACCURACY_REGISTRY) == ACCURACY_UNLOCKS


# --- MINOR: the emailed summary and the citation styling -------------------

def test_the_emailed_summary_includes_a_measurable_accuracy_row():
    """They paid for this row and the mail body ends by offering to talk about
    it, so leaving it out of the summary is the one row missing."""
    from urllib.parse import unquote
    from crm_report_card.render_html import build_mailto
    decoded = unquote(build_mailto(_cfg(), [_obj(with_unlock=True)]))
    assert "Employee-count accuracy" in decoded
    assert "32.6% (F)" in decoded


def test_the_emailed_summary_omits_a_not_measurable_accuracy_row():
    from urllib.parse import unquote
    from crm_report_card.render_html import build_mailto
    decoded = unquote(build_mailto(_cfg(), [_obj(fact=_not_measurable_fact())]))
    assert "Employee-count accuracy" not in decoded


def test_the_provenance_line_has_a_style_rule():
    """<p class="prov"> with no .prov rule renders the citation as body text."""
    html = render_report([_obj(with_unlock=True)], _cfg())
    assert ".prov{" in html
