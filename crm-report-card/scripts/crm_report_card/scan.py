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
from .checks.orphaned import check_orphaned
from .checks.email_format import check_email_format
from .grading import grade_rate, overall_grade

_ANNUAL_ROT = 0.30


def run_scan(records: list[dict], cfg: RunConfig, today: date, fetcher=None) -> dict:
    dup = check_duplicates(records, object_type=cfg.object_type)
    fill = check_fill_rate(records, cfg.critical_properties)
    junk = check_junk(records)
    stale = check_staleness(records, today=today)

    dup["grade"] = grade_rate(dup["duplicate_rate"])
    fill["grade"] = grade_rate(fill["overall_missing_rate"])
    junk["grade"] = grade_rate(junk["junk_rate"])
    stale["grade"] = grade_rate(stale["stale_rate"])

    facts = {"duplicates": dup, "fill_rate": fill, "junk": junk, "staleness": stale}
    grades = [dup["grade"], fill["grade"], junk["grade"], stale["grade"]]

    if cfg.object_type == "contact":
        orphaned = check_orphaned(records)
        email_format = check_email_format(records)
        orphaned["grade"] = grade_rate(orphaned["orphaned_rate"])
        email_format["grade"] = grade_rate(email_format["invalid_rate"])
        facts["orphaned"] = orphaned
        facts["email_format"] = email_format
        grades += [orphaned["grade"], email_format["grade"]]
    else:
        # Contradictions compare the STATED company size against the number of
        # distinct contacts on a domain, so it needs BOTH of those inputs. It is
        # a company-object check (we do not map company size onto contacts), and
        # even on a companies file it is only reportable when the export carries
        # emails: a standard HubSpot companies export has no email column, so
        # the comparison never fires and the check would print a structural
        # 0.0% (A) for something it never measured. Omit it instead.
        has_size = any((rec.get("company_size") or "").strip() for rec in records)
        has_email = any((rec.get("email") or "").strip() for rec in records)
        if has_size and has_email:
            contra = check_contradictions(records)
            contra["grade"] = grade_rate(contra["rate"])
            facts["contradictions"] = contra
            grades.append(contra["grade"])
        live = check_liveness(records, fetcher=fetcher or default_fetcher)
        live["grade"] = grade_rate(live["dead_rate"])
        facts["liveness"] = live
        grades.append(live["grade"])

    n = len(records)
    return {
        "product_name": cfg.product_name,
        "object_type": cfg.object_type,
        "counts": {"records": n},
        "facts": facts,
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
