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
        {"record_id": "0", "domain": "live.com"},
        {"record_id": "1", "domain": "blocked.com"},
        {"record_id": "2", "domain": "dead.com"},
        {"record_id": "3", "domain": "live.com"},   # duplicate, dedup
        {"record_id": "4", "domain": ""},           # skip
    ]
    table = {"live.com": (200, False), "blocked.com": (403, False), "dead.com": (None, True)}
    out = check_liveness(recs, fetcher=lambda d: table[d])
    assert out["checked"] == 3
    assert out["live"] == 1
    assert out["bot_blocked"] == 1
    assert out["dead"] == 1
    assert abs(out["dead_rate"] - 1 / 3) < 1e-9
    # only the one record on the dead domain is offending; bot_blocked never counted
    assert out["offending_ids"] == ["2"]
    assert len(out["examples"]) == 1
    ex = out["examples"][0]
    assert set(ex.keys()) == {"record_id", "label", "detail"}
    assert ex["label"] == "dead.com"
    assert ex["record_id"] == "2"


def test_bot_blocked_never_counted_dead():
    recs = [{"record_id": "0", "domain": "shielded.com"}]
    out = check_liveness(recs, fetcher=lambda d: (403, False))
    assert out["dead"] == 0
    assert out["bot_blocked"] == 1
    assert out["offending_ids"] == []
    assert out["examples"] == []


def test_liveness_offending_ids_include_all_records_on_dead_domain():
    recs = [
        {"record_id": "0", "domain": "dead.com"},
        {"record_id": "1", "domain": "dead.com"},
        {"record_id": "2", "domain": "live.com"},
    ]
    table = {"dead.com": (None, True), "live.com": (200, False)}
    out = check_liveness(recs, fetcher=lambda d: table[d])
    assert out["dead"] == 1
    assert set(out["offending_ids"]) == {"0", "1"}
    assert len(out["offending_ids"]) == 2
    # examples deduped to one per dead domain
    assert len(out["examples"]) == 1
