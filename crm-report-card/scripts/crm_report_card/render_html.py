"""Render the self-contained, interactive, unified (companies+contacts) HTML
report card: drill-down evidence per FACT, HubSpot deep-links, and an offer
close. No network calls; nothing leaves the machine."""
from __future__ import annotations
import os
from string import Template
from urllib.parse import quote
from .config import RunConfig
from .grading import overall_grade
from .unlock import accuracy_grade, is_measurable

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

# The accuracy axis (stage 02), in card order: unlock key, label, rate key.
# The keys must stay in step with unlock.ACCURACY_UNLOCKS; a test asserts it.
# `_ACCURACY_ROWS` stays as the label list so `accuracy_rows()` is unchanged.
_ACCURACY_REGISTRY = [
    ("employee_count_accuracy", "Employee-count accuracy, verified vs stored", "rate"),
    ("email_deliverability", "Email deliverability, not just format", "rate"),
    ("still_employed", "Still-employed accuracy, real not timestamp", "rate"),
    ("linkedin_url_verified", "LinkedIn URLs that point at the right person", "rate"),
]

_HUBSPOT_OBJECT_TYPE_IDS = {"company": "0-2", "contact": "0-1"}

# Below this many comparable records the rate is still printed, but qualified:
# 1 of 3 and 33 of 100 are not the same kind of number and must not read alike.
_LOW_CONFIDENCE_MIN = 20


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


def _nudge(grade: str, unlocked: bool = False) -> str:
    if grade in ("D", "F"):
        return "A book at this grade is exactly what Jacob fixes with clients."
    if grade == "C":
        return "There is enough here to be worth a real cleanup."
    if unlocked:
        return "Want the rest of the accuracy picture? Here is the fast way."
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
        # The accuracy rows the user paid for belong in the summary they send.
        # Only the measurable ones: a not-measurable row has no rate to quote.
        for key, label, rate_key in _ACCURACY_REGISTRY:
            fact = facts.get(key)
            if not fact or not is_measurable(fact) or "grade" not in fact:
                continue
            lines.append(f"- {label}: {_pct(fact[rate_key])} ({fact['grade']}), "
                         f"verified on {fact['checked']} of {fact['sample_size']} sampled")
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


def _sample_disclosure(fact: dict) -> str:
    """The sample is not filtered against the free scan's own flags: filtering
    would bias it the other way. Say so instead of hiding it."""
    return ("The sample is drawn at random from all graded records, including "
            "records other checks on this card already flagged.")


def _provenance_html(fact: dict) -> str:
    """Accuracy rows cannot be re-run from the CSV, so they earn trust by being
    fully cited instead."""
    provider = (fact.get("provider") or "").strip()
    via = f" via {provider}" if provider else ""
    skipped = fact.get("skipped_blank", 0)
    counts = (f'{fact["checked"]} comparable, {fact["unverifiable"]} unverifiable '
              '(the provider had no data, which is not counted as an error), '
              f'{skipped} skipped because the stored value was blank.')

    if not is_measurable(fact):
        return (
            f'<p class="prov">A random sample of {fact["sample_size"]} records was '
            f'sent{via} on {fact["run_at"]}, and nothing came back that could be '
            f'compared, so this row is not graded. {counts} '
            f'{_sample_disclosure(fact)}</p>'
        )

    low = ""
    if fact["checked"] < _LOW_CONFIDENCE_MIN:
        low = (f' Only {fact["checked"]} records could actually be compared, so read '
               'this as a rough signal, not a precise measurement.')
    return (
        '<p class="prov">Verified on a random sample of '
        f'{fact["sample_size"]} records{via} on {fact["run_at"]}. '
        f'{counts} {_sample_disclosure(fact)}{low}</p>'
    )


def _not_measurable_html(label: str, explainer: str) -> str:
    """A row that measured nothing gets no letter grade, no percentage, and no
    bar. The provenance underneath says why. See unlock.is_measurable."""
    return (
        '<div class="sig nm">\n'
        '  <div class="sigtop"><span class="signame">'
        f'<span class="tag">NOT MEASURED</span>{label}</span>'
        '<span class="nmval">Not measurable</span></div>\n'
        f'  <p class="sigexp">{explainer}</p></div>'
    )


def _accuracy_html(cfg: RunConfig, objects: list[dict]) -> str:
    """One row per accuracy signal: a graded signal where a play has been run
    and measured something, a NOT MEASURED row where it measured nothing, and a
    LOCKED row everywhere else."""
    out = []
    for key, label, rate_key in _ACCURACY_REGISTRY:
        # First object carrying this key wins; any other is silently dropped.
        # Deliberate: each unlock key is semantically scoped to one object
        # type today, so at most one object should ever carry it.
        holder = next(
            (obj for obj in objects if key in obj["metrics"].get("facts", {})),
            None,
        )
        if holder is None:
            out.append(
                f'<div class="lrow"><span class="lname">{label}</span>'
                '<span class="lmark">LOCKED</span></div>'
            )
            continue
        fact = holder["metrics"]["facts"][key]
        # The comparison rule belongs to the play, not to the renderer: without
        # it on the card, "32% of your employee counts are wrong" is a number
        # nobody can check. A second play will have a different rule.
        rule = fact.get("comparison_rule", "")
        if not is_measurable(fact):
            out.append(_not_measurable_html(label, rule) + _provenance_html(fact))
            continue
        sig = _sig_html(cfg, holder["object_type"], key, label, rate_key, fact,
                        holder.get("list_files") or {}, explainer=rule)
        out.append(sig + _provenance_html(fact))
    return "\n".join(out)


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
              list_files: dict, explainer: str | None = None) -> str:
    grade = fact["grade"]
    rate = fact[rate_key]
    fcls = " f" if grade == "F" else ""
    width = min(rate * 100, 100)
    # Accuracy rows pass their own explainer (the play's comparison rule);
    # completeness rows look theirs up in _EXPLAINERS.
    if explainer is None:
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


def _has_accuracy_fact(objects: list[dict]) -> bool:
    """True once any accuracy play has been merged in, measurable or not.

    Both flavours mean company domains were sent to a third-party provider, so
    both invalidate the "nothing left this machine" claim.
    """
    keys = {key for key, _label, _rate_key in _ACCURACY_REGISTRY}
    return any(key in obj["metrics"].get("facts", {})
               for obj in objects for key in keys)


def _scope_line(objects: list[dict]) -> str:
    parts = []
    for obj in objects:
        n = obj["metrics"]["counts"]["records"]
        label = "companies" if obj["object_type"] == "company" else "contacts"
        parts.append(f"<b>{n:,} {label}</b>")
    tail = ("Click any line item to see the actual records and verify them in your CRM. "
            "Nothing left this machine.")
    if _has_accuracy_fact(objects):
        # The free scan's promise is true and stays untouched. Once a paid
        # accuracy play has run it is not true any more, so it must not be said.
        tail = ("Click any line item to see the actual records and verify them in "
                "your CRM. Everything stayed on this machine except the company "
                "domains in the verified sample, which were sent to the providers "
                "named in the accuracy rows below, through your own Deepline account.")
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

    # Completeness and accuracy side by side, as the design spec asks. The
    # accuracy column appears only when a measurable accuracy fact exists;
    # a not-measurable one produces no grade (see unlock.accuracy_grade).
    badges = (f'<div class="gradecol"><div class="gradebadge{badge_cls}">{grade}</div>'
              '<div class="gradelbl">Completeness</div></div>')
    acc = accuracy_grade(metrics)
    if acc:
        acc_cls = " ok" if acc in ("A", "B") else ""
        badges += (f'<div class="gradecol"><div class="gradebadge{acc_cls}">{acc}</div>'
                   '<div class="gradelbl">Accuracy</div></div>')

    return (
        f'<div class="seg">\n'
        f'  <div class="seghead"><div><h2>{title}</h2>'
        f'<div class="cnt">{n:,} records &middot; completeness grade &middot; {verdict}</div></div>'
        f'<div class="grades">{badges}</div></div>\n'
        f'  <div class="tiles">{tiles_html}</div>\n'
        f'  {sig_html}\n'
        f'</div>'
    )


# Every piece of standing copy that is true before any play has run and false
# after one has. Keyed by whether an accuracy fact is present.
_LOCKED_COPY = {
    "stage_02": ('<div class="stage locked"><div class="num">02</div>'
                 '<div class="nm">Accuracy</div><div class="st">Locked</div>'
                 '<div class="cap">Run the plays yourself</div></div>'),
    "punch": ("Both grades measure <b>completeness</b>. Neither can tell you if the "
              "data is <b>accurate</b>, nothing in a static file can. A book can be "
              "fully complete and mostly wrong, and complete-but-wrong is the "
              "dangerous kind, because it looks fine."),
    "accuracy_heading": "Accuracy: unlock stage 02",
    "accuracy_tag": "locked",
    "accuracy_box_class": "locked",
    "accuracy_note": ("Unlock with the cheap, tried-and-true Sculpted plays, shared "
                      "with you to run yourself, or have Jacob run them for you."),
    "close_body": ("You have your completeness grades. The accuracy grade is one step "
                   "away, fastest via a free session where Jacob runs it on your real "
                   "data with you."),
    "footer_note": "Read-only. Your rows never left this machine. Made by Sculpted.",
}

_UNLOCKED_COPY = {
    "stage_02": ('<div class="stage active"><div class="num">02</div>'
                 '<div class="nm">Accuracy</div><div class="st">Unlocked</div>'
                 # Not "verified on a sample": a play can run and come back with
                 # nothing comparable, and the chip must not claim otherwise.
                 '<div class="cap">Run on a sample of your book</div></div>'),
    "punch": ("The grades above measure <b>completeness</b>. No static file can grade "
              "<b>accuracy</b>, so the accuracy rows below were measured a different "
              "way: a random sample of your records checked against live sources. A "
              "book can be fully complete and mostly wrong, and complete-but-wrong is "
              "the dangerous kind, because it looks fine."),
    "accuracy_heading": "Accuracy: stage 02",
    "accuracy_tag": "partly unlocked",
    "accuracy_box_class": "unlockedbox",
    "accuracy_note": ("The rows still marked LOCKED unlock the same way: cheap, "
                      "tried-and-true Sculpted plays, shared with you to run "
                      "yourself, or have Jacob run them for you."),
    "close_body": ("You have your completeness grades, and an accuracy grade measured "
                   "on a sample. Getting that same rigour across your whole book is "
                   "the work itself, fastest via a free session where Jacob runs it on "
                   "your real data with you."),
    "footer_note": ("Read-only. The only thing that left this machine was the company "
                    "domains in the verified sample, sent to the providers named above "
                    "through your own Deepline account. Made by Sculpted."),
}


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

    unlocked = _has_accuracy_fact(objects)
    copy = _UNLOCKED_COPY if unlocked else _LOCKED_COPY

    return Template(template).substitute(
        product_name=cfg.product_name,
        overall_grade=grade,
        verdict=_verdict(grade),
        scope_line=_scope_line(objects),
        segments=segments,
        estimate_block=estimate_block,
        accuracy_rows=_accuracy_html(cfg, objects),
        custom_rows=_locked_list_html(custom_rows(cfg)),
        nudge=_nudge(grade, unlocked=unlocked),
        mailto=build_mailto(cfg, objects),
        booking_url=cfg.booking_url,
        **copy,
    )


def render_html(metrics: dict, cfg: RunConfig, template: str | None = None) -> str:
    """Single-object entry point (used by the existing CLI `render` command and
    older tests). Delegates to `render_report` with one object built from cfg."""
    object_type = getattr(cfg, "object_type", "company")
    return render_report([{"object_type": object_type, "metrics": metrics}], cfg, template)
