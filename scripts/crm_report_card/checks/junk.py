"""Junk detection: free-mail-as-company, generic contacts, test records."""
from __future__ import annotations

_FREE_MAIL = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
              "icloud.com", "protonmail.com", "gmx.com", "mail.com", "yandex.com"}
_GENERIC_LOCALPARTS = {"info", "sales", "support", "admin", "contact", "hello", "office"}
_TEST_TOKENS = ("test", "demo", "asdf", "example")


def _email_domain(email: str) -> str:
    return email.split("@", 1)[1].strip().lower() if "@" in email else ""


def _email_local(email: str) -> str:
    return email.split("@", 1)[0].strip().lower() if "@" in email else ""


def check_junk(records: list[dict]) -> dict:
    total = len(records)
    free_mail = generic = test = 0
    junk_ids: set[str] = set()
    for rec in records:
        rid = rec["record_id"]
        domain = (rec.get("domain") or "").strip().lower()
        email = (rec.get("email") or "").strip().lower()
        name = (rec.get("company_name") or "").strip().lower()
        is_junk = False
        if domain in _FREE_MAIL or _email_domain(email) in _FREE_MAIL:
            free_mail += 1
            is_junk = True
        if _email_local(email) in _GENERIC_LOCALPARTS:
            generic += 1
            is_junk = True
        blob = f"{name} {email} {domain}"
        if any(tok in blob for tok in _TEST_TOKENS):
            test += 1
            is_junk = True
        if is_junk:
            junk_ids.add(rid)
    return {
        "free_mail_as_company": free_mail,
        "generic_contacts": generic,
        "test_records": test,
        "total_junk": len(junk_ids),
        "junk_rate": (len(junk_ids) / total) if total else 0.0,
    }
