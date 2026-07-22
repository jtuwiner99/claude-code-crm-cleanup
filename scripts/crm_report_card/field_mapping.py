"""Map arbitrary CRM column headers to canonical roles."""
from __future__ import annotations
import re

CANONICAL_ROLES = ("company_name", "domain", "contact_name", "email",
                   "company_size", "last_activity", "record_id")

_SYNONYMS = {
    "company_name": ("company", "account", "organization", "org", "business", "company name"),
    "domain": ("domain", "website", "url", "web", "site", "company domain"),
    "contact_name": ("contact", "name", "full name", "person", "lead"),
    "email": ("email", "e-mail", "email address", "work email"),
    "company_size": ("employees", "employee count", "size", "headcount", "num employees"),
    "last_activity": ("last activity", "last modified", "updated", "last contacted",
                      "modified date", "last touch"),
    "record_id": ("record id", "record_id", "id", "hs object id", "crm id"),
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def auto_map(headers: list[str]) -> dict[str, str]:
    normed = {h: _norm(h) for h in headers}
    mapping: dict[str, str] = {}
    for role, syns in _SYNONYMS.items():
        for header, nh in normed.items():
            if nh in syns or any(nh == _norm(s) for s in syns):
                mapping[role] = header
                break
        if role in mapping:
            continue
        for header, nh in normed.items():
            if any(_norm(s) in nh for s in syns):
                mapping[role] = header
                break
    return mapping


def resolve_mapping(headers: list[str], overrides: dict[str, str]) -> dict[str, str]:
    mapping = auto_map(headers)
    header_set = set(headers)
    for role, header in overrides.items():
        if role in CANONICAL_ROLES and header in header_set:
            mapping[role] = header
    return mapping
