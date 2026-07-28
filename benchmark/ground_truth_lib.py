"""Pure logic for the ground-truth review console. Standard library only --
no Flask, no network calls. This is the layer tests/test_ground_truth_console.py
exercises, so the suite runs under plain `python3 -m pytest` even on a machine
that has never installed Flask.

benchmark/ground_truth_console.py imports this module and adds only the Flask
routes, HTML, and server startup on top.

Purpose: the operator hand-verifies all 100 companies in domains.csv and
records, per company, the true employee count and the correct LinkedIn
company page, each with a citation. See METHODOLOGY.md for why this has to be
a human pass and why LinkedIn cannot be the truth source for headcount.

Reads  benchmark/domains.csv            (domain, tier, note)
Writes benchmark/ground_truth.jsonl      (append-only; crash-safe)

Resume: on restart, any domain already present in ground_truth.jsonl (in any
row) is skipped; the operator picks up wherever they stopped. A correction is
just a new appended row for the same domain -- last row wins for any reader.

BLIND BY DESIGN -- read this before touching this file:
This module must NEVER read, load, display, or link to benchmark/raw_results.csv
or benchmark/ourplay_results.csv. Those hold provider answers, and the
benchmark's validity depends on ground truth being recorded without seeing
them (METHODOLOGY.md, "Anchoring control"). Do not add a "compare" or "hint"
feature, even if it looks convenient.

The evidence split (also load-bearing, see METHODOLOGY.md):
  - Headcount evidence is NEVER LinkedIn. We surface the company's own site
    and Google queries aimed at an about/careers page and at filings.
  - LinkedIn IS the correct source for identity (which LinkedIn page is
    right is literally the second value being recorded).
"""
from __future__ import annotations

import csv
import json
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

SOURCE_TYPES = ("filing", "company_page", "third_party", "none")


def load_domains(path) -> list[dict]:
    """Read domains.csv into a list of {domain, tier, note} dicts, in file
    order. Blank domain cells are skipped rather than erroring, since a
    trailing blank line in the CSV is normal."""
    p = Path(path)
    rows: list[dict] = []
    with p.open(newline="") as f:
        for row in csv.DictReader(f):
            domain = (row.get("domain") or "").strip()
            if not domain:
                continue
            rows.append({
                "domain": domain,
                "tier": (row.get("tier") or "").strip(),
                "note": (row.get("note") or "").strip(),
            })
    return rows


def load_ground_truth(path) -> list[dict]:
    """Read every JSON line from ground_truth.jsonl, in file order. A
    malformed line is skipped (warn-and-continue), never fatal -- the file is
    append-only and a half-written last line from a crash should not block
    resume."""
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def recorded_domains(rows: list[dict]) -> set[str]:
    """Domains with at least one row already recorded -- any row counts,
    including a 'no ground truth' row, since that IS the recorded outcome for
    that domain."""
    return {r["domain"] for r in rows if r.get("domain")}


def pending(domains: list[dict], rows: list[dict]) -> list[dict]:
    """Domains from domains.csv with no row yet in ground_truth.jsonl, in
    original domains.csv order. This is the resume queue."""
    done = recorded_domains(rows)
    return [d for d in domains if d["domain"] not in done]


def latest_by_domain(rows: list[dict]) -> dict[str, dict]:
    """Last-row-wins per domain. A correction is a new appended row for the
    same domain; since file order is chronological, a later dict assignment
    overwrites the earlier one -- no explicit timestamp comparison needed."""
    out: dict[str, dict] = {}
    for r in rows:
        if r.get("domain"):
            out[r["domain"]] = r
    return out


def make_record(domain: str, tier: str = "", *, true_employee_count=None,
                 true_linkedin_url: str = "", citation_url: str = "",
                 source_type: str = "", note: str = "",
                 no_ground_truth: bool = False) -> dict:
    """Build one ground-truth record. Raises ValueError on a bad source_type
    or an employee count that doesn't parse as an int -- both are cheap to
    catch here rather than downstream in the JSONL."""
    if source_type and source_type not in SOURCE_TYPES:
        raise ValueError(f"source_type must be one of {SOURCE_TYPES}, got {source_type!r}")
    count = None
    if not no_ground_truth and true_employee_count not in (None, ""):
        try:
            count = int(true_employee_count)
        except (TypeError, ValueError):
            raise ValueError(f"true_employee_count must be an integer, got {true_employee_count!r}")
    return {
        "domain": domain,
        "tier": tier,
        "true_employee_count": None if no_ground_truth else count,
        "true_linkedin_url": "" if no_ground_truth else (true_linkedin_url or "").strip(),
        "citation_url": "" if no_ground_truth else (citation_url or "").strip(),
        "source_type": "none" if no_ground_truth else (source_type or "none"),
        "note": (note or "").strip(),
        "no_ground_truth": bool(no_ground_truth),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def append_record(path, record: dict) -> None:
    """Append one JSON line and close (flushing) the file. Crash-safe by
    construction: every submit is a single append, never a rewrite of the
    whole file, so a kill mid-session loses at most the row in flight."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(record) + "\n")


# --------------------------------------------------------------------------
# Evidence link builders -- pure string/URL construction, no network calls.
# Headcount evidence deliberately excludes LinkedIn; identity evidence is
# LinkedIn-only, opened out-of-band in a reused browser window (console JS).
# --------------------------------------------------------------------------

def site_url(domain: str) -> str:
    return f"https://{domain}"


def google_about_url(domain: str) -> str:
    q = f'site:{domain} (about OR "about us" OR careers OR team OR "who we are")'
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(q)


def google_filing_url(domain: str) -> str:
    q = (f'{domain} (SEC filing OR "10-K" OR "annual report" OR '
         f'"Companies House" OR prospectus) employees')
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(q)


def linkedin_search_url(domain: str) -> str:
    return ("https://www.linkedin.com/search/results/companies/?keywords="
             + urllib.parse.quote_plus(domain))


def evidence_for(domain: str) -> dict:
    return {
        "site_url": site_url(domain),
        "google_about_url": google_about_url(domain),
        "google_filing_url": google_filing_url(domain),
        "linkedin_search_url": linkedin_search_url(domain),
    }
