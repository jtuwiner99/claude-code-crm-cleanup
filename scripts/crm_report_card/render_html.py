"""Render the self-contained HTML scorecard + mailto offer."""
from __future__ import annotations
import os
from string import Template
from urllib.parse import quote
from .config import RunConfig

_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "scorecard-template.html")

_FACT_REGISTRY = [
    ("duplicates", "Duplicates", "duplicate_rate"),
    ("fill_rate", "Missing critical fields", "overall_missing_rate"),
    ("contradictions", "Internal contradictions", "rate"),
    ("junk", "Junk records", "junk_rate"),
    ("staleness", "Stale (12+ mo)", "stale_rate"),
    ("liveness", "Dead domains", "dead_rate"),
    ("orphaned", "Orphaned contacts", "orphaned_rate"),
    ("email_format", "Invalid email format", "invalid_rate"),
]

# The accuracy axis (stage 02): the file cannot prove these; they come from the
# cheap, tried-and-true Sculpted plays the user runs themselves.
_ACCURACY_ROWS = [
    "Employee-count accuracy, verified vs stored",
    "Email deliverability, not just format",
    "Still-employed accuracy, real not timestamp",
]


def _pct(rate: float) -> str:
    return f"{rate * 100:.1f}%"


def accuracy_rows() -> list[str]:
    return list(_ACCURACY_ROWS)


def custom_rows(cfg: RunConfig) -> list[str]:
    # Stage 03: hand-built by Sculpted, personalized with the fields they named.
    rows = [f"Custom rules and scoring for your {p} data" for p in cfg.critical_properties]
    rows += [
        "Company type / vertical classification",
        "Parent-child account resolution",
        "Custom fit scoring against your ICP",
    ]
    return rows


def locked_rows(cfg: RunConfig) -> list[str]:
    # Everything the free (completeness) scan does not deliver: the accuracy plays
    # plus the custom dimensions.
    return accuracy_rows() + custom_rows(cfg)


def _verdict(grade: str) -> str:
    return {
        "A": "Solid on completeness.",
        "B": "Mostly complete, a few gaps.",
        "C": "Real cleanup to do here.",
        "D": "This book needs work.",
        "F": "This book is in rough shape.",
    }.get(grade, "Here is where your data stands.")


def _nudge(grade: str) -> str:
    if grade in ("D", "F"):
        return "A book at this grade is exactly what Jacob fixes with clients."
    if grade == "C":
        return "There is enough here to be worth a real cleanup."
    return "Want the accuracy grade too? Here is the fast way."


def build_mailto(cfg: RunConfig, metrics: dict) -> str:
    facts = metrics["facts"]
    grade = metrics["overall_grade"]
    lines = [f"My CRM Report Card summary (Grade: {grade})", ""]
    for key, label, rate_key in _FACT_REGISTRY:
        if key not in facts:
            continue
        lines.append(f"- {label}: {_pct(facts[key][rate_key])} ({facts[key]['grade']})")
    ai = metrics.get("ai_baseline")
    if ai:
        lines.append(f"- Qualified (ESTIMATE, unverified): ~{ai['qualified_estimate'] * 100:.0f}%")
    lines += ["", "I'd like to talk about the accuracy grade."]
    subject = quote(f"My CRM Report Card (Grade: {grade})")
    body = quote("\n".join(lines))
    return f"mailto:{cfg.contact_email}?subject={subject}&body={body}"


def _fact_rows_html(metrics: dict) -> str:
    facts = metrics["facts"]
    out = []
    for key, label, rate_key in _FACT_REGISTRY:
        if key not in facts:
            continue
        extra = ""
        if key == "liveness":
            extra = f" &middot; bot-blocked: {facts['liveness']['bot_blocked']}"
        out.append(
            f'<div class="row"><span class="name"><span class="tag">FACT</span> {label}{extra}</span>'
            f'<span class="val">{_pct(facts[key][rate_key])} '
            f'<span class="g">{facts[key]["grade"]}</span></span></div>'
        )
    return "\n".join(out)


def _estimate_html(metrics: dict) -> str:
    ai = metrics.get("ai_baseline")
    if not ai:
        return ('<div class="estimate"><div class="top"><span><span class="etag">ESTIMATE</span> '
                'Qualified %</span><span class="val">not run</span></div></div>')
    reasons = "".join(f"<li>{r}</li>" for r in ai["reasons"])
    return (
        '<div class="estimate"><div class="top">'
        '<span><span class="etag">ESTIMATE: NOT VERIFIED</span> Qualified</span>'
        f'<span class="val">~{ai["qualified_estimate"] * 100:.0f}% (accuracy unmeasured)</span></div>'
        f'<p class="why">Why you can\'t trust this yet:</p><ul>{reasons}</ul></div>'
    )


def _locked_list_html(rows: list[str]) -> str:
    return "\n".join(
        f'<div class="lrow"><span class="lname">{r}</span><span class="lmark">LOCKED</span></div>'
        for r in rows
    )


def render_html(metrics: dict, cfg: RunConfig, template: str | None = None) -> str:
    if template is None:
        with open(os.path.normpath(_TEMPLATE_PATH), encoding="utf-8") as fh:
            template = fh.read()
    grade = metrics["overall_grade"]
    return Template(template).substitute(
        product_name=cfg.product_name,
        overall_grade=grade,
        verdict=_verdict(grade),
        record_count=f'{metrics["counts"]["records"]:,}',
        fact_rows=_fact_rows_html(metrics),
        estimate_block=_estimate_html(metrics),
        accuracy_rows=_locked_list_html(accuracy_rows()),
        custom_rows=_locked_list_html(custom_rows(cfg)),
        nudge=_nudge(grade),
        mailto=build_mailto(cfg, metrics),
        booking_url=cfg.booking_url,
    )
