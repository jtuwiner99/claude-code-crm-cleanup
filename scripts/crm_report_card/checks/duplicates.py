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
    tokens = [t for t in tokens if t not in _LEGAL_SUFFIXES]
    return " ".join(tokens).strip()


def check_duplicates(records: list[dict]) -> dict:
    total = len(records)
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
