from crm_report_card.render_terminal import render_terminal


def _metrics(ai=None):
    return {
        "product_name": "The CRM Report Card",
        "counts": {"records": 18412},
        "facts": {
            "duplicates": {"duplicate_rate": 0.116, "grade": "F"},
            "fill_rate": {"overall_missing_rate": 0.41, "grade": "F"},
            "contradictions": {"rate": 0.02, "grade": "B"},
            "junk": {"junk_rate": 0.05, "grade": "C"},
            "staleness": {"stale_rate": 0.22, "grade": "F"},
            "liveness": {"dead_rate": 0.09, "bot_blocked": 40, "grade": "C"},
        },
        "overall_grade": "D",
        "ai_baseline": ai,
    }


def test_terminal_has_counts_facts_and_grade():
    out = render_terminal(_metrics())
    assert "18412" in out or "18,412" in out
    assert "[FACT]" in out
    assert "OVERALL GRADE: D" in out
    assert "not run" in out.lower()


def test_terminal_shows_unverified_estimate():
    out = render_terminal(_metrics(ai={"qualified_estimate": 0.34, "reasons": ["x"], "sample_size": 250, "verified": False}))
    assert "ESTIMATE" in out and "NOT VERIFIED" in out
    assert "34" in out


def _contact_metrics():
    return {
        "product_name": "The CRM Report Card",
        "counts": {"records": 500},
        "facts": {
            "duplicates": {"duplicate_rate": 0.02, "grade": "B"},
            "fill_rate": {"overall_missing_rate": 0.15, "grade": "C"},
            "contradictions": {"rate": 0.01, "grade": "A"},
            "junk": {"junk_rate": 0.03, "grade": "B"},
            "staleness": {"stale_rate": 0.10, "grade": "C"},
            "orphaned": {"orphaned_rate": 0.08, "grade": "C"},
            "email_format": {"invalid_rate": 0.04, "grade": "B"},
        },
        "overall_grade": "C",
        "ai_baseline": None,
    }


def test_terminal_contact_mode_renders_without_keyerror():
    out = render_terminal(_contact_metrics())
    assert "Orphaned contacts" in out
    assert "Invalid email format" in out
    assert "Dead domains" not in out


def test_terminal_company_mode_still_shows_dead_domains():
    out = render_terminal(_metrics())
    assert "Dead domains" in out
