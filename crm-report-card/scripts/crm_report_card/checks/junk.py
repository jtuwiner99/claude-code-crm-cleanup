"""Junk detection: free-mail-as-company, generic contacts, test records."""
from __future__ import annotations

import re

_FREE_MAIL = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
              "icloud.com", "protonmail.com", "gmx.com", "mail.com", "yandex.com"}
_GENERIC_LOCALPARTS = {"info", "sales", "support", "admin", "contact", "hello", "office"}
_TEST_PATTERN = re.compile(r"\b(?:test|demo|asdf|example)\b")
_MAX_EXAMPLES = 12


def _email_domain(email: str) -> str:
    return email.split("@", 1)[1].strip().lower() if "@" in email else ""


def _email_local(email: str) -> str:
    return email.split("@", 1)[0].strip().lower() if "@" in email else ""


def check_junk(records: list[dict]) -> dict:
    total = len(records)
    free_mail = generic = test = 0
    junk_ids: set[str] = set()
    offending_ids: list[str] = []
    examples: list[dict] = []
    for rec in records:
        rid = rec["record_id"]
        domain = (rec.get("domain") or "").strip().lower()
        email = (rec.get("email") or "").strip().lower()
        name = (rec.get("company_name") or "").strip().lower()
        reasons: list[str] = []
        if domain in _FREE_MAIL or _email_domain(email) in _FREE_MAIL:
            free_mail += 1
            reasons.append("free-mail domain as company")
        if _email_local(email) in _GENERIC_LOCALPARTS:
            generic += 1
            reasons.append("generic inbox")
        blob = f"{name} {email} {domain}"
        if _TEST_PATTERN.search(blob):
            test += 1
            reasons.append("test/demo record")
        if reasons:
            junk_ids.add(rid)
            offending_ids.append(rid)
            if len(examples) < _MAX_EXAMPLES:
                label = (rec.get("email") or "").strip() or (rec.get("company_name") or "").strip() or rid
                examples.append({
                    "record_id": rid,
                    "label": label,
                    "detail": ", ".join(reasons),
                })
    return {
        "free_mail_as_company": free_mail,
        "generic_contacts": generic,
        "test_records": test,
        "total_junk": len(junk_ids),
        "junk_rate": (len(junk_ids) / total) if total else 0.0,
        "examples": examples,
        "offending_ids": offending_ids,
    }
