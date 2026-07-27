"""Merge an accuracy play's result into a metrics dict and grade it.

Accuracy facts live in metrics["facts"] under their unlock key. They are
invisible to the completeness renderer, which iterates its own registry, so
adding one cannot change a grade that was already printed.
"""
from __future__ import annotations
import copy
from .grading import grade_rate, overall_grade

ACCURACY_UNLOCKS = ("employee_count_accuracy", "email_deliverability", "still_employed")

_REQUIRED = ("unlock", "object_type", "sample_size", "checked", "mismatched",
             "rate", "unverifiable", "examples", "offending_ids", "provider", "run_at")


def validate_fragment(fragment: dict) -> list[str]:
    errors: list[str] = []
    for field in _REQUIRED:
        if field not in fragment:
            errors.append(f"fragment missing required field '{field}'")
    unlock = fragment.get("unlock")
    if unlock is not None and unlock not in ACCURACY_UNLOCKS:
        errors.append(f"unknown unlock key '{unlock}', expected one of {ACCURACY_UNLOCKS}")
    return errors


def merge_fragment(metrics: dict, fragment: dict) -> dict:
    """Return a new metrics dict with the fragment merged in, idempotently."""
    errors = validate_fragment(fragment)
    if errors:
        raise ValueError("; ".join(errors))

    expected = metrics.get("object_type")
    if not expected:
        raise ValueError(
            "metrics has no object_type, so a fragment cannot be safely attached. "
            "Please re-run the scan to regenerate metrics.json."
        )
    if fragment["object_type"] != expected:
        raise ValueError(
            f"fragment object_type '{fragment['object_type']}' does not match the "
            f"scanned object_type '{expected}'"
        )

    out = copy.deepcopy(metrics)
    fact = dict(fragment)
    fact["grade"] = grade_rate(fragment["rate"])
    # Replacement, not accumulation: re-running a play overwrites its own row.
    out.setdefault("facts", {})[fragment["unlock"]] = fact
    return out


def accuracy_grade(metrics: dict):
    """The accuracy axis grade, or None if nothing has been unlocked yet.

    Deliberately separate from the completeness grade. Averaging accuracy into
    the existing overall grade would retroactively change what a card printed
    yesterday meant.
    """
    facts = metrics.get("facts", {})
    grades = [facts[key]["grade"] for key in ACCURACY_UNLOCKS
              if key in facts and "grade" in facts[key]]
    return overall_grade(grades) if grades else None
