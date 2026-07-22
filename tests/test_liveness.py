from crm_report_card.checks.liveness import classify, check_liveness


def test_classify_buckets():
    assert classify(200, False) == "live"
    assert classify(301, False) == "live"
    assert classify(403, False) == "bot_blocked"
    assert classify(429, False) == "bot_blocked"
    assert classify(500, False) == "dead"
    assert classify(None, True) == "dead"


def test_check_liveness_with_fake_fetcher():
    recs = [
        {"domain": "live.com"},
        {"domain": "blocked.com"},
        {"domain": "dead.com"},
        {"domain": "live.com"},   # duplicate, dedup
        {"domain": ""},           # skip
    ]
    table = {"live.com": (200, False), "blocked.com": (403, False), "dead.com": (None, True)}
    out = check_liveness(recs, fetcher=lambda d: table[d])
    assert out["checked"] == 3
    assert out["live"] == 1
    assert out["bot_blocked"] == 1
    assert out["dead"] == 1
    assert abs(out["dead_rate"] - 1 / 3) < 1e-9


def test_bot_blocked_never_counted_dead():
    recs = [{"domain": "shielded.com"}]
    out = check_liveness(recs, fetcher=lambda d: (403, False))
    assert out["dead"] == 0
    assert out["bot_blocked"] == 1
