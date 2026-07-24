"""Exact-domain and fuzzy-name duplicate detection."""
from __future__ import annotations
import re
from difflib import SequenceMatcher

_FUZZY_THRESHOLD = 0.90

_LEGAL_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation",
    "co", "company", "gmbh", "plc", "sa", "ag", "srl", "bv", "nv", "pty",
    "llp", "lp",
}


def _norm_name(name: str) -> str:
    tokens = re.sub(r"[^a-z0-9]+", " ", name.lower()).split()
    stripped = list(tokens)
    while stripped and stripped[-1] in _LEGAL_SUFFIXES:
        stripped.pop()
    result = " ".join(stripped).strip()
    return result or " ".join(tokens).strip()


def check_duplicates(records: list[dict], object_type: str = "company") -> dict:
    total = len(records)

    if object_type == "contact":
        seen_emails: set[str] = set()
        dupe_count = 0
        for rec in records:
            email = (rec.get("email") or "").strip().lower()
            if not email:
                continue
            if email in seen_emails:
                dupe_count += 1
            else:
                seen_emails.add(email)
        return {
            "total_records": total,
            "exact_domain_dupes": 0,
            "fuzzy_name_dupes": 0,
            "duplicate_records": dupe_count,
            "duplicate_rate": (dupe_count / total) if total else 0.0,
        }

    seen_domains: set[str] = set()
    exact_ids: set[str] = set()
    for rec in records:
        dom = (rec.get("domain") or "").strip().lower()
        if not dom:
            continue
        if dom in seen_domains:
            exact_ids.add(rec["record_id"])
        else:
            seen_domains.add(dom)

    fuzzy_ids: set[str] = set()
    prior_names: list[str] = []
    for rec in records:
        if rec["record_id"] in exact_ids:
            continue
        name = _norm_name(rec.get("company_name") or "")
        if not name:
            continue
        if any(SequenceMatcher(None, name, p).ratio() >= _FUZZY_THRESHOLD for p in prior_names):
            fuzzy_ids.add(rec["record_id"])
        else:
            prior_names.append(name)

    dupes = len(exact_ids) + len(fuzzy_ids)
    return {
        "total_records": total,
        "exact_domain_dupes": len(exact_ids),
        "fuzzy_name_dupes": len(fuzzy_ids),
        "duplicate_records": dupes,
        "duplicate_rate": (dupes / total) if total else 0.0,
    }
