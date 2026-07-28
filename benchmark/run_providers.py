"""Run each contestant provider over the pre-registered domain list.

Writes one row per (domain, provider) to raw_results.csv. Extracts a headcount
where the provider gives one, and records the raw payload size and any error so
a null answer can be told apart from a failed call.

Deliberately does NOT score anything. Ground truth is logged separately and
blind, and the join happens only after. See METHODOLOGY.md.

Usage:  python3 benchmark/run_providers.py [--limit N] [--dry-run]
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import subprocess
import sys

DEEPLINE = os.path.expanduser("~/.local/bin/deepline")
HERE = os.path.dirname(os.path.abspath(__file__))

# Each contestant: how to call it, and where its headcount lives in the response.
# Paths were confirmed by a live probe on 2026-07-27, not read off a declared
# schema. The declared schema for peopledatalabs omits employee_count entirely
# while the live payload carries it at the top level, which is exactly why every
# path here is probe-verified.
PROVIDERS = [
    {
        "name": "peopledatalabs",
        "tool": "peopledatalabs_enrich_company",
        "param": "domain",
        "count_paths": ["employee_count"],
        "band_paths": ["size"],
        "url_paths": ["linkedin_url"],
    },
    {
        "name": "crustdata",
        "tool": "crustdata_company_enrichment",
        "param": "companyDomain",
        "count_paths": ["employee_count", "headcount"],
        "band_paths": ["employee_count_range"],
        "url_paths": ["linkedin_profile_url", "linkedin_url"],
    },
    {
        "name": "datagma",
        "tool": "datagma_enrich_company",
        "param": "domain",
        "count_paths": ["employeeCount", "employee_count", "staffCount"],
        "band_paths": ["employeeCountRange", "size"],
        "url_paths": ["linkedinUrl", "linkedin_url"],
    },
]


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return proc.stdout or proc.stderr or ""


def _parse_json(text: str):
    """Deepline prints an update banner before its JSON, so slice from the first
    brace rather than parsing the whole stream."""
    i = text.find("{")
    if i < 0:
        return None
    try:
        return json.loads(text[i:])
    except json.JSONDecodeError:
        return None


def _search(obj, keys, depth=0):
    """First scalar value found under any of `keys`, breadth-ish, ignoring the
    nested affiliated-entity records some providers attach."""
    if depth > 4 or obj is None:
        return None
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, (int, float, str)) and str(v).strip():
                return v
        for k, v in obj.items():
            if k in ("affiliated_entities", "similar_companies", "competitors"):
                continue
            found = _search(v, keys, depth + 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj[:3]:
            found = _search(item, keys, depth + 1)
            if found is not None:
                return found
    return None


def call_provider(provider: dict, domain: str) -> dict:
    payload = json.dumps({provider["param"]: domain})
    out = _run([DEEPLINE, "tools", "execute", provider["tool"], "--json", "--input", payload])
    data = _parse_json(out)

    row = {
        "domain": domain,
        "provider": provider["name"],
        "count": "",
        "band": "",
        "linkedin_url": "",
        "error": "",
        "payload_bytes": 0,
    }
    if data is None:
        row["error"] = "unparseable-cli-output"
        return row
    if data.get("ok") is False:
        row["error"] = (data.get("error") or {}).get("message", "")[:160]
        return row

    raw = (data.get("toolResponse") or {}).get("raw")
    row["payload_bytes"] = len(json.dumps(raw)) if raw is not None else 0
    if raw is None:
        row["error"] = "null-payload"
        return row

    count = _search(raw, provider["count_paths"])
    band = _search(raw, provider["band_paths"])
    url = _search(raw, provider.get("url_paths", []))
    row["count"] = "" if count is None else str(count)
    row["band"] = "" if band is None else str(band)
    row["linkedin_url"] = "" if url is None else str(url)

    # Persist the whole payload. Re-extracting a field we forgot should never
    # cost another paid call, which is exactly what happened the first time.
    raw_dir = os.path.join(HERE, "raw_payloads")
    os.makedirs(raw_dir, exist_ok=True)
    safe = domain.replace("/", "_")
    with open(os.path.join(raw_dir, f"{safe}__{provider['name']}.json"), "w", encoding="utf-8") as fh:
        json.dump(raw, fh)
    return row


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only the first N domains")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, call nothing")
    ap.add_argument("--out", default=os.path.join(HERE, "raw_results.csv"))
    args = ap.parse_args(argv)

    with open(os.path.join(HERE, "domains.csv"), newline="", encoding="utf-8") as fh:
        domains = list(csv.DictReader(fh))
    if args.limit:
        domains = domains[: args.limit]

    total = len(domains) * len(PROVIDERS)
    print(f"{len(domains)} domains x {len(PROVIDERS)} providers = {total} calls")
    if args.dry_run:
        for p in PROVIDERS:
            print(f"  {p['name']:16s} {p['tool']} ({p['param']})")
        return 0

    results = []
    for n, d in enumerate(domains, 1):
        for p in PROVIDERS:
            row = call_provider(p, d["domain"])
            row["tier"] = d["tier"]
            results.append(row)
        done = [r for r in results if r["domain"] == d["domain"]]
        got = sum(1 for r in done if r["count"] or r["band"])
        print(f"[{n}/{len(domains)}] {d['domain']:24s} answered by {got}/{len(PROVIDERS)}", flush=True)

    fields = ["domain", "tier", "provider", "count", "band", "linkedin_url", "error", "payload_bytes"]
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(results)
    print(f"wrote {len(results)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
