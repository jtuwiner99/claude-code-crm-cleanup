"""The play registry: what each accuracy play unlocks, what it needs, what it costs.

The registry is the contract between the driver skill and the play sources. It is
data, not code, so adding a play is a folder plus a row.
"""
from __future__ import annotations
import json
from .field_mapping import roles_for

REQUIRED_FIELDS = ("id", "unlocks", "object_type", "label", "requires_roles",
                   "providers", "cost_per_record_usd", "default_sample",
                   "comparison_rule")

_VALID_OBJECT_TYPES = ("company", "contact")


def load_registry(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return list(raw.get("plays", []))


def validate_registry(entries: list[dict]) -> list[str]:
    """Return a list of human-readable errors. Empty means the registry is valid.

    A typo'd role would otherwise disable a play silently and permanently, so
    role names are checked against the canonical set for that object type.
    """
    errors: list[str] = []
    seen_unlocks: set[str] = set()

    for entry in entries:
        ident = entry.get("id", "<no id>")

        for field in REQUIRED_FIELDS:
            if field not in entry:
                errors.append(f"{ident}: missing required field '{field}'")

        object_type = entry.get("object_type")
        if object_type not in _VALID_OBJECT_TYPES:
            errors.append(f"{ident}: object_type must be one of {_VALID_OBJECT_TYPES}")
            continue

        valid_roles = roles_for(object_type)
        for role in entry.get("requires_roles", []):
            if role not in valid_roles:
                errors.append(
                    f"{ident}: requires_roles has '{role}', which is not a canonical "
                    f"role on {object_type} records"
                )

        unlock = entry.get("unlocks")
        if unlock in seen_unlocks:
            errors.append(f"{ident}: duplicate unlocks key '{unlock}'")
        seen_unlocks.add(unlock)

    return errors


def _missing_roles(entry: dict, mapping: dict) -> list[str]:
    return [role for role in entry.get("requires_roles", []) if role not in mapping]


def eligible_plays(entries: list[dict], object_type: str, mapping: dict) -> list[dict]:
    """Plays that match this object and whose every required role resolved."""
    return [e for e in entries
            if e.get("object_type") == object_type and not _missing_roles(e, mapping)]


def blocked_plays(entries: list[dict], object_type: str,
                  mapping: dict) -> list[tuple[dict, list[str]]]:
    """Plays that match this object but lack a column, paired with what is missing."""
    out = []
    for entry in entries:
        if entry.get("object_type") != object_type:
            continue
        missing = _missing_roles(entry, mapping)
        if missing:
            out.append((entry, missing))
    return out


import random

# Deepline bills in credits. Verified 2026-07-27 against `deepline billing
# balance --json`: balance 668 credits reported as rough_usd_balance 66.8.
CREDIT_USD = 0.10


def eligible_records(records: list[dict], play: dict) -> list[dict]:
    """Records this play can actually check: every required role is filled.

    A blank stored value is a COMPLETENESS defect, already graded by the free
    scan's fill-rate check. Including it here would let a missing value show up
    a second time as an accuracy failure.
    """
    roles = play.get("requires_roles", [])
    return [rec for rec in records
            if all((rec.get(role) or "").strip() for role in roles)]


def draw_sample(records: list[dict], size: int, seed: int) -> list[dict]:
    """A reproducible random sample. Never the flagged subset.

    Sampling records the free scan already flagged would inflate the accuracy
    failure rate and make the book look worse than it is.
    """
    pool = list(records)
    if size >= len(pool):
        return pool
    rng = random.Random(seed)
    return rng.sample(pool, size)


def estimate_cost(play: dict, n: int) -> dict:
    usd = float(play.get("cost_per_record_usd", 0.0)) * n
    return {"records": n, "usd": round(usd, 2), "credits": round(usd / CREDIT_USD, 1)}
