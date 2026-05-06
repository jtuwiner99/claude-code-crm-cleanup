#!/usr/bin/env python3
"""
Engagement-report renderer: turn an enriched CSV + recipe + QA report into a
stakeholder-facing markdown brief.

Designed to be the closing artifact of a `/crm-cleanup` run — the file you'd
hand to a CRO/RevOps lead. Pure markdown, no infrastructure, no portal.

Inputs (defaults work for the standard `/crm-cleanup` flow):
    --enriched  tmp/enriched-flat.csv
    --recipe    tmp/recipe.yaml
    --qa        tmp/qa-report.md                    (optional — included if present)
    --workflow  tmp/workflows/latest-workflow.json  (optional — Phase 5 pointer)
    --output    tmp/engagement-report.md
    --client-name   "your accounts"  (header substitution; pass for personalization)

Auto-extracted findings (only surface what the data actually shows):
    - Acquired companies needing rerouting (`is_acquired=true`)
    - Subsidiaries / parent-routing candidates (`relationship_type=subsidiary`)
    - Dead / unreachable domains (`is_live=false`, `research_status=failed`,
      or `routing_flag=drop`)
    - Industry / taxonomy distribution (counts per enum)
    - Geo distribution (verified country code) when present

Phase 5 close (optional): if the `--workflow` pointer exists, the report
appends a "Live workflow" section with the hosted-workflow ID, name, smoke
test status, and per-deploy artifact paths.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import re
import sys
from collections import Counter
from datetime import datetime
from typing import Iterable

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def _load_rows(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _load_recipe_properties(recipe_path: pathlib.Path) -> list[dict]:
    """Pull `properties:` list from a tmp/recipe.yaml-shaped file. Returns
    [{name, description}]. Returns [] if the file is missing or yaml is unavailable.
    Tolerant of small format drift — falls back to scanning column headers from
    the enriched CSV if recipe.yaml isn't there."""
    if not recipe_path.exists():
        return []
    try:
        import yaml
    except ImportError:
        return []
    try:
        data = yaml.safe_load(recipe_path.read_text()) or {}
    except yaml.YAMLError:
        return []
    props = data.get("properties") or []
    if isinstance(props, list):
        out = []
        for p in props:
            if isinstance(p, dict):
                name = p.get("name")
                desc = p.get("description") or ""
                if name:
                    out.append({"name": str(name), "description": str(desc).strip()})
        return out
    return []


def _load_workflow_pointer(path: pathlib.Path) -> dict | None:
    """Load the Phase 5 latest-workflow.json pointer if present. Returns
    None if missing or unparseable."""
    if not path.exists():
        return None
    try:
        import json
        return json.loads(path.read_text())
    except (Exception,):
        return None


def _parse_qa_summary(qa_path: pathlib.Path) -> dict | None:
    """Pull headline accuracy + per-field % from a qa-report.md file."""
    if not qa_path.exists():
        return None
    text = qa_path.read_text()
    m = re.search(r"\*\*Overall accuracy: ([\d.]+)%\*\* \((\d+)/(\d+) cells\)", text)
    if not m:
        return None
    overall_pct = float(m.group(1))
    pass_cells = int(m.group(2))
    total_cells = int(m.group(3))
    per_field: list[tuple[str, int, int, int]] = []
    for fm in re.finditer(r"\| `(\w+)` \| (\d+) \| (\d+) \| (\d+)% \|", text):
        per_field.append((fm.group(1), int(fm.group(2)), int(fm.group(3)), int(fm.group(4))))
    return {
        "overall_pct": overall_pct,
        "pass_cells": pass_cells,
        "total_cells": total_cells,
        "per_field": per_field,
    }


# ---------------------------------------------------------------------------
# Findings (only surface what the data shows)
# ---------------------------------------------------------------------------

def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in ("true", "yes", "1", "y")


def _falsy_string(v) -> bool:
    if v is None:
        return True
    return str(v).strip().lower() in ("", "false", "no", "0", "n", "none", "null", "nan")


def _domain(row: dict) -> str:
    return (row.get("domain") or row.get("domain_clean") or row.get("domain_input_raw") or "?").lower()


def _company(row: dict) -> str:
    return row.get("company_name") or row.get("company_name_clean") or _domain(row)


def _find_acquired(rows: list[dict]) -> list[dict]:
    """Return rows where is_acquired=true. Sorted alphabetically."""
    out = []
    for r in rows:
        if "is_acquired" not in r:
            continue
        if _truthy(r.get("is_acquired")):
            out.append({
                "domain": _domain(r),
                "company": _company(r),
                "acquirer": (r.get("acquirer_name") or r.get("parent_name") or "?").strip() or "?",
            })
    return sorted(out, key=lambda x: x["company"].lower())


def _find_subsidiaries(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        rel = (r.get("relationship_type") or "").strip().lower()
        if rel == "subsidiary":
            out.append({
                "domain": _domain(r),
                "company": _company(r),
                "parent": (r.get("parent_name") or "?").strip() or "?",
            })
    return sorted(out, key=lambda x: x["company"].lower())


def _find_dead(rows: list[dict]) -> list[dict]:
    """Only flag a domain as dead when the recipe explicitly says so. We do NOT
    infer death from research_status=failed — research can fail for many reasons
    (rate limit, transient error, scraper edge case) and false positives here
    would put real companies on a "drop" list."""
    out = []
    for r in rows:
        is_live = r.get("is_live")
        routing = (r.get("routing_flag") or "").strip().lower()
        flag = False
        if is_live is not None and str(is_live).strip() != "" and _falsy_string(is_live):
            flag = True
        elif routing == "drop":
            flag = True
        if flag:
            out.append({"domain": _domain(r), "company": _company(r)})
    return sorted(out, key=lambda x: x["domain"])


def _distribution(rows: list[dict], col: str, top_n: int = 6) -> list[tuple[str, int]]:
    """Counter for a column's values. Empty values bucketed under '(unknown)'."""
    if not rows or col not in rows[0]:
        return []
    counter: Counter = Counter()
    for r in rows:
        v = (r.get(col) or "").strip()
        counter[v if v else "(unknown)"] += 1
    return counter.most_common(top_n)


def _has_column(rows: list[dict], col: str) -> bool:
    return bool(rows) and col in rows[0]


# ---------------------------------------------------------------------------
# Sample rows
# ---------------------------------------------------------------------------

def _interestingness(row: dict) -> int:
    """Higher = more interesting to show as a sample. Acquired/subsidiary/dead beat clean rows."""
    score = 0
    if _truthy(row.get("is_acquired")):
        score += 3
    if (row.get("relationship_type") or "").strip().lower() == "subsidiary":
        score += 2
    if (row.get("routing_flag") or "").strip().lower() in ("reroute_to_acquirer", "verify_parent_routing", "drop"):
        score += 2
    if (row.get("research_status") or "").strip().lower() == "failed":
        score += 1
    return score


def _sample_rows(rows: list[dict], properties: list[str], n: int = 5) -> list[dict]:
    """Pick up to n rows, biased toward the ones with the most signal."""
    if not rows:
        return []
    scored = sorted(rows, key=_interestingness, reverse=True)
    # Take the top N but ensure at least one "boring" clean row for contrast.
    if n > 1 and any(_interestingness(r) == 0 for r in rows):
        clean = next((r for r in rows if _interestingness(r) == 0), None)
        chosen = scored[: n - 1] + ([clean] if clean is not None else [])
    else:
        chosen = scored[:n]
    seen = set()
    out = []
    for r in chosen:
        d = _domain(r)
        if d in seen:
            continue
        seen.add(d)
        out.append(r)
    return out[:n]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _md_table(headers: list[str], rows: Iterable[Iterable[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return out


def render(
    enriched_rows: list[dict],
    properties: list[dict],
    qa_summary: dict | None,
    client_name: str,
    workflow_pointer: dict | None = None,
) -> str:
    n_rows = len(enriched_rows)
    lines: list[str] = []

    # Header
    title = f"CRM cleanup — {client_name}"
    lines.append(f"# {title}")
    lines.append(f"*Run completed {datetime.now().strftime('%Y-%m-%d %H:%M')} — {n_rows} accounts*")
    lines.append("")

    # What we measured
    lines.append("## What we measured")
    lines.append("")
    if properties:
        for p in properties:
            # Collapse the description into a single line, then cap at ~140
            # chars with an ellipsis. Sentence-boundary detection trips on
            # abbreviations like "e.g." / "i.e." so we don't try to be clever.
            desc = " ".join(p["description"].split()).strip()
            if desc:
                if len(desc) > 140:
                    desc = desc[:137].rstrip() + "…"
                lines.append(f"- **{p['name']}** — {desc}")
            else:
                lines.append(f"- **{p['name']}**")
    else:
        # Fall back to the verdict columns we can see in the data
        candidate_props = []
        skip = {"domain", "company_name", "domain_clean", "domain_input_raw",
                "company_name_clean", "research_status", "_metadata"}
        first = enriched_rows[0] if enriched_rows else {}
        for k in first:
            if k in skip or k.startswith("_"):
                continue
            candidate_props.append(k)
        if candidate_props:
            for k in candidate_props[:8]:
                lines.append(f"- **{k}**")
        else:
            lines.append("- (no recipe found and no enriched columns to summarize)")
    lines.append("")

    # Top findings
    lines.append("## Top findings")
    lines.append("")
    any_finding = False

    acquired = _find_acquired(enriched_rows)
    if acquired:
        any_finding = True
        lines.append(f"### {len(acquired)} acquired companies — reroute to acquirer")
        lines.append("")
        lines.append("Sales motion should target the parent. The on-record domain is no longer the buying entity.")
        lines.append("")
        lines.extend(_md_table(
            ["On record", "Acquired by", "Domain"],
            [(a["company"], a["acquirer"], a["domain"]) for a in acquired[:15]],
        ))
        if len(acquired) > 15:
            lines.append(f"\n*…and {len(acquired) - 15} more.*")
        lines.append("")

    subs = _find_subsidiaries(enriched_rows)
    if subs:
        any_finding = True
        lines.append(f"### {len(subs)} subsidiaries — verify parent routing")
        lines.append("")
        lines.append("Independent legal entities that roll up to a parent. Parent-account ownership may apply.")
        lines.append("")
        lines.extend(_md_table(
            ["Subsidiary", "Parent", "Domain"],
            [(s["company"], s["parent"], s["domain"]) for s in subs[:10]],
        ))
        lines.append("")

    dead = _find_dead(enriched_rows)
    if dead:
        any_finding = True
        lines.append(f"### {len(dead)} dead / unreachable domains — drop")
        lines.append("")
        for d in dead[:10]:
            lines.append(f"- `{d['domain']}` ({d['company']})")
        if len(dead) > 10:
            lines.append(f"- …and {len(dead) - 10} more.")
        lines.append("")

    # Industry / taxonomy distribution — try a few likely column names
    for col in ("industry", "industry_label", "company_type", "category"):
        if _has_column(enriched_rows, col):
            dist = _distribution(enriched_rows, col, top_n=8)
            if dist:
                any_finding = True
                lines.append(f"### {col} distribution")
                lines.append("")
                lines.extend(_md_table(
                    [col, "count", "%"],
                    [(v or "(unknown)", c, f"{c/n_rows*100:.0f}%") for v, c in dist],
                ))
                lines.append("")
            break

    # Geo distribution
    if _has_column(enriched_rows, "verified_country_code"):
        dist = _distribution(enriched_rows, "verified_country_code", top_n=8)
        if dist and any(v for v, _ in dist):
            any_finding = True
            lines.append("### geo distribution (verified country)")
            lines.append("")
            lines.extend(_md_table(
                ["country", "count", "%"],
                [(v or "(unknown)", c, f"{c/n_rows*100:.0f}%") for v, c in dist],
            ))
            lines.append("")

    if not any_finding:
        lines.append("*No notable verdicts surfaced — every account looks clean and standalone.*")
        lines.append("")

    # Accuracy
    if qa_summary:
        lines.append("## Accuracy")
        lines.append("")
        bar = "█" * int(qa_summary["overall_pct"] / 5) + "░" * (20 - int(qa_summary["overall_pct"] / 5))
        lines.append(f"**{qa_summary['overall_pct']:.1f}%** ({qa_summary['pass_cells']}/{qa_summary['total_cells']} cells against your regression dataset)")
        lines.append("")
        lines.append(f"`{bar}` {qa_summary['overall_pct']:.1f}%")
        lines.append("")
        if qa_summary["per_field"]:
            lines.append("Per-field:")
            lines.append("")
            for name, p, t, pct in qa_summary["per_field"]:
                lines.append(f"- `{name}`: {p}/{t} ({pct}%)")
            lines.append("")
        lines.append("*Cell-by-cell breakdown in `tmp/qa-report.md`.*")
        lines.append("")

    # Sample rows — pick property columns to display, but never duplicate the
    # row label (which already shows company name + domain).
    skip_in_sample = {"domain", "company_name", "domain_clean", "domain_input_raw",
                      "company_name_clean", "_metadata", "research_status"}
    sample_props: list[str] = []
    for p in properties:
        if p["name"] not in skip_in_sample and p["name"] not in sample_props:
            sample_props.append(p["name"])
    if not sample_props and enriched_rows:
        for k in enriched_rows[0]:
            if k not in skip_in_sample and not k.startswith("_") and len(sample_props) < 5:
                sample_props.append(k)

    if enriched_rows and sample_props:
        lines.append("## Sample rows")
        lines.append("")
        chosen = _sample_rows(enriched_rows, sample_props, n=5)
        # Truncate long values for table sanity
        def _trim(v: str, w: int = 60) -> str:
            v = (v or "").strip().replace("\n", " ").replace("|", "\\|")
            return v if len(v) <= w else v[:w - 1] + "…"

        headers = ["company"] + sample_props[:5]
        rows_table = []
        for r in chosen:
            row_vals = [_trim(_company(r), 24)] + [_trim(str(r.get(p, "")), 60) for p in sample_props[:5]]
            rows_table.append(row_vals)
        lines.extend(_md_table(headers, rows_table))
        lines.append("")

    # Live workflow (Phase 5) — only when promote_to_workflow.py has run
    if workflow_pointer:
        lines.append("## Live Deepline workflow")
        lines.append("")
        wf_name = workflow_pointer.get("workflow_name") or "(unnamed)"
        wf_id = workflow_pointer.get("workflow_id") or "(no id)"
        trig = workflow_pointer.get("trigger_type") or "api"
        deployed = workflow_pointer.get("deployed_at") or ""
        lines.append(f"This playbook was promoted to a hosted Deepline workflow — same logic, now with a shareable DAG and persistent run history.")
        lines.append("")
        lines.append(f"- **Name:** `{wf_name}`")
        lines.append(f"- **Workflow ID:** `{wf_id}`")
        lines.append(f"- **Trigger:** `{trig}`")
        if deployed:
            lines.append(f"- **Deployed:** {deployed}")
        smoke = workflow_pointer.get("smoke_test")
        if smoke:
            run_id = smoke.get("run_id") or "(no run id)"
            status = smoke.get("status") or "unknown"
            domain = smoke.get("domain") or "?"
            lines.append(f"- **Smoke test:** `{domain}` → run `{run_id}` ({status})")
        archive = workflow_pointer.get("archive_dir")
        if archive:
            lines.append(f"- **Per-deploy artifacts:** `{archive}/`")
        lines.append("")
        lines.append(f"Invoke live: `deepline workflows call --workflow-id {wf_id} --payload '{{\"domain\":\"<domain>\",\"company_name\":\"<name>\"}}'`")
        lines.append("")

    # Next steps
    lines.append("## Next steps")
    lines.append("")
    if acquired:
        lines.append(f"- **Reroute {len(acquired)} acquired-company accounts** to their acquirers before the next QBR.")
    if subs:
        lines.append(f"- **Verify parent-routing on {len(subs)} subsidiaries** — confirm whether your account ownership rules treat them independently.")
    if dead:
        lines.append(f"- **Drop {len(dead)} dead / unreachable domains** from active outreach lists.")
    if not (acquired or subs or dead):
        lines.append("- No routing changes recommended — the cleanup pass surfaced no acquisitions, subsidiaries, or dead domains.")
    lines.append("- Review the per-row enriched output at `tmp/enriched-flat.csv` and write back to your CRM.")
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a stakeholder-facing engagement report from enriched CRM data.",
    )
    parser.add_argument("--enriched", type=pathlib.Path,
                        default=ROOT / "tmp" / "enriched-flat.csv",
                        help="Flat enriched CSV (default: tmp/enriched-flat.csv).")
    parser.add_argument("--recipe", type=pathlib.Path,
                        default=ROOT / "tmp" / "recipe.yaml",
                        help="Recipe yaml with `properties:` (default: tmp/recipe.yaml).")
    parser.add_argument("--qa", type=pathlib.Path,
                        default=ROOT / "tmp" / "qa-report.md",
                        help="QA report markdown (default: tmp/qa-report.md). Optional.")
    parser.add_argument("--workflow", type=pathlib.Path,
                        default=ROOT / "tmp" / "workflows" / "latest-workflow.json",
                        help="Phase 5 workflow pointer (default: tmp/workflows/latest-workflow.json). Optional.")
    parser.add_argument("--output", type=pathlib.Path,
                        default=ROOT / "tmp" / "engagement-report.md",
                        help="Output markdown path (default: tmp/engagement-report.md).")
    parser.add_argument("--client-name", type=str, default="your accounts",
                        help="Header substitution. Pass for personalization (e.g. 'Acme SaaS').")
    args = parser.parse_args()

    if not args.enriched.exists():
        print(f"ERROR: enriched CSV not found: {args.enriched}", file=sys.stderr)
        return 2

    rows = _load_rows(args.enriched)
    properties = _load_recipe_properties(args.recipe)
    qa_summary = _parse_qa_summary(args.qa)
    workflow_pointer = _load_workflow_pointer(args.workflow)

    md = render(rows, properties, qa_summary, args.client_name, workflow_pointer)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md)

    print(f"Engagement report: {args.output}")
    print(f"  {len(rows)} accounts summarized")
    if properties:
        print(f"  {len(properties)} properties from recipe")
    if qa_summary:
        print(f"  QA: {qa_summary['overall_pct']:.1f}% accuracy")
    if workflow_pointer:
        print(f"  Live workflow: {workflow_pointer.get('workflow_name')} ({workflow_pointer.get('workflow_id')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
