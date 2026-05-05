"""
Deepline runner — thin Python wrapper around `deepline enrich`.

Replaces the hand-run `bash run.sh` flow. Streams progress, captures the
final dataset_stats JSON, tracks credits used (delta between pre/post
balance), and surfaces the Session UI URL when Deepline emits one.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
from datetime import datetime

SESSION_URL_RE = re.compile(r"http://127\.0\.0\.1:4173\?session_id=[a-f0-9\-]+")


def _get_balance() -> float | None:
    """Call `deepline billing balance`, parse the numeric credit value."""
    try:
        out = subprocess.run(
            ["deepline", "billing", "balance"],
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode != 0:
            return None
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*credits?", out.stdout)
        return float(m.group(1)) if m else None
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None


def run_enrichment(
    playbook_path: pathlib.Path,
    csv_path: pathlib.Path,
    output_path: pathlib.Path,
    row_range: str | None = None,
    timeout_seconds: int = 1800,
) -> dict:
    """Shell out to `deepline enrich`, tail progress, return stats + credits.

    Args:
        playbook_path: compiled playbook.jsonc path
        csv_path: input CSV path
        output_path: where the enriched CSV should land
        row_range: e.g. "0:50" for a 50-row pilot; None for full run
        timeout_seconds: kill if it hangs

    Returns dict with:
        ok: bool
        enriched_csv: str (absolute path)
        dataset_stats: dict | None (the --json output's dataset_stats)
        credits_used: float | None (balance delta; negative = consumed)
        session_url: str | None (http://127.0.0.1:4173?session_id=... if detected)
        errors: list[str]
        exit_code: int
        started_at: str (ISO timestamp)
        finished_at: str (ISO timestamp)
    """
    playbook_path = pathlib.Path(playbook_path).resolve()
    csv_path = pathlib.Path(csv_path).resolve()
    output_path = pathlib.Path(output_path).resolve()

    if not playbook_path.exists():
        return {
            "ok": False, "enriched_csv": None, "dataset_stats": None,
            "credits_used": None, "session_url": None,
            "errors": [f"Playbook not found: {playbook_path}"],
            "exit_code": -1,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
    if not csv_path.exists():
        return {
            "ok": False, "enriched_csv": None, "dataset_stats": None,
            "credits_used": None, "session_url": None,
            "errors": [f"Input CSV not found: {csv_path}"],
            "exit_code": -1,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }

    if output_path.exists():
        output_path.unlink()

    cmd = [
        "deepline", "enrich",
        "--input", str(csv_path),
        "--output", str(output_path),
        "--config", str(playbook_path),
        "--json",
    ]
    if row_range:
        cmd += ["--rows", row_range]

    started_at = datetime.now().isoformat(timespec="seconds")
    balance_before = _get_balance()
    if balance_before is not None:
        print(f"  Balance: {balance_before:.2f} credits")

    session_url: str | None = None
    errors: list[str] = []
    last_json_line: str | None = None

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        return {
            "ok": False, "enriched_csv": None, "dataset_stats": None,
            "credits_used": None, "session_url": None,
            "errors": ["`deepline` CLI not found on PATH. Install it first: "
                       "curl -s 'https://code.deepline.com/api/v2/cli/install' | bash"],
            "exit_code": -1,
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }

    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue

            if session_url is None:
                m = SESSION_URL_RE.search(line)
                if m:
                    session_url = m.group(0)
                    print(f"  Session UI: {session_url}")

            if line.startswith("{") and '"status"' in line:
                last_json_line = line
            else:
                print(f"  {line}")

        proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        errors.append(f"Run exceeded {timeout_seconds}s timeout; process killed")
    except KeyboardInterrupt:
        proc.kill()
        errors.append("Run cancelled by operator (Ctrl+C)")

    exit_code = proc.returncode if proc.returncode is not None else -1

    dataset_stats = None
    if last_json_line:
        try:
            payload = json.loads(last_json_line)
            dataset_stats = payload.get("dataset_stats")
            if not payload.get("ok", True) and payload.get("failed_jobs"):
                errors.extend(
                    f"{j.get('column', '?')}: {j.get('last_error', '?')}"
                    for j in payload["failed_jobs"][:5]
                )
        except json.JSONDecodeError:
            errors.append("Could not parse final JSON line from deepline")

    balance_after = _get_balance()
    credits_used = None
    if balance_before is not None and balance_after is not None:
        credits_used = round(balance_before - balance_after, 4)
        print(f"  Credits used: {credits_used} (balance now {balance_after:.2f})")

    return {
        "ok": exit_code == 0 and not errors,
        "enriched_csv": str(output_path) if output_path.exists() else None,
        "dataset_stats": dataset_stats,
        "credits_used": credits_used,
        "session_url": session_url,
        "errors": errors,
        "exit_code": exit_code,
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
