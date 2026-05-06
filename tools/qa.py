#!/usr/bin/env python3
"""
QA grader: score an enriched CSV against a golden EXPECTED dataset.

Reads the flat enriched CSV (`tmp/enriched-flat.csv` by default — emitted
automatically by `tools/enrich.py`) and a golden CSV that has `EXPECTED_<col>`
columns. For each row in golden, joins by normalized domain, then grades each
`EXPECTED_<col>` cell:

  - **Exact-match** (deterministic): booleans, short strings (≤32 chars),
    enums, empty values. Case-insensitive, whitespace-trimmed.
  - **Claude-judged** (semantic): long-form prose like `pitch`, `reasoning`,
    `summary`. Uses Claude Haiku 4.5 with a paraphrase-tolerant rubric.
    Falls back to exact-match if `ANTHROPIC_API_KEY` is missing or the SDK
    is unavailable.

Writes `tmp/qa-report.md`:
  - Headline accuracy %
  - Per-field breakdown (pass/total + %)
  - Failing rows (with expected vs got + grader reasoning)

Usage:
    python tools/qa.py
    python tools/qa.py --enriched tmp/enriched-flat.csv --golden tmp/golden-accounts.csv
    python tools/qa.py --output tmp/qa-report.md
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import re
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# Field-grading thresholds. Keep simple — string length is a good-enough
# heuristic to route between exact and semantic grading.
SEMANTIC_GRADE_MIN_LEN = 33
SEMANTIC_GRADE_FIELDS_FORCE = {"pitch", "reasoning", "summary", "description", "ai_reasoning"}
EXACT_GRADE_FIELDS_FORCE = {"is_acquired", "is_live", "is_keepable", "is_real_business",
                            "routing_flag", "relationship_type", "verified_country_code",
                            "industry", "industry_label", "industry_category",
                            "employee_count_tier", "company_type", "acquirer_name",
                            "acquirer_domain", "parent_name", "parent_domain"}

# Sentinel value that means "this domain is dead — accept any dead/empty Got."
DEAD_DOMAIN_SENTINELS = ("UNREACHABLE_OR_DEAD_DOMAIN", "DEAD_DOMAIN", "NOT_REACHABLE")


def _normalize_domain(d: str | None) -> str:
    if not d:
        return ""
    s = str(d).strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = s.split("/")[0].split("?")[0]
    return s


def _normalize_value(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in ("none", "null", "nan"):
        return ""
    return s


def _is_dead_sentinel(expected: str) -> bool:
    return any(sent in expected.upper() for sent in DEAD_DOMAIN_SENTINELS)


def _grade_exact(expected: str, got: str) -> tuple[bool, str]:
    """Pass if normalized values match case-insensitively. Empty == empty."""
    e = _normalize_value(expected)
    g = _normalize_value(got)

    if _is_dead_sentinel(e):
        # Accept empty got OR any got that flags dead/unreachable
        if not g:
            return True, "matched (golden marks dead; got is empty)"
        if any(t in g.lower() for t in ("dead", "unreachable", "parking", "not real")):
            return True, "matched (golden marks dead; got mentions dead/unreachable)"
        return False, f"golden expected dead-domain handling; got '{g[:60]}'"

    if e.lower() == g.lower():
        return True, "exact match"

    # Boolean tolerance: "true"/"True"/True all match
    if e.lower() in ("true", "false") and g.lower() in ("true", "false"):
        return e.lower() == g.lower(), f"boolean mismatch: expected {e}, got {g}"

    return False, f"expected '{e}', got '{g[:80]}'"


def _grade_semantic(prop: str, expected: str, got: str, anthropic_client) -> tuple[bool, str]:
    """Use Claude Haiku 4.5 to judge semantic equivalence. Returns (pass, reason)."""
    e = _normalize_value(expected)
    g = _normalize_value(got)

    if _is_dead_sentinel(e):
        if not g or any(t in g.lower() for t in ("dead", "unreachable", "could not", "no website")):
            return True, "matched (golden marks dead-domain; got reflects same)"
        return False, f"golden expected dead-domain handling; got prose '{g[:60]}'"

    # Empty handling: empty-vs-empty passes; empty-vs-content fails fast
    if not e and not g:
        return True, "matched (both empty)"
    if not e or not g:
        return False, f"empty mismatch: expected={'<empty>' if not e else f'<{len(e)} chars>'}, got={'<empty>' if not g else f'<{len(g)} chars>'}"

    if anthropic_client is None:
        # Fall back to substring/exact when the SDK is unavailable
        ok = e.lower() in g.lower() or g.lower() in e.lower()
        return ok, "fallback substring match (no Claude available)" if ok else f"substring mismatch (no Claude): expected='{e[:60]}', got='{g[:60]}'"

    prompt = f"""You are grading a CRM enrichment output for semantic equivalence.

Property: {prop}
Expected: {e}
Got: {g}

Does "Got" convey the same core meaning as "Expected"? Allow paraphrasing, different word ordering, and additional detail that doesn't contradict. Reject only if the core meaning differs or key facts are wrong.

Respond with strict JSON, no markdown fences:
{{"pass": true|false, "reasoning": "<one sentence>"}}"""

    try:
        resp = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        # Defensive JSON extraction in case the model wraps in fences anyway
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return False, f"grader returned non-JSON: {text[:120]}"
        verdict = json.loads(m.group(0))
        return bool(verdict.get("pass")), str(verdict.get("reasoning", ""))[:200]
    except Exception as exc:
        return False, f"grader error: {exc.__class__.__name__}: {str(exc)[:120]}"


def _is_semantic_field(prop: str, expected: str) -> bool:
    if prop.lower() in SEMANTIC_GRADE_FIELDS_FORCE:
        return True
    if prop.lower() in EXACT_GRADE_FIELDS_FORCE:
        return False
    return len(_normalize_value(expected)) >= SEMANTIC_GRADE_MIN_LEN


def _enriched_lookup(path: pathlib.Path) -> dict[str, dict]:
    """Index enriched rows by normalized domain. Accepts flat or native CSV.

    For native (deepline) CSVs with a `verdict` JSON column, we lift the
    verdict's `result` keys onto the row so callers can read them flat.
    """
    out: dict[str, dict] = {}
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))

    for r in rows:
        domain = _normalize_domain(r.get("domain") or r.get("domain_clean") or r.get("domain_input_raw"))
        if not domain:
            continue
        # If this looks like a native CSV (has a `verdict` JSON column), lift the keys.
        if "verdict" in r and r["verdict"] and r["verdict"].lstrip().startswith("{"):
            try:
                v = json.loads(r["verdict"]).get("result") or {}
                # Don't overwrite explicit columns already on the row.
                for k, val in v.items():
                    if k not in r or r.get(k) in (None, ""):
                        r[k] = val if not isinstance(val, (dict, list)) else json.dumps(val)
            except (json.JSONDecodeError, AttributeError):
                pass
        out[domain] = r
    return out


def _golden_props(golden_fieldnames: list[str]) -> list[str]:
    """Extract property names from EXPECTED_<prop> golden columns."""
    return [c[len("EXPECTED_"):] for c in golden_fieldnames if c.startswith("EXPECTED_")]


def grade(enriched_path: pathlib.Path, golden_path: pathlib.Path) -> dict:
    """Run the full grading. Returns a structured result dict."""
    if not enriched_path.exists():
        raise FileNotFoundError(f"Enriched CSV not found: {enriched_path}")
    if not golden_path.exists():
        raise FileNotFoundError(f"Golden CSV not found: {golden_path}")

    with open(golden_path, newline="") as f:
        reader = csv.DictReader(f)
        golden_rows = list(reader)
        golden_fields = reader.fieldnames or []

    props = _golden_props(golden_fields)
    if not props:
        raise ValueError(f"No EXPECTED_* columns found in {golden_path}. Add columns like EXPECTED_industry, EXPECTED_is_acquired, etc.")

    enriched = _enriched_lookup(enriched_path)

    # Spin up Claude client lazily (only if we'll actually use it)
    client = None
    will_use_claude = any(_is_semantic_field(p, golden_rows[0].get(f"EXPECTED_{p}", "")) for p in props) and bool(os.environ.get("ANTHROPIC_API_KEY"))
    if will_use_claude:
        try:
            from anthropic import Anthropic
            client = Anthropic()
        except ImportError:
            client = None  # fallback path

    per_field: dict[str, dict] = {p: {"pass": 0, "total": 0, "fails": []} for p in props}
    missing_rows: list[str] = []

    for row in golden_rows:
        domain = _normalize_domain(row.get("domain"))
        if not domain:
            continue
        enr = enriched.get(domain)
        if enr is None:
            missing_rows.append(domain)
            for p in props:
                per_field[p]["total"] += 1
                per_field[p]["fails"].append({
                    "domain": domain,
                    "expected": row.get(f"EXPECTED_{p}", ""),
                    "got": "<row not found in enriched output>",
                    "reasoning": "no matching domain in enriched CSV",
                })
            continue

        for p in props:
            expected = row.get(f"EXPECTED_{p}", "")
            got = enr.get(p, "")
            if _is_semantic_field(p, expected):
                ok, reason = _grade_semantic(p, expected, got, client)
            else:
                ok, reason = _grade_exact(expected, got)
            per_field[p]["total"] += 1
            if ok:
                per_field[p]["pass"] += 1
            else:
                per_field[p]["fails"].append({
                    "domain": domain,
                    "expected": _normalize_value(expected),
                    "got": _normalize_value(got),
                    "reasoning": reason,
                })

    total_cells = sum(d["total"] for d in per_field.values())
    pass_cells = sum(d["pass"] for d in per_field.values())
    overall_pct = (pass_cells / total_cells * 100) if total_cells else 0.0

    return {
        "graded_at": datetime.now().isoformat(timespec="seconds"),
        "enriched_csv": str(enriched_path),
        "golden_csv": str(golden_path),
        "rows_in_golden": len(golden_rows),
        "rows_matched": len(golden_rows) - len(missing_rows),
        "missing_rows": missing_rows,
        "properties": props,
        "per_field": per_field,
        "total_cells": total_cells,
        "pass_cells": pass_cells,
        "overall_pct": overall_pct,
        "grader_used_claude": client is not None,
    }


def render_report(result: dict) -> str:
    lines: list[str] = []
    lines.append("# QA report")
    lines.append("")
    pct = result["overall_pct"]
    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
    lines.append(f"**Overall accuracy: {pct:.1f}%** ({result['pass_cells']}/{result['total_cells']} cells)")
    lines.append("")
    lines.append(f"`{bar}` {pct:.1f}%")
    lines.append("")
    lines.append(f"- Rows in golden: {result['rows_in_golden']}")
    lines.append(f"- Rows matched in enriched: {result['rows_matched']}")
    if result["missing_rows"]:
        lines.append(f"- Missing in enriched: {len(result['missing_rows'])} ({', '.join(result['missing_rows'][:5])}{'...' if len(result['missing_rows']) > 5 else ''})")
    lines.append(f"- Grader: {'Claude Haiku 4.5 + exact-match' if result['grader_used_claude'] else 'exact-match only (no ANTHROPIC_API_KEY)'}")
    lines.append(f"- Graded at: {result['graded_at']}")
    lines.append("")

    lines.append("## Per-field accuracy")
    lines.append("")
    lines.append("| Property | Pass | Total | % |")
    lines.append("|---|---:|---:|---:|")
    for p in result["properties"]:
        d = result["per_field"][p]
        p_pct = (d["pass"] / d["total"] * 100) if d["total"] else 0
        lines.append(f"| `{p}` | {d['pass']} | {d['total']} | {p_pct:.0f}% |")
    lines.append("")

    fail_props = [p for p in result["properties"] if result["per_field"][p]["fails"]]
    if not fail_props:
        lines.append("## Failures")
        lines.append("")
        lines.append("None. Every graded cell passed.")
        return "\n".join(lines) + "\n"

    lines.append("## Failures")
    lines.append("")
    for p in fail_props:
        fails = result["per_field"][p]["fails"]
        lines.append(f"### `{p}` — {len(fails)} fail(s)")
        lines.append("")
        for f in fails:
            lines.append(f"- **{f['domain']}**")
            lines.append(f"  - expected: `{f['expected']}`")
            lines.append(f"  - got: `{f['got']}`")
            lines.append(f"  - {f['reasoning']}")
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Grade an enriched CSV against a golden EXPECTED dataset.",
    )
    parser.add_argument("--enriched", type=pathlib.Path,
                        default=ROOT / "tmp" / "enriched-flat.csv",
                        help="Flat enriched CSV (default: tmp/enriched-flat.csv).")
    parser.add_argument("--golden", type=pathlib.Path,
                        default=ROOT / "tmp" / "golden-accounts.csv",
                        help="Golden CSV with EXPECTED_<col> columns (default: tmp/golden-accounts.csv).")
    parser.add_argument("--output", type=pathlib.Path,
                        default=ROOT / "tmp" / "qa-report.md",
                        help="Markdown report path (default: tmp/qa-report.md).")
    args = parser.parse_args()

    # If the user pointed at a deepline-native enriched.csv but a -flat sibling
    # exists, prefer the flat one — it's what verdict columns live on.
    if args.enriched.name == "enriched.csv":
        flat = args.enriched.with_name("enriched-flat.csv")
        if flat.exists():
            print(f"Using flat enriched CSV: {flat}")
            args.enriched = flat

    try:
        result = grade(args.enriched, args.golden)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(result))

    pct = result["overall_pct"]
    print(f"Overall: {pct:.1f}% ({result['pass_cells']}/{result['total_cells']} cells)")
    for p in result["properties"]:
        d = result["per_field"][p]
        p_pct = (d["pass"] / d["total"] * 100) if d["total"] else 0
        print(f"  {p}: {d['pass']}/{d['total']} ({p_pct:.0f}%)")
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
