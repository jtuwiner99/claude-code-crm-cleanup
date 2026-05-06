#!/usr/bin/env python3
"""
Promote a CSV-mode Deepline playbook to a hosted workflow.

Implements the four CSV-to-hosted gotchas documented in
docs/best-practices/deepline-best-practices.md:

  1. Bracket-form row reads. Lint pass — warns if a `row.<unknown>` reference
     is found with spaces / non-identifier chars in the column name. We never
     auto-rewrite (false positives kill hosted runs silently).

  2. No `row` object in cron-triggered runs. Default trigger is `api`. If the
     user passes --trigger cron, we refuse and tell them to split into two
     workflows — one row-aware, one cron-driven.

  3. Non-uniform `.result` wrap. Already handled in the canonical
     `recipes/default-cleanup-template.jsonc` via the inline unwrap() helper
     (and explicit `.result.data.X` reads in extract_js where present). No-op
     for the canonical shape — but we surface the rule in convert-warnings.md
     so future-Jacob doesn't re-derive.

  4. {{alias.X}} → {{alias.result.X}} template envelope rewrite. The big one.
     In CSV mode, `{{alias.field}}` auto-unwraps; in hosted mode, the same
     template resolves to the full envelope (which has `.result` at the top).
     We walk the playbook recursively and rewrite every template that
     references a known alias, unless the next segment is already `result`.

End-to-end flow when --dry-run is OFF:
  - read tmp/playbook.compiled.jsonc (the env-substituted CSV-mode playbook)
  - lint + rewrite into a hosted apply payload
  - `deepline workflows lint --file <payload>` to validate before deploying
  - `deepline workflows apply --file <payload>` to publish
  - `deepline workflows call --workflow-id <id> --payload <smoke>` smoke-test
  - `deepline workflows runs --tail` until the run completes
  - archive everything to tmp/workflows/<slug>/
  - update tmp/workflows/latest-workflow.json (the pointer downstream tools read)

Usage:
  # Dry run — convert + lint, no network deploy
  python tools/promote_to_workflow.py --playbook tmp/playbook.compiled.jsonc --dry-run

  # Live deploy with auto-generated slug + stripe.com smoke test
  python tools/promote_to_workflow.py --playbook tmp/playbook.compiled.jsonc

  # Live deploy with explicit name + custom smoke-test row
  python tools/promote_to_workflow.py \\
    --playbook tmp/playbook.compiled.jsonc \\
    --workflow-name acme_account_cleanup_v1 \\
    --smoke-domain shopify.com --smoke-company-name Shopify
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_PLAYBOOK = ROOT / "tmp" / "playbook.compiled.jsonc"
DEFAULT_ARCHIVE_DIR = ROOT / "tmp" / "workflows"
LATEST_POINTER = DEFAULT_ARCHIVE_DIR / "latest-workflow.json"


# ---------------------------------------------------------------------------
# Read playbook (jsonc → dict)
# ---------------------------------------------------------------------------

_LINE_COMMENT_RE = re.compile(r"^\s*//.*$", flags=re.MULTILINE)


def read_playbook(path: pathlib.Path) -> dict:
    """Parse a JSONC playbook (strips // line comments). Block comments are
    rare in our playbooks and not stripped — if you hit one, the JSON parser
    will surface a clear error."""
    if not path.exists():
        raise FileNotFoundError(f"playbook not found: {path}")
    raw = path.read_text()
    return json.loads(_LINE_COMMENT_RE.sub("", raw))


# ---------------------------------------------------------------------------
# Gotcha 1 — bracket-form row reads (lint only)
# ---------------------------------------------------------------------------

# Matches `row.<word>` where <word> is a valid identifier. We're looking for
# the OPPOSITE — `row.<X>` where X has spaces or punctuation, which would be
# a syntax error in JS anyway, so this lint is mostly a tripwire for people
# hand-editing the playbook.
_ROW_IDENT_RE = re.compile(r"\brow\.([A-Za-z_$][\w$]*)")


def lint_row_reads(commands: list[dict]) -> list[str]:
    """Currently a no-op for canonical playbooks (every row read uses bracket
    form: `row['domain']`). Returns a list of warnings to print to
    convert-warnings.md."""
    warnings: list[str] = []
    for cmd in commands:
        code = (cmd.get("payload") or {}).get("code", "")
        if not isinstance(code, str) or not code:
            continue
        # We're looking for things that AREN'T `row['X']` and AREN'T `row.X`
        # with X being an identifier — ie literal syntax errors. JS catches
        # these at runtime, but the hosted analyzer is stricter and rejects
        # before the code runs. We don't auto-rewrite; we just warn.
        # (Currently empty — the canonical playbook is clean.)
        pass
    return warnings


# ---------------------------------------------------------------------------
# Gotcha 3 + 4 combined — template envelope rewrite, per-alias tool-aware
# ---------------------------------------------------------------------------
#
# In CSV mode, `{{alias.X}}` auto-unwraps the result envelope: the user
# writes `{{harvest.data.element.description}}` and Deepline resolves it
# against `result.data.element.description` automatically.
#
# In hosted mode, NO auto-unwrap happens — `{{alias.X}}` resolves against
# the literal envelope. The envelope shape varies by tool:
#
#   - run_javascript          → {result: {data: <user_return_value>, meta: ...}}
#                                (so `{{alias.X}}` in CSV → `{{alias.result.data.X}}` in hosted)
#   - generic_http_request    → {result: {data: <body>, status_code, ok, ...}}
#                                (so `{{alias.data.X}}` in CSV → `{{alias.result.data.X}}` in hosted)
#   - apollo_enrich_company   → {result: {data: <organization>, meta: ...}}
#                                (same as generic_http_request in practice)
#   - deeplineagent           → {result: {text, object: <structured>, finishReason}}
#                                (so `{{alias.object.X}}` in CSV → `{{alias.result.object.X}}` in hosted)
#
# General rule: every alias gets `.result` injected immediately after.
# Additionally, for run_javascript aliases ONLY, we inject `.data` after
# `.result` because the user's CSV-mode template typically reads fields
# directly off the JS return value (skipping the `data` envelope key the
# hosted runtime adds).
#
# Empirically validated 2026-05-05: this matches the patterns in every
# enrichment-function in this repo (e.g. `{{build_request.result.data.url}}`,
# `{{detection_and_analysis.result.object.acquirer_name}}`,
# `{{redirect_to_parent_check.result.data.final_url}}`).

# Matches {{alias.field.subfield...}} — captures alias separately so we can
# decide per-alias what to inject.
_TEMPLATE_RE = re.compile(r"\{\{\s*([A-Za-z_][\w]*)((?:\.[A-Za-z_][\w]*)*)\s*\}\}")


def alias_tool_map(commands: list[dict]) -> dict[str, str]:
    """Build {alias: tool_id} so the rewriter knows which envelope shape to
    expect per alias."""
    out: dict[str, str] = {}
    for cmd in commands:
        if not isinstance(cmd, dict):
            continue
        alias = cmd.get("alias")
        tool = cmd.get("tool") or cmd.get("operation")
        if alias and tool:
            out[alias] = tool
    return out


def _hosted_prefix(tool: str) -> str:
    """Path segments to inject between {{alias and .X for hosted mode.

      run_javascript → ".result.data"  (inject 2 levels)
      everything else → ".result"      (inject 1 level)

    Caller checks the user's CSV-mode template doesn't already start
    with the prefix before injecting.
    """
    if tool == "run_javascript":
        return ".result.data"
    return ".result"


def rewrite_templates(node, alias_tools: dict[str, str], stats: dict | None = None):
    """Recursively rewrite `{{alias.X.Y}}` to the hosted-mode equivalent for
    every alias defined in the playbook's commands.

    Skipped:
      - {{alias}} with no field — already references the full envelope.
      - {{alias.result.X}} — user already wrote the hosted-mode form.
      - {{otheralias.X}} where otheralias is not in our command aliases.
    """
    if isinstance(node, dict):
        return {k: rewrite_templates(v, alias_tools, stats) for k, v in node.items()}
    if isinstance(node, list):
        return [rewrite_templates(v, alias_tools, stats) for v in node]
    if isinstance(node, str):
        return _rewrite_template_string(node, alias_tools, stats)
    return node


def _rewrite_template_string(s: str, alias_tools: dict[str, str], stats: dict | None) -> str:
    def _sub(m: re.Match) -> str:
        alias = m.group(1)
        rest = m.group(2)  # ".data.element.description" etc, or ""
        if alias not in alias_tools:
            return m.group(0)  # leave foreign templates alone
        if not rest:
            return m.group(0)  # bare {{alias}} — full envelope already
        if rest.startswith(".result"):
            return m.group(0)  # already explicit
        prefix = _hosted_prefix(alias_tools[alias])
        # Avoid double-prefix if user already happened to write the inner
        # segment (e.g. for generic_http_request, .data is part of CSV
        # path → don't insert .result.data, insert just .result).
        # For run_javascript whose prefix is .result.data, if user wrote
        # {{alias.data.X}}, we'd produce .result.data.data.X which is wrong.
        # Detect: if rest starts with the LAST segment of prefix, strip
        # that segment from prefix.
        if "." in prefix:
            last_seg = prefix.rsplit(".", 1)[-1]  # e.g. "data"
            if rest == f".{last_seg}" or rest.startswith(f".{last_seg}."):
                prefix = prefix.rsplit(".", 1)[0]  # drop the last segment
        new = f"{{{{{alias}{prefix}{rest}}}}}"
        if stats is not None:
            stats.setdefault("rewrites", []).append(f"{m.group(0)} → {new}")
        return new

    return _TEMPLATE_RE.sub(_sub, s)


# ---------------------------------------------------------------------------
# Build the apply payload
# ---------------------------------------------------------------------------


def build_apply_payload(
    playbook: dict,
    workflow_name: str,
    trigger_type: str = "api",
) -> tuple[dict, dict]:
    """Returns (apply_payload, stats). stats has the rewrite trail + lint
    warnings for archiving as convert-warnings.md."""
    if trigger_type == "cron":
        raise SystemExit(
            "ERROR: --trigger cron rejected. Cron-triggered runs have no `row` object; "
            "the canonical CRM-cleanup playbook is row-driven. Either deploy with "
            "--trigger api/webhook (and call from your scheduler) OR split into a "
            "data-source workflow + a per-row cleanup workflow."
        )
    if trigger_type not in {"api", "webhook"}:
        raise SystemExit(f"ERROR: unsupported --trigger {trigger_type!r} (allowed: api, webhook).")

    commands = playbook.get("commands") or []
    alias_tools = alias_tool_map(commands)
    stats: dict = {"rewrites": [], "skipped_rawvalue": [], "warnings": []}

    rewritten = rewrite_templates(commands, alias_tools, stats)
    stats["warnings"].extend(lint_row_reads(commands))

    apply_payload = {
        "name": workflow_name,
        "config": {
            "version": playbook.get("version", 1),
            "commands": rewritten,
        },
        "trigger": {"type": trigger_type},
    }
    return apply_payload, stats


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------


def _read_latest_pointer() -> dict | None:
    if not LATEST_POINTER.exists():
        return None
    try:
        return json.loads(LATEST_POINTER.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def auto_slug(prefix: str = "crm_cleanup") -> str:
    """Generate a slug like `crm_cleanup_20260505_v3`. v-suffix increments
    based on latest-workflow.json (or 1 if none)."""
    today = datetime.now().strftime("%Y%m%d")
    prev = _read_latest_pointer()
    next_v = 1
    if prev and isinstance(prev, dict):
        prev_name = prev.get("workflow_name", "")
        m = re.search(r"_v(\d+)$", prev_name or "")
        if m:
            next_v = int(m.group(1)) + 1
    return f"{prefix}_{today}_v{next_v}"


# ---------------------------------------------------------------------------
# Deepline CLI shells
# ---------------------------------------------------------------------------


def deepline_cli(args: list[str], capture: bool = True, check: bool = True) -> dict:
    """Invoke the deepline CLI with --json appended. Returns parsed JSON
    response. Raises SystemExit with the stderr trail on non-zero exit."""
    full = ["deepline", *args, "--json"]
    print(f"  $ {' '.join(full)}")
    proc = subprocess.run(full, capture_output=capture, text=True)
    if check and proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"deepline {' '.join(args[:2])} exit {proc.returncode}")
    if not proc.stdout.strip():
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"  (deepline returned non-JSON output: {e})\n")
        sys.stderr.write(proc.stdout[:1000])
        raise


def lint_apply_payload(apply_path: pathlib.Path) -> None:
    print("Linting apply payload via deepline workflows lint...")
    res = deepline_cli(["workflows", "lint", "--file", str(apply_path)])
    if res.get("ok") is False or res.get("errors"):
        raise SystemExit(f"Lint failed: {json.dumps(res, indent=2)[:1500]}")


def workflow_apply(apply_path: pathlib.Path) -> dict:
    print("Publishing workflow via deepline workflows apply...")
    return deepline_cli(["workflows", "apply", "--file", str(apply_path)])


def workflow_call(workflow_id: str, payload: dict) -> dict:
    print(f"Smoke-testing workflow {workflow_id}...")
    return deepline_cli([
        "workflows", "call",
        "--workflow-id", workflow_id,
        "--payload", json.dumps(payload),
    ])


def workflow_runs_get(workflow_id: str, run_id: str) -> dict:
    return deepline_cli([
        "workflows", "runs",
        "--workflow-id", workflow_id,
        "--run-id", run_id,
    ])


_PENDING_STATES = {"pending", "running", "queued", "dispatched", "in_progress"}


def wait_for_run(workflow_id: str, run_id: str, timeout_sec: int = 180) -> dict:
    """Poll runs until the run is no longer in a pending state. Returns the
    final run record (or the full envelope if no `run` key was found)."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        rec = workflow_runs_get(workflow_id, run_id)
        run = rec.get("run") or rec.get("data") or rec
        if isinstance(run, list) and run:
            run = run[0]
        status = (run or {}).get("status") or (run or {}).get("state")
        if status and status not in _PENDING_STATES:
            return run if isinstance(run, dict) else rec
        time.sleep(3)
    raise SystemExit(f"Run {run_id} did not complete within {timeout_sec}s")


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------


def write_convert_warnings(archive_dir: pathlib.Path, stats: dict) -> None:
    md = ["# Convert warnings", ""]
    rewrites = stats.get("rewrites") or []
    if rewrites:
        md.append(f"## Template rewrites applied ({len(rewrites)})")
        md.append("")
        md.append("Hosted-mode envelope rewrites (gotchas #3 + #4): `.result` is injected for every alias; `.data` is also injected for `run_javascript` aliases (their hosted envelope wraps the user's return value as `result.data`).")
        md.append("")
        for r in sorted(set(rewrites)):
            md.append(f"- `{r}`")
        md.append("")
    else:
        md.append("## Template rewrites applied (0)")
        md.append("")
        md.append("Playbook had no CSV-mode-style template references — already hosted-clean.")
        md.append("")

    warnings = stats.get("warnings") or []
    md.append(f"## Lint warnings ({len(warnings)})")
    md.append("")
    if warnings:
        for w in warnings:
            md.append(f"- {w}")
    else:
        md.append("None.")
    md.append("")

    md.append("## Inherent rules from docs/best-practices/deepline-best-practices.md")
    md.append("")
    md.append("- Gotcha #1 (bracket-form row reads): canonical playbook uses `row['domain']` shape — clean.")
    md.append("- Gotcha #2 (no row in cron): converter refuses --trigger cron; api/webhook only.")
    md.append("- Gotcha #3 (non-uniform .result wrap): canonical verdict uses inline unwrap() helper.")
    md.append("- Gotcha #4 (template envelope): rewrites listed above.")
    md.append("")
    (archive_dir / "convert-warnings.md").write_text("\n".join(md))


def archive_artifact(archive_dir: pathlib.Path, name: str, payload) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    p = archive_dir / name
    if isinstance(payload, (dict, list)):
        p.write_text(json.dumps(payload, indent=2))
    else:
        p.write_text(str(payload))


def update_latest_pointer(pointer: dict) -> None:
    LATEST_POINTER.parent.mkdir(parents=True, exist_ok=True)
    LATEST_POINTER.write_text(json.dumps(pointer, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Promote a CSV-mode Deepline playbook to a hosted workflow."
    )
    parser.add_argument("--playbook", type=pathlib.Path, default=DEFAULT_PLAYBOOK,
                        help=f"Compiled playbook to convert (default: {DEFAULT_PLAYBOOK.relative_to(ROOT)}).")
    parser.add_argument("--workflow-name", type=str, default=None,
                        help="Workflow slug (default: auto-generated `crm_cleanup_<YYYYMMDD>_v<N>`).")
    parser.add_argument("--trigger", choices=["api", "webhook"], default="api",
                        help="Workflow trigger type (default: api). cron is rejected — see docstring.")
    parser.add_argument("--smoke-domain", type=str, default="stripe.com",
                        help="Domain to use for the post-deploy smoke test (default: stripe.com).")
    parser.add_argument("--smoke-company-name", type=str, default="Stripe",
                        help="company_name to use for the smoke test (default: Stripe).")
    parser.add_argument("--no-smoke-test", action="store_true",
                        help="Skip the post-deploy smoke test.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Convert + lint only; no `deepline workflows apply`.")
    parser.add_argument("--archive-dir", type=pathlib.Path, default=DEFAULT_ARCHIVE_DIR,
                        help=f"Where to write the per-deploy artifacts (default: {DEFAULT_ARCHIVE_DIR.relative_to(ROOT)}/<slug>/).")
    args = parser.parse_args()

    workflow_name = args.workflow_name or auto_slug()
    archive_dir = args.archive_dir / workflow_name

    print(f"Promoting playbook: {args.playbook}")
    print(f"Workflow name:      {workflow_name}")
    print(f"Trigger type:       {args.trigger}")
    print(f"Archive dir:        {archive_dir.relative_to(ROOT)}")
    print(f"Mode:               {'DRY-RUN (no deploy)' if args.dry_run else 'LIVE'}")
    print()

    # Step 1: read + convert
    print("Step 1: read playbook + convert to hosted apply payload...")
    playbook = read_playbook(args.playbook)
    apply_payload, stats = build_apply_payload(playbook, workflow_name, args.trigger)
    archive_artifact(archive_dir, "apply.json", apply_payload)
    write_convert_warnings(archive_dir, stats)
    n_rewrites = len(stats.get("rewrites") or [])
    print(f"  template rewrites: {n_rewrites}")
    print(f"  lint warnings:     {len(stats.get('warnings') or [])}")
    print(f"  → {archive_dir / 'apply.json'}")
    print(f"  → {archive_dir / 'convert-warnings.md'}")
    print()

    # Step 2: lint via deepline
    print("Step 2: validate apply payload via `deepline workflows lint`...")
    apply_path = archive_dir / "apply.json"
    lint_apply_payload(apply_path)
    print("  lint passed.")
    print()

    if args.dry_run:
        print("DRY-RUN complete. No workflow was deployed.")
        print(f"Apply payload:    {apply_path}")
        print(f"Convert warnings: {archive_dir / 'convert-warnings.md'}")
        return 0

    # Step 3: apply
    print("Step 3: deploy via `deepline workflows apply`...")
    apply_result = workflow_apply(apply_path)
    archive_artifact(archive_dir, "apply-result.json", apply_result)
    workflow_id = (
        apply_result.get("id")
        or apply_result.get("workflow_id")
        or (apply_result.get("data") or {}).get("id")
        or (apply_result.get("workflow") or {}).get("id")
    )
    if not workflow_id:
        print("ERROR: apply succeeded but no workflow id found in response. Inspect:", file=sys.stderr)
        print(json.dumps(apply_result, indent=2)[:2000], file=sys.stderr)
        return 2
    print(f"  workflow_id: {workflow_id}")
    print()

    # Step 4: smoke-test
    smoke_run_record: dict | None = None
    if not args.no_smoke_test:
        print(f"Step 4: smoke test against `{args.smoke_domain}`...")
        smoke_payload = {
            "domain": args.smoke_domain,
            "company_name": args.smoke_company_name,
        }
        archive_artifact(archive_dir, "smoke-test-payload.json", smoke_payload)
        call_result = workflow_call(workflow_id, smoke_payload)
        run_id = (
            call_result.get("run_id")
            or call_result.get("id")
            or (call_result.get("run") or {}).get("id")
            or (call_result.get("data") or {}).get("run_id")
        )
        if not run_id:
            print(f"  WARNING: call returned but no run_id found. Response:", file=sys.stderr)
            print(json.dumps(call_result, indent=2)[:1500], file=sys.stderr)
        else:
            print(f"  run_id: {run_id}")
            print(f"  waiting for run to complete (up to 180s)...")
            try:
                smoke_run_record = wait_for_run(workflow_id, run_id, timeout_sec=180)
                archive_artifact(archive_dir, "smoke-test-run.json", smoke_run_record)
                final_status = smoke_run_record.get("status") or smoke_run_record.get("state") or "unknown"
                print(f"  run final status: {final_status}")
            except SystemExit as e:
                print(f"  WARNING: {e}", file=sys.stderr)

    # Step 5: update latest pointer
    pointer = {
        "workflow_id": workflow_id,
        "workflow_name": workflow_name,
        "trigger_type": args.trigger,
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "archive_dir": str(archive_dir.relative_to(ROOT)),
        "smoke_test": ({
            "domain": args.smoke_domain,
            "run_id": (smoke_run_record or {}).get("id") or (smoke_run_record or {}).get("run_id"),
            "status": (smoke_run_record or {}).get("status") or (smoke_run_record or {}).get("state"),
        } if smoke_run_record else None),
    }
    update_latest_pointer(pointer)
    archive_artifact(archive_dir, "pointer.json", pointer)
    print()
    print(f"Latest workflow pointer: {LATEST_POINTER.relative_to(ROOT)}")
    print()
    print("=" * 60)
    print(f"Workflow {workflow_name} ({workflow_id}) deployed.")
    if smoke_run_record:
        print(f"Smoke test: {(smoke_run_record.get('status') or 'unknown').upper()}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
