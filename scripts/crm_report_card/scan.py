"""Compose the deterministic checks into one metrics dict."""
from __future__ import annotations
from datetime import date
from .config import RunConfig
from .loader import load_records
from .field_mapping import CANONICAL_ROLES
from .checks.duplicates import check_duplicates
from .checks.fill_rate import check_fill_rate
from .checks.contradictions import check_contradictions
from .checks.junk import check_junk
from .checks.staleness import check_staleness
from .checks.liveness import check_liveness, default_fetcher
from .grading import grade_rate, overall_grade

_ANNUAL_ROT = 0.30


def run_scan(records: list[dict], cfg: RunConfig, today: date, fetcher=None) -> dict:
    dup = check_duplicates(records, object_type=cfg.object_type)
    fill = check_fill_rate(records, cfg.critical_properties)
    contra = check_contradictions(records)
    junk = check_junk(records)
    stale = check_staleness(records, today=today)
    live = check_liveness(records, fetcher=fetcher or default_fetcher)

    dup["grade"] = grade_rate(dup["duplicate_rate"])
    fill["grade"] = grade_rate(fill["overall_missing_rate"])
    contra["grade"] = grade_rate(contra["rate"])
    junk["grade"] = grade_rate(junk["junk_rate"])
    stale["grade"] = grade_rate(stale["stale_rate"])
    live["grade"] = grade_rate(live["dead_rate"])

    grades = [dup["grade"], fill["grade"], contra["grade"], junk["grade"], stale["grade"], live["grade"]]
    n = len(records)
    return {
        "product_name": cfg.product_name,
        "counts": {"records": n},
        "facts": {
            "duplicates": dup, "fill_rate": fill, "contradictions": contra,
            "junk": junk, "staleness": stale, "liveness": live,
        },
        "overall_grade": overall_grade(grades),
        "decay": {
            "annual_rot_rate": _ANNUAL_ROT,
            "projected_next_quarter_added_rot": round(n * _ANNUAL_ROT / 4),
        },
        "ai_baseline": None,
    }


def scan_from_files(csv_path: str, cfg: RunConfig, today: date, fetcher=None) -> dict:
    extra = [p for p in cfg.critical_properties if p not in CANONICAL_ROLES]
    records, _ = load_records(csv_path, cfg.field_mapping, extra_columns=extra,
                              object_type=cfg.object_type)
    return run_scan(records, cfg, today=today, fetcher=fetcher)
