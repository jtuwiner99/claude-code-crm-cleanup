"""Command-line entry: `scan` and `render` subcommands."""
from __future__ import annotations
import argparse
import json
import os
from datetime import date
from .config import load_config
from .scan import scan_from_files
from .render_terminal import render_terminal
from .render_html import render_html


def _offline_fetcher(_domain):
    return None, True  # everything "dead" without network; used when liveness is skipped


def _cmd_scan(args) -> int:
    cfg = load_config(args.config)
    fetcher = _offline_fetcher if os.environ.get("CRM_RC_SKIP_LIVENESS") == "1" else None
    metrics = scan_from_files(args.csv, cfg, today=date.today(), fetcher=fetcher)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)
    print(render_terminal(metrics))
    return 0


def _cmd_render(args) -> int:
    cfg = load_config(args.config)
    with open(args.metrics, encoding="utf-8") as fh:
        metrics = json.load(fh)
    html = render_html(metrics, cfg)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(render_terminal(metrics))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="crm-report-card")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("--config", required=True)
    p_scan.add_argument("--csv", required=True)
    p_scan.add_argument("--out", required=True)
    p_scan.set_defaults(func=_cmd_scan)

    p_render = sub.add_parser("render")
    p_render.add_argument("--metrics", required=True)
    p_render.add_argument("--config", required=True)
    p_render.add_argument("--out", required=True)
    p_render.set_defaults(func=_cmd_render)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
