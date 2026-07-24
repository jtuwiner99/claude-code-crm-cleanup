"""Exact-domain and fuzzy-name duplicate detection."""
from __future__ import annotations
import re
from difflib import SequenceMatcher

_FUZZY_THRESHOLD = 0.90
_MAX_EXAMPLES = 12

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


def _label(rec: dict, *roles: str) -> str:
    for role in roles:
        val = (rec.get(role) or "").strip()
        if val:
            return val
    return rec.get("record_id", "")


def check_duplicates(records: list[dict], object_type: str = "company") -> dict:
    total = len(records)

    if object_type == "contact":
        seen_emails: set[str] = set()
        dupe_count = 0
        offending_ids: list[str] = []
        examples: list[dict] = []
        for rec in records:
            email = (rec.get("email") or "").strip().lower()
            if not email:
                continue
            if email in seen_emails:
                dupe_count += 1
                rid = rec.get("record_id", "")
                offending_ids.append(rid)
                if len(examples) < _MAX_EXAMPLES:
                    examples.append({
                        "record_id": rid,
                        "label": email,
                        "detail": f"duplicate email {email}",
                    })
            else:
                seen_emails.add(email)
        return {
            "total_records": total,
            "exact_domain_dupes": 0,
            "fuzzy_name_dupes": 0,
            "duplicate_records": dupe_count,
            "duplicate_rate": (dupe_count / total) if total else 0.0,
            "examples": examples,
            "offending_ids": offending_ids,
        }

    seen_domains: set[str] = set()
    exact_ids: set[str] = set()
    offending_ids: list[str] = []
    examples: list[dict] = []
    for rec in records:
        dom = (rec.get("domain") or "").strip().lower()
        if not dom:
            continue
        if dom in seen_domains:
            rid = rec.get("record_id", "")
            exact_ids.add(rid)
            offending_ids.append(rid)
            if len(examples) < _MAX_EXAMPLES:
                examples.append({
                    "record_id": rid,
                    "label": _label(rec, "company_name", "domain"),
                    "detail": f"shares domain {dom}",
                })
        else:
            seen_domains.add(dom)

    fuzzy_ids: set[str] = set()
    prior_names: list[str] = []
    prior_originals: list[str] = []
    for rec in records:
        rid = rec.get("record_id", "")
        if rid in exact_ids:
            continue
        name = _norm_name(rec.get("company_name") or "")
        if not name:
            continue
        match_idx = None
        for i, p in enumerate(prior_names):
            if SequenceMatcher(None, name, p).ratio() >= _FUZZY_THRESHOLD:
                match_idx = i
                break
        if match_idx is not None:
            fuzzy_ids.add(rid)
            offending_ids.append(rid)
            if len(examples) < _MAX_EXAMPLES:
                matched_name = prior_originals[match_idx]
                examples.append({
                    "record_id": rid,
                    "label": _label(rec, "company_name", "domain"),
                    "detail": f"fuzzy match to {matched_name}",
                })
        else:
            prior_names.append(name)
            prior_originals.append((rec.get("company_name") or "").strip())

    dupes = len(exact_ids) + len(fuzzy_ids)
    return {
        "total_records": total,
        "exact_domain_dupes": len(exact_ids),
        "fuzzy_name_dupes": len(fuzzy_ids),
        "duplicate_records": dupes,
        "duplicate_rate": (dupes / total) if total else 0.0,
        "examples": examples,
        "offending_ids": offending_ids,
    }
