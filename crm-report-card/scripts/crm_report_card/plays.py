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
