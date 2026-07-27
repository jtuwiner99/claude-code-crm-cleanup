"""Command-line entry: `scan`, `render`, and `report` subcommands."""
from __future__ import annotations
import argparse
import csv
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
from .plays import (load_registry, validate_registry, eligible_plays,
                    blocked_plays, eligible_records, draw_sample, estimate_cost)
from .scorers import SCORERS
from .unlock import merge_fragment


def _cmd_scan(args) -> int:
    cfg = load_config(args.config)
    # CRM_RC_SKIP_LIVENESS omits the dead-domain row entirely. It must never
    # stand in a fake fetcher: that would report 100% dead and grade an F on a
    # check that never ran.
    skip_liveness = os.environ.get("CRM_RC_SKIP_LIVENESS") == "1"
    metrics = scan_from_files(args.csv, cfg, today=date.today(),
                              skip_liveness=skip_liveness)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)
    print(render_terminal(metrics))
    return 0


def _read_json(path):
    """Read and parse a JSON file, raising a message that names the path.

    json.JSONDecodeError does not include the file path in its message, so a
    malformed metrics/fragment file would otherwise surface a location-free
    "Expecting value: ..." error. Wrapping every JSON read cli.py itself
    performs means the central error handler in main() always has a path to
    show the user.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _cmd_render(args) -> int:
    cfg = load_config(args.config)
    metrics = _read_json(args.metrics)
    html = render_html(metrics, cfg)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(render_terminal(metrics))
    return 0


def _load_object(object_type, metrics_path, csv_path, cfg, lists_dir):
    metrics = _read_json(metrics_path)
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


def _registry_or_fail(path):
    try:
        entries = load_registry(path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    errors = validate_registry(entries)
    if errors:
        for err in errors:
            print(f"registry error: {err}", file=sys.stderr)
        return None
    return entries


def _mapping_and_records(cfg, csv_path):
    records, mapping = load_records(csv_path, cfg.field_mapping,
                                    object_type=cfg.object_type)
    return records, mapping


def _cmd_plays(args) -> int:
    entries = _registry_or_fail(args.registry)
    if entries is None:
        return 2
    cfg = load_config(args.config)
    records, mapping = _mapping_and_records(cfg, args.csv)

    eligible = []
    for play in eligible_plays(entries, cfg.object_type, mapping):
        pool = eligible_records(records, play)
        n = min(play["default_sample"], len(pool))
        eligible.append({
            "id": play["id"], "label": play["label"], "unlocks": play["unlocks"],
            "eligible_records": len(pool), "sample": n,
            "estimate": estimate_cost(play, n),
            "comparison_rule": play["comparison_rule"],
            "providers": play["providers"],
        })

    blocked = [{"id": play["id"], "label": play["label"], "missing_roles": missing}
               for play, missing in blocked_plays(entries, cfg.object_type, mapping)]

    out = {"object_type": cfg.object_type, "eligible": eligible, "blocked": blocked}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)

    for play in eligible:
        est = play["estimate"]
        print(f"{play['id']}: {play['sample']} of {play['eligible_records']} records, "
              f"about ${est['usd']:.2f} ({est['credits']:.1f} credits)")
    for play in blocked:
        print(f"{play['id']}: cannot run, missing {', '.join(play['missing_roles'])}")
    return 0


def _find_play(entries, play_id):
    return next((e for e in entries if e["id"] == play_id), None)


def _cmd_sample(args) -> int:
    entries = _registry_or_fail(args.registry)
    if entries is None:
        return 2
    play = _find_play(entries, args.play)
    if play is None:
        print(f"error: no play with id '{args.play}'", file=sys.stderr)
        return 2

    cfg = load_config(args.config)
    records, _mapping = _mapping_and_records(cfg, args.csv)
    pool = eligible_records(records, play)
    size = args.size if args.size is not None else play["default_sample"]
    sample = draw_sample(pool, size, seed=args.seed)

    fields = ["record_id"] + list(play["requires_roles"])
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for rec in sample:
            writer.writerow({f: rec.get(f, "") for f in fields})

    print(f"wrote {len(sample)} of {len(pool)} eligible records to {args.out}")
    return 0


def _provider_citation(body: dict, play: dict) -> str:
    """Cite the providers that actually returned the values, with counts.

    These plays are waterfalls: naming `providers[0]` cites one provider for a
    sample most of which came from another. Counts come from the rows' own
    `source` column, so the citation cannot drift from the data. A row with no
    source is not attributed to anyone.
    """
    counts = body.get("source_counts") or {}
    if counts:
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        return ", ".join(f"{name} ({n})" for name, n in ranked)
    # Nothing came back to attribute. Name what the play was configured to try,
    # so the provenance line still says who the sample was sent to.
    return ", ".join(play.get("providers") or [])


def _cmd_fragment(args) -> int:
    entries = _registry_or_fail(args.registry)
    if entries is None:
        return 2
    play = _find_play(entries, args.play)
    if play is None:
        print(f"error: no play with id '{args.play}'", file=sys.stderr)
        return 2

    scorer = SCORERS.get(play["unlocks"])
    if scorer is None:
        print(f"error: no scorer registered for '{play['unlocks']}'", file=sys.stderr)
        return 2

    with open(args.rows, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    body = scorer(rows)
    fragment = dict(body)
    fragment.update({
        "unlock": play["unlocks"],
        "object_type": play["object_type"],
        "sample_size": args.sample_size if args.sample_size is not None else len(rows),
        "provider": args.provider or _provider_citation(body, play),
        "run_at": args.run_at or date.today().isoformat(),
        # What "wrong" means for this play. Without it on the card the rate is
        # unfalsifiable, and the rule belongs to the play, not the renderer.
        "comparison_rule": play.get("comparison_rule", ""),
    })
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(fragment, fh, indent=2)

    print(f"{fragment['unlock']}: {fragment['mismatched']} of {fragment['checked']} "
          f"checked are off by two or more bands, {fragment['unverifiable']} unverifiable")
    return 0


def _cmd_unlock(args) -> int:
    metrics = _read_json(args.metrics)
    fragment = _read_json(args.fragment)
    try:
        merged = merge_fragment(metrics, fragment)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2)
    fact = merged["facts"][fragment["unlock"]]
    if "grade" not in fact:
        # Nothing was comparable, so there is no rate and no grade to print.
        # Printing 0.0% (A) here is what made a run that verified nothing look
        # like a perfect score.
        print(f"unlocked {fragment['unlock']}: not measurable, 0 of "
              f"{fact['sample_size']} sampled records could be compared "
              f"({fact['unverifiable']} unverifiable, "
              f"{fact.get('skipped_blank', 0)} skipped because the stored value "
              f"was blank). No grade.")
    else:
        print(f"unlocked {fragment['unlock']}: {fact['rate'] * 100:.1f}% ({fact['grade']})")
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

    p_plays = sub.add_parser("plays")
    p_plays.add_argument("--registry", required=True)
    p_plays.add_argument("--config", required=True)
    p_plays.add_argument("--csv", required=True)
    p_plays.add_argument("--out", required=True)
    p_plays.set_defaults(func=_cmd_plays)

    p_sample = sub.add_parser("sample")
    p_sample.add_argument("--registry", required=True)
    p_sample.add_argument("--play", required=True)
    p_sample.add_argument("--config", required=True)
    p_sample.add_argument("--csv", required=True)
    p_sample.add_argument("--out", required=True)
    p_sample.add_argument("--size", type=int)
    p_sample.add_argument("--seed", type=int, default=1)
    p_sample.set_defaults(func=_cmd_sample)

    p_fragment = sub.add_parser("fragment")
    p_fragment.add_argument("--registry", required=True)
    p_fragment.add_argument("--play", required=True)
    p_fragment.add_argument("--rows", required=True)
    p_fragment.add_argument("--out", required=True)
    # Defaults to the number of rows the play actually returned. On a partial
    # run, leave it unset: the honest sample size is what came back, not what
    # was drawn.
    p_fragment.add_argument("--sample-size", type=int, dest="sample_size")
    p_fragment.add_argument("--provider")
    p_fragment.add_argument("--run-at", dest="run_at")
    p_fragment.set_defaults(func=_cmd_fragment)

    p_unlock = sub.add_parser("unlock")
    p_unlock.add_argument("--metrics", required=True)
    p_unlock.add_argument("--fragment", required=True)
    p_unlock.add_argument("--out", required=True)
    p_unlock.set_defaults(func=_cmd_unlock)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        # Backstop for every subcommand (including the pre-existing scan,
        # render, report): a bad path or a malformed file should read as
        # "your file has a typo", never as a stack trace. Handlers above this
        # one (unknown --play id, missing scorer, merge_fragment's own
        # ValueError) already print a more specific message and return
        # before an exception would reach here.
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
