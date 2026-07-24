"""Map arbitrary CRM column headers to canonical roles."""
from __future__ import annotations
import re

CANONICAL_ROLES = ("company_name", "domain", "contact_name", "email",
                   "company_size", "last_activity", "record_id",
                   "first_name", "last_name")

# Known HubSpot default (and common) property names per role, matched by EXACT
# normalized equality. Conservative on purpose: a header maps to a role only if
# its normalized form is exactly one of these, so we never grab "Company Domain
# Name" for contact_name or a date column for email. A role with no exact match
# is simply left unmapped.
_ROLE_ALIASES = {
    "company_name": {"company name", "company", "account name", "account",
                     "organization", "organization name"},
    "domain": {"company domain name", "domain", "domain name", "website",
               "website url", "company domain", "web domain"},
    "company_size": {"number of employees", "employees", "employee count",
                     "num employees", "headcount", "company size", "size",
                     "total employees"},
    "last_activity": {"last activity date", "last activity", "last modified date",
                      "last modified", "last engagement date", "last engagement"},
    "contact_name": {"contact name", "full name", "contact full name"},
    "email": {"email", "email address", "work email", "contact email"},
    "record_id": {"record id", "company id", "contact id", "object id",
                  "hs object id", "id", "vid"},
    "first_name": {"first name", "firstname", "given name"},
    "last_name": {"last name", "lastname", "surname", "family name"},
}


# Best-effort HubSpot internal property name per role, so the mapping display can
# show the underlying field (e.g. "Number of Employees (numberofemployees)").
ROLE_HUBSPOT_INTERNAL = {
    "company_name": "name",
    "domain": "domain",
    "company_size": "numberofemployees",
    "last_activity": "notes_last_updated",
    "email": "email",
    "contact_name": "firstname / lastname",
    "record_id": "hs_object_id",
    "first_name": "firstname",
    "last_name": "lastname",
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def auto_map(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for role, aliases in _ROLE_ALIASES.items():
        for header in headers:
            if _norm(header) in aliases:
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
