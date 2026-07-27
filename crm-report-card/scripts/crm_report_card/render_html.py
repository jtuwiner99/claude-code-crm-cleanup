"""Render the self-contained, interactive, unified (companies+contacts) HTML
report card: drill-down evidence per FACT, HubSpot deep-links, and an offer
close. No network calls; nothing leaves the machine."""
from __future__ import annotations
import os
from string import Template
from urllib.parse import quote
from .config import RunConfig
from .grading import overall_grade

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

# One-line explainer per signal, reused from the approved mockup. "duplicates"
# and "junk" vary slightly by object type since the underlying match key
# differs (domain+name vs. email).
_EXPLAINERS = {
    "duplicates": {
        "company": "The same company entered more than once (exact domain + fuzzy name). Inflates counts, splits history.",
        "contact": "The same contact entered more than once (matched by email). Inflates counts, splits history.",
    },
    "fill_rate": "Blank values in the fields you said matter.",
    "contradictions": "Stated company size does not match the number of distinct contacts on file.",
    "junk": "Free-mail domains posing as companies, generic inboxes, test rows.",
    "staleness": "No recorded activity in 12+ months.",
    "liveness": "The company website does not resolve. Bot-blocked sites shown separately, never counted as dead.",
    "orphaned": "Contacts with no associated company. Invisible to account-based plays.",
    "email_format": "Not even shaped like an email. Guaranteed bounces before deliverability is checked.",
}

# F worst, A best; used to rank the three worst signals for the tiles row.
_GRADE_BADNESS = {"F": 4, "D": 3, "C": 2, "B": 1, "A": 0}

# The accuracy axis (stage 02): the file cannot prove these; they come from the
# cheap, tried-and-true Sculpted plays the user runs themselves.
_ACCURACY_ROWS = [
    "Employee-count accuracy, verified vs stored",
    "Email deliverability, not just format",
    "Still-employed accuracy, real not timestamp",
]

_HUBSPOT_OBJECT_TYPE_IDS = {"company": "0-2", "contact": "0-1"}


def _pct(rate: float) -> str:
    return f"{rate * 100:.1f}%"


def _hubspot_url(portal_id: str, object_type: str, record_id: str) -> str:
    """Deep-link to a HubSpot record for one-click verification. Empty string
    if either the portal id or the record id is missing (nothing to link to)."""
    if not portal_id or not record_id:
        return ""
    obj = _HUBSPOT_OBJECT_TYPE_IDS.get(object_type, object_type)
    return f"https://app.hubspot.com/contacts/{portal_id}/record/{obj}/{record_id}"


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


def _explainer(key: str, object_type: str) -> str:
    exp = _EXPLAINERS.get(key, "")
    if isinstance(exp, dict):
        return exp.get(object_type, next(iter(exp.values()), ""))
    return exp


def build_mailto(cfg: RunConfig, objects: list[dict]) -> str:
    grades = [obj["metrics"]["overall_grade"] for obj in objects]
    grade = overall_grade(grades) if grades else "N/A"
    lines = [f"My CRM Report Card summary (Grade: {grade})", ""]
    for obj in objects:
        metrics = obj["metrics"]
        facts = metrics["facts"]
        title = "Companies" if obj["object_type"] == "company" else "Contacts"
        lines.append(f"{title}:")
        for key, label, rate_key in _FACT_REGISTRY:
            if key not in facts:
                continue
            lines.append(f"- {label}: {_pct(facts[key][rate_key])} ({facts[key]['grade']})")
        ai = metrics.get("ai_baseline")
        if ai:
            lines.append(f"- Qualified (ESTIMATE, unverified): ~{ai['qualified_estimate'] * 100:.0f}%")
        lines.append("")
    lines.append("I'd like to talk about the accuracy grade.")
    subject = quote(f"My CRM Report Card (Grade: {grade})")
    body = quote("\n".join(lines))
    return f"mailto:{cfg.contact_email}?subject={subject}&body={body}"


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


def _example_row_html(cfg: RunConfig, object_type: str, ex: dict) -> str:
    label = ex.get("label", "")
    detail = ex.get("detail", "")
    record_id = ex.get("record_id", "")
    url = _hubspot_url(cfg.portal_id, object_type, record_id)
    if url:
        meta = f'<a href="{url}" target="_blank" rel="noopener">verify &#8599;</a>'
    else:
        meta = f"row {record_id}"
    return (
        '<div class="ex"><span class="w">'
        f'<b>{label}</b>{" &middot; " + detail if detail else ""}'
        f'</span><span class="meta">{meta}</span></div>'
    )


def _sig_html(cfg: RunConfig, object_type: str, key: str, label: str, rate_key: str, fact: dict,
              list_files: dict) -> str:
    grade = fact["grade"]
    rate = fact[rate_key]
    fcls = " f" if grade == "F" else ""
    width = min(rate * 100, 100)
    explainer = _explainer(key, object_type)
    extra = f" &middot; bot-blocked: {fact['bot_blocked']}" if key == "liveness" and "bot_blocked" in fact else ""

    examples = fact.get("examples") or []
    offending_ids = fact.get("offending_ids") or []
    total = len(offending_ids)
    shown = len(examples)

    csv_name = (list_files or {}).get(key)
    csv_link = f' <a href="{csv_name}">Download all {total} as CSV</a>' if csv_name else ""

    ex_rows = "\n".join(_example_row_html(cfg, object_type, ex) for ex in examples)

    return (
        f'<div class="sig"><button class="sigbtn">\n'
        f'  <div class="sigtop"><span class="signame"><span class="chev">&#9656;</span>'
        f'<span class="tag">FACT</span>{label}{extra}</span>'
        f'<span class="sigval">{_pct(rate)} <span class="grade{fcls}">{grade}</span></span></div>\n'
        f'  <div class="bartrack"><div class="barfill{fcls}" style="width:{width:.0f}%"></div></div>\n'
        f'  <p class="sigexp">{explainer}</p></button>\n'
        f'  <div class="detail"><div class="exhead">Showing {shown} of {total}.{csv_link}</div>\n'
        f'  {ex_rows}\n'
        f'  </div></div>'
    )


def _scope_line(objects: list[dict]) -> str:
    parts = []
    for obj in objects:
        n = obj["metrics"]["counts"]["records"]
        label = "companies" if obj["object_type"] == "company" else "contacts"
        parts.append(f"<b>{n:,} {label}</b>")
    tail = ("Click any line item to see the actual records and verify them in your CRM. "
            "Nothing left this machine.")
    if len(parts) == 2:
        return f"Analyzed both objects: {parts[0]} and {parts[1]}. {tail}"
    if len(parts) > 2:
        return f"Analyzed {', '.join(parts[:-1])}, and {parts[-1]}. {tail}"
    if parts:
        return f"Analyzed {parts[0]}. {tail}"
    return ""


def _segment_html(obj: dict, cfg: RunConfig) -> str:
    object_type = obj["object_type"]
    metrics = obj["metrics"]
    list_files = obj.get("list_files") or {}
    facts = metrics["facts"]
    grade = metrics["overall_grade"]
    n = metrics["counts"]["records"]
    title = "Companies" if object_type == "company" else "Contacts"

    present = [(key, label, rate_key) for key, label, rate_key in _FACT_REGISTRY if key in facts]
    ranked = sorted(
        present,
        key=lambda t: (_GRADE_BADNESS.get(facts[t[0]]["grade"], 0), facts[t[0]][t[2]]),
        reverse=True,
    )
    worst = ranked[:3]

    tiles = [f'<div class="tile"><div class="n">{n:,}</div><div class="l">records scanned</div></div>']
    for key, label, rate_key in worst:
        rate = facts[key][rate_key]
        cls = " bad" if facts[key]["grade"] in ("D", "F") else ""
        tiles.append(f'<div class="tile"><div class="n{cls}">{_pct(rate)}</div><div class="l">{label.lower()}</div></div>')
    tiles_html = "\n".join(tiles)

    sig_html = "\n".join(
        _sig_html(cfg, object_type, key, label, rate_key, facts[key], list_files)
        for key, label, rate_key in present
    )

    badge_cls = " ok" if grade in ("A", "B") else ""
    verdict = _verdict(grade)

    return (
        f'<div class="seg">\n'
        f'  <div class="seghead"><div><h2>{title}</h2>'
        f'<div class="cnt">{n:,} records &middot; completeness grade &middot; {verdict}</div></div>'
        f'<div class="gradebadge{badge_cls}">{grade}</div></div>\n'
        f'  <div class="tiles">{tiles_html}</div>\n'
        f'  {sig_html}\n'
        f'</div>'
    )


def render_report(objects: list[dict], cfg: RunConfig, template: str | None = None) -> str:
    """Render the unified interactive report card for one or more objects
    (each `{"object_type": "company"|"contact", "metrics": {...},
    "list_files": {signal: filename}}`). One `.seg` block per object."""
    if template is None:
        with open(os.path.normpath(_TEMPLATE_PATH), encoding="utf-8") as fh:
            template = fh.read()

    segments = "\n".join(_segment_html(obj, cfg) for obj in objects)
    grades = [obj["metrics"]["overall_grade"] for obj in objects]
    grade = overall_grade(grades) if grades else "N/A"

    ai_obj = next((obj for obj in objects if obj["metrics"].get("ai_baseline")), None)
    estimate_block = _estimate_html(ai_obj["metrics"] if ai_obj else {"ai_baseline": None})

    return Template(template).substitute(
        product_name=cfg.product_name,
        overall_grade=grade,
        verdict=_verdict(grade),
        scope_line=_scope_line(objects),
        segments=segments,
        estimate_block=estimate_block,
        accuracy_rows=_locked_list_html(accuracy_rows()),
        custom_rows=_locked_list_html(custom_rows(cfg)),
        nudge=_nudge(grade),
        mailto=build_mailto(cfg, objects),
        booking_url=cfg.booking_url,
    )


def render_html(metrics: dict, cfg: RunConfig, template: str | None = None) -> str:
    """Single-object entry point (used by the existing CLI `render` command and
    older tests). Delegates to `render_report` with one object built from cfg."""
    object_type = getattr(cfg, "object_type", "company")
    return render_report([{"object_type": object_type, "metrics": metrics}], cfg, template)
