"""Render the live terminal reveal from a metrics dict."""
from __future__ import annotations


def _pct(rate: float) -> str:
    return f"{rate * 100:.1f}%"


def render_terminal(metrics: dict) -> str:
    n = metrics["counts"]["records"]
    facts = metrics["facts"]
    lines = [
        f"Scanning {n:,} records...",
        "",
        f"  [FACT] Duplicates ........ {_pct(facts['duplicates']['duplicate_rate'])}  ({facts['duplicates']['grade']})",
        f"  [FACT] Missing critical .. {_pct(facts['fill_rate']['overall_missing_rate'])}  ({facts['fill_rate']['grade']})",
        f"  [FACT] Contradictions .... {_pct(facts['contradictions']['rate'])}  ({facts['contradictions']['grade']})",
        f"  [FACT] Junk .............. {_pct(facts['junk']['junk_rate'])}  ({facts['junk']['grade']})",
        f"  [FACT] Stale ............. {_pct(facts['staleness']['stale_rate'])}  ({facts['staleness']['grade']})",
        f"  [FACT] Dead domains ...... {_pct(facts['liveness']['dead_rate'])}  "
        f"(bot-blocked: {facts['liveness']['bot_blocked']})  ({facts['liveness']['grade']})",
    ]
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
