"""Render the live terminal reveal from a metrics dict."""
from __future__ import annotations

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


def _pct(rate: float) -> str:
    return f"{rate * 100:.1f}%"


def render_terminal(metrics: dict) -> str:
    n = metrics["counts"]["records"]
    facts = metrics["facts"]
    lines = [
        f"Scanning {n:,} records...",
        "",
    ]
    for key, label, rate_key in _FACT_REGISTRY:
        if key not in facts:
            continue
        pad = "." * max(1, 24 - len(label))
        extra = ""
        if key == "liveness":
            extra = f"(bot-blocked: {facts['liveness']['bot_blocked']})  "
        lines.append(
            f"  [FACT] {label} {pad} {_pct(facts[key][rate_key])}  {extra}({facts[key]['grade']})"
        )
    ai = metrics.get("ai_baseline")
    if ai:
        lines.append(
            f"  [ESTIMATE: NOT VERIFIED] Qualified ~ {ai['qualified_estimate'] * 100:.0f}%  "
            f"(single-pass guess, accuracy unmeasured)"
        )
    else:
        lines.append("  [ESTIMATE] Qualified %: not run")
    lines += ["", f"OVERALL GRADE: {metrics['overall_grade']}"]
    return "\n".join(lines)
