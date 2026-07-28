"""Pure logic for the ground-truth review console. Standard library only --
no Flask, no test needs a network call. This is the layer
tests/test_ground_truth_console.py exercises, so the suite runs under plain
`python3 -m pytest` even on a machine that has never installed Flask.

benchmark/ground_truth_console.py imports this module and adds only the Flask
routes, HTML, and server startup on top (including the /proxy route that
frames a company's homepage -- it calls fetch_url_bytes + strip_frame_guards
here, but the Response object itself is built in the Flask layer).

Purpose: the operator hand-verifies all 100 companies in domains.csv and
records, per company, the true LinkedIn identity AND the reference headcount
in one motion: typing the real count shown on a candidate's LinkedIn People
tab both confirms that candidate is the right company and records the
LinkedIn People-tab count as truth (METHODOLOGY.md, "Ground truth", amended
2026-07-28: the People-tab count is now the reference, since firmographic
providers overwhelmingly derive headcount from LinkedIn-sourced data). A
second, optional, non-LinkedIn `independent_count` with its own citation is
recorded separately where the operator can find one (the framed homepage, an
about/careers page, or a filing); it is not required, and it is scored as its
own secondary table, never averaged into the LinkedIn-referenced number.

Reads  benchmark/domains.csv              (domain, tier, note)
Reads  benchmark/raw_results.csv           (ONLY domain + linkedin_url columns)
Reads  benchmark/ourplay_results.csv       (ONLY domain + linkedin_url columns)
Writes benchmark/ground_truth.jsonl        (append-only; crash-safe)

Resume: on restart, any domain already present in ground_truth.jsonl (in any
row) is skipped; the operator picks up wherever they stopped. A correction is
just a new appended row for the same domain -- last row wins for any reader.

BLIND BY DESIGN -- read this before touching this file:
raw_results.csv and ourplay_results.csv are read for exactly one purpose:
building the unlabeled candidate LinkedIn URL list for a domain. Every
function that touches those files reads ONLY the `domain` and `linkedin_url`
columns -- `provider`, `count`, `band`, `identity_method`, and `error` are
never parsed into anything this module returns, so they can never leak into
the console's JSON or HTML. Never surface which provider produced which
candidate, never surface any provider's employee count, and never add a
"compare" or "hint" feature -- that is exactly the anchoring risk
METHODOLOGY.md's "Anchoring control" section closes off.

The evidence split (also load-bearing, see METHODOLOGY.md):
  - linkedin_people_count is the reference count AND proves identity in one
    step: typing a real number from the LinkedIn People tab records that
    candidate's page as the correct one.
  - independent_count is the optional secondary, non-LinkedIn signal (framed
    homepage, about/careers Google query, filings Google query), recorded
    with its own citation and scored separately, never blended with the
    LinkedIn-referenced number.
"""
from __future__ import annotations

import csv
import hashlib
import html as html_mod
import ipaddress
import json
import random
import re
import socket
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

IDENTITY_VERDICTS = ("correct", "wrong", "no-ground-truth")

_LI_SLUG_RE = re.compile(r"linkedin\.com/company/([^/?#\s]+)", re.IGNORECASE)


# --------------------------------------------------------------------------
# domains.csv / ground_truth.jsonl -- load, resume, append, last-row-wins
# --------------------------------------------------------------------------

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


def pending(domains: list[dict], rows: list[dict], only: set[str] | None = None,
            exclude: set[str] | None = None) -> list[dict]:
    """Domains from domains.csv still needing a console visit, in original
    domains.csv order.

    Default (only=None): the append-only resume queue -- any domain with at
    least one row already in ground_truth.jsonl is skipped.

    only, when given a set of domains, switches to re-review mode for those
    specific rows: the already-recorded skip logic above is bypassed
    entirely, so a domain in `only` is served regardless of what is already
    in ground_truth.jsonl (that is the whole point -- correcting a row
    confirmed against the wrong LinkedIn page). Domains not in `only` are
    never served in this mode, and a domain in `only` that is not in
    domains.csv is simply absent from the result.

    exclude is session-local bookkeeping (not derived from ground_truth.jsonl
    at all): the caller adds a domain to it once it has been re-submitted in
    the current console run, so the --only queue advances to the next
    requested domain instead of re-showing the one just corrected. Ignored
    when only is None."""
    if only is not None:
        exclude = exclude or set()
        return [d for d in domains if d["domain"] in only and d["domain"] not in exclude]
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


def append_record(path, record: dict) -> None:
    """Append one JSON line and close (flushing) the file. Crash-safe by
    construction: every submit is a single append, never a rewrite of the
    whole file, so a kill mid-session loses at most the row in flight."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(record) + "\n")


# --------------------------------------------------------------------------
# The record -- identity_verdict drives which fields are meaningful.
# --------------------------------------------------------------------------

def make_record(domain: str, tier: str = "", *, identity_verdict: str,
                 chosen_linkedin_url: str = "", linkedin_people_count=None,
                 independent_count=None, independent_citation_url: str = "",
                 note: str = "") -> dict:
    """Build one ground-truth record.

    identity_verdict drives the invariant the operator described: typing a
    real LinkedIn People-tab count MEANS the shown/chosen candidate page is
    correct, so 'correct' REQUIRES both linkedin_people_count and
    chosen_linkedin_url and raises otherwise. 'wrong' ("not the right page")
    always nulls both -- no count is recorded against a page that's wrong.
    'no-ground-truth' nulls every value field; the row is genuinely
    unverifiable, on both dimensions, not just the LinkedIn one.

    independent_count / independent_citation_url are a second, optional,
    non-LinkedIn headcount signal (framed homepage / about-careers page /
    filing). They are orthogonal to identity_verdict and pass through as
    given for 'correct' and 'wrong' (a wrong LinkedIn candidate doesn't mean
    the homepage was unreadable); 'no-ground-truth' nulls them too, since
    that verdict means nothing could be verified at all for this company.
    """
    if identity_verdict not in IDENTITY_VERDICTS:
        raise ValueError(f"identity_verdict must be one of {IDENTITY_VERDICTS}, got {identity_verdict!r}")

    def _int_or_none(value, field_name):
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{field_name} must be an integer, got {value!r}")

    if identity_verdict == "no-ground-truth":
        li_count = None
        li_url = ""
        ind_count = None
        ind_cite = ""
    elif identity_verdict == "wrong":
        li_count = None
        li_url = ""
        ind_count = _int_or_none(independent_count, "independent_count")
        ind_cite = (independent_citation_url or "").strip()
    else:  # correct
        li_count = _int_or_none(linkedin_people_count, "linkedin_people_count")
        if li_count is None:
            raise ValueError("linkedin_people_count is required when identity_verdict is 'correct'")
        li_url = (chosen_linkedin_url or "").strip()
        if not li_url:
            raise ValueError("chosen_linkedin_url is required when identity_verdict is 'correct'")
        ind_count = _int_or_none(independent_count, "independent_count")
        ind_cite = (independent_citation_url or "").strip()

    return {
        "domain": domain,
        "tier": tier,
        "identity_verdict": identity_verdict,
        "chosen_linkedin_url": li_url,
        "linkedin_people_count": li_count,
        "independent_count": ind_count,
        "independent_citation_url": ind_cite,
        "note": (note or "").strip(),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# --------------------------------------------------------------------------
# LinkedIn URL / slug handling
# --------------------------------------------------------------------------

def normalize_linkedin_slug(url: str) -> str | None:
    """Extract the normalized company slug from a LinkedIn URL, e.g.
    'linkedin.com/company/stripe' or 'https://www.linkedin.com/company/Stripe/'
    both yield 'stripe'. Returns None if the string has no
    linkedin.com/company/<slug> segment."""
    if not url:
        return None
    m = _LI_SLUG_RE.search(url.strip())
    if not m:
        return None
    slug = m.group(1).strip().lower()
    return slug or None


def linkedin_company_url(slug: str) -> str:
    return f"https://www.linkedin.com/company/{slug}/"


def linkedin_people_url(slug: str) -> str:
    """The People tab -- where the employee count is visible. This is the
    page that auto-opens in the reused browser window, never the plain
    company overview page."""
    return f"https://www.linkedin.com/company/{slug}/people/"


def linkedin_search_url(domain: str) -> str:
    """Fallback when none of the candidates are right: a LinkedIn company
    search for the domain, so the operator can find and paste the correct
    URL themselves."""
    return ("https://www.linkedin.com/search/results/companies/?keywords="
            + urllib.parse.quote_plus(domain))


# --------------------------------------------------------------------------
# Candidate building from raw_results.csv / ourplay_results.csv.
#
# Reads ONLY the domain + linkedin_url columns of each file. Deduplicates by
# normalized slug, then shuffles with a seed derived purely from the domain
# string -- stable across restarts of the console (same domain always
# produces the same order), but the shuffle happens AFTER dedup, so a
# candidate's position carries no information about which provider (or how
# many providers) produced it. Nothing about provider identity is threaded
# through any of this.
# --------------------------------------------------------------------------

def _slugs_from_results_csv(path, domain: str) -> list[str]:
    """Extract LinkedIn company slugs for one domain from a raw_results.csv-
    or ourplay_results.csv-shaped file, in file order. Reads only the
    `domain` and `linkedin_url` columns of each row -- `provider`, `count`,
    `band`, `identity_method`, and `error` (whichever of these the file
    happens to have) are never read into anything returned here."""
    p = Path(path)
    if not p.exists():
        return []
    out: list[str] = []
    with p.open(newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("domain") or "").strip() != domain:
                continue
            slug = normalize_linkedin_slug(row.get("linkedin_url") or "")
            if slug:
                out.append(slug)
    return out


def candidate_slugs_for_domain(domain: str, raw_results_path, ourplay_results_path) -> list[str]:
    """Deduplicated, deterministically-shuffled candidate slug list for one
    domain, combining both result files."""
    combined = (_slugs_from_results_csv(raw_results_path, domain)
                + _slugs_from_results_csv(ourplay_results_path, domain))
    deduped: list[str] = []
    seen: set[str] = set()
    for slug in combined:
        if slug not in seen:
            seen.add(slug)
            deduped.append(slug)
    seed = int(hashlib.sha256(domain.encode("utf-8")).hexdigest(), 16)
    random.Random(seed).shuffle(deduped)
    return deduped


def candidates_for_domain(domain: str, raw_results_path, ourplay_results_path) -> list[dict]:
    """Unlabeled candidate list for the console: each entry is just the
    company page URL and the People-tab URL to auto-open. No id, source, or
    provider tag of any kind."""
    slugs = candidate_slugs_for_domain(domain, raw_results_path, ourplay_results_path)
    return [
        {"company_url": linkedin_company_url(s), "people_url": linkedin_people_url(s)}
        for s in slugs
    ]


# --------------------------------------------------------------------------
# Non-LinkedIn headcount evidence -- site + Google queries aimed at
# about/careers pages and at filings. Never LinkedIn.
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


def row_context_for(domain: str, raw_results_path, ourplay_results_path) -> dict:
    """Everything the console needs to render one row: the homepage to
    frame, the non-LinkedIn evidence links, the unlabeled candidate list, and
    the LinkedIn search fallback. No provider name or count anywhere in this
    structure."""
    return {
        "homepage_url": site_url(domain),
        "google_about_url": google_about_url(domain),
        "google_filing_url": google_filing_url(domain),
        "linkedin_search_url": linkedin_search_url(domain),
        "candidates": candidates_for_domain(domain, raw_results_path, ourplay_results_path),
    }


# --------------------------------------------------------------------------
# Homepage framing -- same pattern as sculpted-skills' qa-console: proxy the
# page same-origin (many sites send X-Frame-Options / CSP that blocks direct
# framing) and strip the framing guards + inject a <base> tag so relative
# asset URLs still resolve. This whole layer is stdlib-only (urllib, socket,
# ipaddress, re, html); only the console.py route wraps the result in a
# Flask Response.
# --------------------------------------------------------------------------

def safe_public_url(url: str) -> bool:
    """Only proxy http(s) URLs that resolve to a public address -- blocks
    loopback/private/link-local/reserved so the pane can't be aimed at
    internal services. Unresolvable hosts are allowed through (the fetch
    just fails)."""
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        infos = socket.getaddrinfo(p.hostname, None)
    except Exception:
        return True
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def strip_frame_guards(html: str, url: str) -> str:
    """Make a fetched page framable + self-contained enough to render in the
    pane: drop meta CSP / X-Frame-Options directives and inject a <base> so
    the page's relative asset URLs resolve against its own origin."""
    html = re.sub(
        r'(?is)<meta[^>]+http-equiv=["\']?(content-security-policy|x-frame-options)["\']?[^>]*>',
        "", html)
    base = '<base href="' + html_mod.escape(url, quote=True) + '">'
    m = re.search(r"(?i)<head[^>]*>", html)
    if m:
        return html[:m.end()] + base + html[m.end():]
    return base + html


def fetch_url_bytes(url: str, timeout: int = 15):
    """Fetch a URL with a full browser-like fingerprint (many sites 403 a
    bare UA) and return (content_type, raw_bytes, final_url). Raises on any
    network/HTTP error -- the caller renders a failure page rather than
    letting an exception surface to the operator. Stdlib-only (urllib); it
    needs network access to do anything useful, which is why tests don't
    exercise it directly (safe_public_url and strip_frame_guards, the parts
    that don't need a live network call, are tested)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"),
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "application/pdf,image/avif,image/webp,image/*,*/*;q=0.8"),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Referer": "https://www.google.com/",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type", "")
        raw = r.read(6_000_000)  # 6 MB cap
        final_url = r.geturl()
    return ctype, raw, final_url
