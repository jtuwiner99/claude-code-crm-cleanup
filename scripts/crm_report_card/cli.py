"""Command-line entry: `scan`, `render`, and `report` subcommands."""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import date
from .config import load_config
from .scan import scan_from_files
from .render_terminal import render_terminal
from .render_html import render_html, render_report
from .export_lists import write_lists
from .loader import load_records


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


def _load_object(object_type, metrics_path, csv_path, cfg, lists_dir):
    with open(metrics_path, encoding="utf-8") as fh:
        metrics = json.load(fh)
    records, _mapping = load_records(csv_path, cfg.field_mapping, object_type=object_type)
    list_files = write_lists(object_type, metrics, records, lists_dir)
    return {"object_type": object_type, "metrics": metrics, "list_files": list_files}


def _cmd_report(args) -> int:
    cfg = load_config(args.config)

    objects = []
    if args.company_metrics and args.company_csv:
        objects.append(_load_object("company", args.company_metrics, args.company_csv, cfg, args.lists_dir))
    if args.contact_metrics and args.contact_csv:
        objects.append(_load_object("contact", args.contact_metrics, args.contact_csv, cfg, args.lists_dir))

    if not objects:
        print("error: report requires at least one of --company-metrics/--company-csv "
              "or --contact-metrics/--contact-csv", file=sys.stderr)
        return 2

    os.makedirs(args.lists_dir, exist_ok=True)

    html = render_report(objects, cfg)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html)

    for obj in objects:
        grade = obj["metrics"].get("overall_grade", "N/A")
        n_lists = len(obj["list_files"])
        print(f"{obj['object_type']}: grade {grade}, {n_lists} list file(s) written")

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

    p_report = sub.add_parser("report")
    p_report.add_argument("--config", required=True)
    p_report.add_argument("--out", required=True)
    p_report.add_argument("--lists-dir", required=True)
    p_report.add_argument("--company-metrics")
    p_report.add_argument("--company-csv")
    p_report.add_argument("--contact-metrics")
    p_report.add_argument("--contact-csv")
    p_report.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
