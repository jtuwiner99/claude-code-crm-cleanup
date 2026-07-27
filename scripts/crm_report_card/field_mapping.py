"""Map arbitrary CRM column headers to canonical roles."""
from __future__ import annotations
import re

CANONICAL_ROLES = ("company_name", "domain", "contact_name", "email",
                   "company_size", "last_activity", "record_id",
                   "first_name", "last_name", "associated_company_id")

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
    # The real contact->company link. Preferred over the denormalized
    # company-name text field when deciding whether a contact is orphaned.
    # Deliberately narrow: "company id" / "account id" are NOT listed, because
    # `record_id` already claims them and a mis-grab there would silently key
    # every check off the wrong column.
    "associated_company_id": {"associated company id", "associatedcompanyid",
                              "primary associated company id",
                              "associated company"},
}

# Roles that do not belong on a given object, so auto_map never claims them
# there. A contact does not carry the COMPANY's headcount: HubSpot's
# contact-level "Company size" was 0.2% filled on a real 848-record book, so
# mapping it graded a company property on the wrong object and left the
# contradiction check measuring nothing while still printing a rate.
# `associated_company_id` is the mirror image: a contact->company link that has
# no meaning on a companies export.
_OBJECT_EXCLUDED_ROLES = {
    "contact": {"company_size"},
    "company": {"associated_company_id"},
}

# Per-object alias overrides, applied on top of _ROLE_ALIASES.
_OBJECT_ROLE_ALIASES = {
    "contact": {
        # On a contact, "Website URL" is that person's own site (20.8% filled on
        # a real book) while "Email Domain" is derived from their email address
        # (97.3% filled). Same information, four times the coverage, so contacts
        # key on the email domain and never on a website column. If the export
        # has no email-domain column, the loader derives the domain from the
        # email address itself, which is the identical signal.
        "domain": {"email domain", "hs email domain", "contact email domain"},
    },
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
    "associated_company_id": "associatedcompanyid",
}

# Same role, different underlying property depending on the object.
_OBJECT_HUBSPOT_INTERNAL = {
    "contact": {
        "domain": "hs_email_domain",
        "company_name": "company",
        "last_activity": "notes_last_updated",
    },
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def hubspot_internal(role: str, object_type: str = "company") -> str:
    """The HubSpot internal property name for a role ON THIS OBJECT."""
    per_object = _OBJECT_HUBSPOT_INTERNAL.get(object_type, {})
    return per_object.get(role) or ROLE_HUBSPOT_INTERNAL.get(role, "")


def roles_for(object_type: str = "company") -> tuple[str, ...]:
    """Canonical roles that are meaningful on this object type."""
    excluded = _OBJECT_EXCLUDED_ROLES.get(object_type, set())
    return tuple(role for role in CANONICAL_ROLES if role not in excluded)


def _aliases_for(object_type: str) -> dict[str, set[str]]:
    aliases = {role: set(vals) for role, vals in _ROLE_ALIASES.items()}
    for role, vals in _OBJECT_ROLE_ALIASES.get(object_type, {}).items():
        aliases[role] = set(vals)
    for role in _OBJECT_EXCLUDED_ROLES.get(object_type, set()):
        aliases.pop(role, None)
    return aliases


def auto_map(headers: list[str], object_type: str = "company") -> dict[str, str]:
    mapping: dict[str, str] = {}
    for role, aliases in _aliases_for(object_type).items():
        for header in headers:
            if _norm(header) in aliases:
                mapping[role] = header
                break
    return mapping


def resolve_mapping(headers: list[str], overrides: dict[str, str],
                    object_type: str = "company") -> dict[str, str]:
    mapping = auto_map(headers, object_type)
    header_set = set(headers)
    applicable = set(roles_for(object_type))
    for role, header in overrides.items():
        # An override cannot resurrect a role that does not belong on this
        # object; a stale run-config must not silently re-map company size onto
        # contacts.
        if role in applicable and header in header_set:
            mapping[role] = header
    return mapping
