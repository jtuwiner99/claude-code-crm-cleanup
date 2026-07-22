"""Render the self-contained HTML scorecard + mailto CTA."""
from __future__ import annotations
import os
from string import Template
from urllib.parse import quote
from .config import RunConfig

_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "scorecard-template.html")

_FACT_LABELS = [
    ("duplicates", "Duplicates", "duplicate_rate"),
    ("fill_rate", "Missing critical fields", "overall_missing_rate"),
    ("contradictions", "Internal contradictions", "rate"),
    ("junk", "Junk records", "junk_rate"),
    ("staleness", "Stale (12+ mo)", "stale_rate"),
    ("liveness", "Dead domains", "dead_rate"),
]


def _pct(rate: float) -> str:
    return f"{rate * 100:.1f}%"


def locked_rows(cfg: RunConfig) -> list[str]:
    rows = [f"Segment your book by {p} [locked]" for p in cfg.critical_properties]
    rows += ["Custom fit scoring [locked]", "Market by segment [locked]"]
    return rows


def build_mailto(cfg: RunConfig, metrics: dict) -> str:
    facts = metrics["facts"]
    grade = metrics["overall_grade"]
    lines = [f"My CRM Report Card summary (Grade: {grade})", ""]
    for key, label, rate_key in _FACT_LABELS:
        lines.append(f"- {label}: {_pct(facts[key][rate_key])} ({facts[key]['grade']})")
    ai = metrics.get("ai_baseline")
    if ai:
        lines.append(f"- Qualified (ESTIMATE, unverified): ~{ai['qualified_estimate'] * 100:.0f}%")
    lines += ["", "I'd like to talk about making this data trustworthy."]
    subject = quote(f"My CRM Report Card (Grade: {grade})")
    body = quote("\n".join(lines))
    return f"mailto:{cfg.contact_email}?subject={subject}&body={body}"


def _fact_rows_html(metrics: dict) -> str:
    facts = metrics["facts"]
    out = []
    for key, label, rate_key in _FACT_LABELS:
        extra = ""
        if key == "liveness":
            extra = f" &middot; bot-blocked: {facts['liveness']['bot_blocked']}"
        out.append(
            f'<div class="row"><span><span class="tag fact">FACT</span> {label}{extra}</span>'
            f'<span>{_pct(facts[key][rate_key])} &middot; {facts[key]["grade"]}</span></div>'
        )
    return "\n".join(out)


def _estimate_html(metrics: dict) -> str:
    ai = metrics.get("ai_baseline")
    if not ai:
        return ('<div class="row"><span><span class="tag estimate">ESTIMATE</span> '
                'Qualified %</span><span>not run</span></div>')
    reasons = "".join(f"<li>{r}</li>" for r in ai["reasons"])
    return (
        f'<div class="row"><span><span class="tag estimate">ESTIMATE: NOT VERIFIED</span> '
        f'Qualified</span><span>~{ai["qualified_estimate"] * 100:.0f}% (accuracy unmeasured)</span></div>'
        f'<p class="sub">Why you can\'t trust this yet:</p><ul class="sub">{reasons}</ul>'
    )


def _locked_html(cfg: RunConfig) -> str:
    return "\n".join(f'<div class="row locked"><span>{r}</span><span>&#128274;</span></div>'
                     for r in locked_rows(cfg))


def render_html(metrics: dict, cfg: RunConfig, template: str | None = None) -> str:
    if template is None:
        with open(os.path.normpath(_TEMPLATE_PATH), encoding="utf-8") as fh:
            template = fh.read()
    return Template(template).substitute(
        product_name=cfg.product_name,
        overall_grade=metrics["overall_grade"],
        record_count=f'{metrics["counts"]["records"]:,}',
        fact_rows=_fact_rows_html(metrics),
        estimate_block=_estimate_html(metrics),
        locked_block=_locked_html(cfg),
        mailto=build_mailto(cfg, metrics),
        booking_url=cfg.booking_url,
    )
