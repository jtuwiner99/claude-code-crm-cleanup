"""Score the provider benchmark against recorded ground truth.

Answers three questions per provider, in this order, because they compound:

  1. Did it resolve the domain to the RIGHT LinkedIn company page?
  2. When it got the page right, did it get the COUNT right?
  3. When the count was wrong, how wrong?

Reporting count accuracy without (1) conflates two different products: a
provider that finds the wrong company and counts it perfectly, and one that
finds the right company and miscounts it. They fail differently and are fixed
differently.

Runs on partial ground truth, so it can be run mid-review to watch the shape
emerge. The number of scored rows is printed with every table, because a
percentage over 12 rows is not the same claim as one over 100.

Reference for the count is the LinkedIn People-tab number. Our own play reads
that same source, so its score measures reading fidelity and not independent
correctness. See METHODOLOGY.md. That caveat is printed with the results so it
cannot be separated from them.

Usage:  python3 benchmark/score.py [--truth PATH] [--json OUT]
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Measured from the Deepline billing ledger, not from rate cards. Our play's
# figure is the whole chain (icypeas + batched Apify scrape + AI verification)
# over 100 companies.
COST_PER_CALL_USD = {
    # Measured from the billing ledger of the single-resolver run on 2026-07-28:
    # 100 companies, 12.02 credits, $1.03 total. The earlier $0.0179 was the
    # two-round icypeas+exa chain this replaced.
    "ourplay": 0.0103,
    "peopledatalabs": 0.14,
    "crustdata": 0.04,
    "datagma": 0.027,
}

BANDS = [(1, 10), (11, 50), (51, 200), (201, 500),
         (501, 1000), (1001, 5000), (5001, 10000), (10001, 10 ** 9)]
BAND_LABELS = ["1-10", "11-50", "51-200", "201-500",
               "501-1000", "1001-5000", "5001-10000", "10001+"]


def band_index(value) -> int | None:
    try:
        v = int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    for i, (lo, hi) in enumerate(BANDS):
        if lo <= v <= hi:
            return i
    return len(BANDS) - 1


def answer_band(pr: dict) -> int | None:
    """A provider's answer as a band index, from its exact count if it gives one
    and otherwise from its band label.

    Crustdata answers in bands rather than exact numbers. Reading only the count
    column would score it zero by construction, which would be a defect in the
    benchmark rather than a finding about the provider.
    """
    i = band_index(pr.get("count"))
    if i is not None:
        return i
    label = (pr.get("band") or "").strip()
    if label in BAND_LABELS:
        return BAND_LABELS.index(label)
    return band_index(label)


# LinkedIn slugs that resolve to the same company page as another slug. The
# methodology already says a redirect is not a failure; that rule was being
# applied to domains but not to LinkedIn slugs, which penalised providers for
# returning a former name that still resolves.
#
# Evidence, 2026-07-28: each left-hand slug was scraped and returned no distinct
# company, while its right-hand counterpart returned one, which is what an alias
# looks like. This is indirect (absence of a separate entity, not an observed
# 301) so it is recorded here rather than asserted as certain.
#
# Two pairs that LOOK like aliases were tested and are NOT, so they stay wrong:
#   birdapp     (id 18359698, "Bird")         is a different company from birdhq
#   notionhq-kr (id 102055240, "Notion Korea") is a regional entity, not notionhq
SLUG_ALIASES = {
    "clay-run": "grow-with-clay",
    "readme-io": "readme",
    "braze-": "braze",
    "transferwise": "wiseaccount",
    "messagebird-com": "birdhq",
}


def slug(url: str) -> str:
    """Normalized LinkedIn company slug, so trailing slashes, www, and scheme
    differences do not read as different companies."""
    u = (url or "").strip().lower()
    if not u:
        return ""
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    u = u.split("?")[0].rstrip("/")
    m = re.search(r"linkedin\.com/company/([^/]+)", u)
    found = m.group(1) if m else u
    return SLUG_ALIASES.get(found, found)


def load_truth(path: str) -> dict:
    """Last record wins per domain, so a correction is just an appended row."""
    truth = {}
    if not os.path.exists(path):
        return truth
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            truth[rec["domain"]] = rec
    return truth


def load_providers() -> dict:
    """{domain: {provider: {count, linkedin_url}}}"""
    out: dict = {}
    raw = os.path.join(HERE, "raw_results.csv")
    if os.path.exists(raw):
        with open(raw, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                out.setdefault(r["domain"], {})[r["provider"]] = {
                    "count": r.get("count", ""),
                    "band": r.get("band", ""),
                    "linkedin_url": r.get("linkedin_url", ""),
                }
    ours = os.path.join(HERE, "ourplay_results.csv")
    if os.path.exists(ours):
        with open(ours, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                out.setdefault(r["domain"], {})["ourplay"] = {
                    "count": r.get("count", ""),
                    "band": r.get("band", ""),
                    "linkedin_url": r.get("linkedin_url", ""),
                }
    return out


def score(truth: dict, providers: dict) -> dict:
    names = sorted({p for d in providers.values() for p in d})
    report = {}

    for name in names:
        identity_total = identity_right = 0
        count_scored = count_right = count_lenient = 0
        rel_errors: list[float] = []
        gave_exact = 0
        cond_scored = cond_right = 0
        abs_errors: list[int] = []
        ratios: list[float] = []
        answered = 0
        by_tier: dict = {}

        for domain, rec in truth.items():
            pr = providers.get(domain, {}).get(name)
            if pr is None:
                continue
            tier = rec.get("tier", "unknown")
            t = by_tier.setdefault(tier, {"scored": 0, "right": 0})

            if answer_band(pr) is not None:
                answered += 1

            # 1. identity, only judgeable where the human settled the page
            true_slug = slug(rec.get("chosen_linkedin_url", ""))
            got_slug = slug(pr.get("linkedin_url", ""))
            id_ok = None
            if true_slug and got_slug:
                identity_total += 1
                id_ok = (true_slug == got_slug)
                identity_right += 1 if id_ok else 0

            # 2. count, against the LinkedIn People reference
            ref = rec.get("linkedin_people_count")
            ref_i = band_index(ref)
            got_i = answer_band(pr)
            if ref_i is None:
                continue
            if got_i is None:
                count_scored += 1          # answered nothing: scored, not right
                t["scored"] += 1
                continue

            # Strict: the answer must land in the SAME band as the reference.
            # Adjacent-band tolerance was dropped on 2026-07-28. Routing rules cut
            # at band boundaries, so 99 against 101 sends a record somewhere else
            # even though the companies are the same size. Forgiving that hides
            # the error that actually costs an operator something. The lenient
            # number is still computed and reported so the effect of tightening
            # the rule is visible rather than buried.
            ok = (ref_i == got_i)
            count_lenient += 1 if abs(ref_i - got_i) <= 1 else 0
            count_scored += 1
            count_right += 1 if ok else 0
            t["scored"] += 1
            t["right"] += 1 if ok else 0

            if id_ok:                       # 3. count given the right page
                cond_scored += 1
                cond_right += 1 if ok else 0

            # Relative error against the reference, for providers that return an
            # exact number at all. A provider that only sells bands cannot be
            # scored here, which is itself a product fact worth reporting.
            if (pr.get("count") or "").strip():
                gave_exact += 1
                try:
                    a = float(str(ref).replace(",", ""))
                    b = float(str(pr["count"]).replace(",", ""))
                    if a > 0:
                        rel_errors.append(abs(a - b) / a)
                except (TypeError, ValueError):
                    pass

            if not ok:
                try:
                    a = int(float(str(ref).replace(",", "")))
                    b = int(float(str(pr.get("count") or "").replace(",", "")))
                    abs_errors.append(abs(a - b))
                    if min(a, b) > 0:
                        ratios.append(max(a, b) / min(a, b))
                except (TypeError, ValueError):
                    pass

        cost = COST_PER_CALL_USD.get(name, 0.0)
        spend = cost * len(truth)
        report[name] = {
            "rows_compared": len([d for d in truth if name in providers.get(d, {})]),
            "answered": answered,
            "identity_scored": identity_total,
            "identity_right": identity_right,
            "count_scored": count_scored,
            "count_right": count_right,
            "count_right_lenient": count_lenient,
            "gave_exact_count": gave_exact,
            "median_rel_error_pct": (round(statistics.median(rel_errors) * 100, 1)
                                     if rel_errors else None),
            "count_right_given_identity_scored": cond_scored,
            "count_right_given_identity": cond_right,
            "median_abs_error_when_wrong": int(statistics.median(abs_errors)) if abs_errors else None,
            "median_ratio_when_wrong": round(statistics.median(ratios), 1) if ratios else None,
            "est_spend_usd": round(spend, 2),
            "cost_per_correct_usd": round(spend / count_right, 4) if count_right else None,
            "by_tier": by_tier,
        }
    return report


def _pct(n, d):
    return f"{n / d * 100:5.1f}%" if d else "    -"


def render(report: dict, truth_n: int) -> str:
    L = []
    L.append(f"Ground truth recorded for {truth_n} companies.")
    if truth_n < 100:
        L.append(f"PARTIAL: this is {truth_n} of 100. Percentages over a small n are noisy.")
    L.append("")
    L.append("Reference for the count is the LinkedIn People-tab number. Our play reads")
    L.append("that same source, so its score measures reading fidelity, not independent")
    L.append("correctness. A high score for ourplay is expected and is not a finding.")
    L.append("")
    head = (f"{'provider':16s} {'answered':>9s} {'right URL':>10s} {'band ok':>8s} "
            f"{'(lenient)':>10s} {'band|URL':>9s} {'med err':>8s} {'$/correct':>10s}")
    L.append(head)
    L.append("-" * len(head))
    for name, r in sorted(report.items()):
        L.append(
            f"{name:16s} "
            f"{r['answered']:>4d}/{r['rows_compared']:<4d} "
            f"{_pct(r['identity_right'], r['identity_scored']):>10s} "
            f"{_pct(r['count_right'], r['count_scored']):>8s} "
            f"{_pct(r['count_right_lenient'], r['count_scored']):>10s} "
            f"{_pct(r['count_right_given_identity'], r['count_right_given_identity_scored']):>9s} "
            f"{(format(r['median_rel_error_pct'], '.1f') + '%') if r['median_rel_error_pct'] is not None else 'band only':>8s} "
            f"{('$' + format(r['cost_per_correct_usd'], '.3f')) if r['cost_per_correct_usd'] else '-':>10s}"
        )
    L.append("")
    L.append("band ok   = the answer lands in the SAME size band as the reference.")
    L.append("(lenient) = the old rule, same or adjacent band, shown so the effect of")
    L.append("            tightening is visible rather than hidden.")
    L.append("band|URL  = band accuracy on only the rows where the provider found the right")
    L.append("            company. The gap to plain band accuracy is how much of its error")
    L.append("            was never a counting problem at all.")
    L.append("med err   = median relative error of the exact headcount. 'band only' means the")
    L.append("            provider never returns an exact number and cannot serve a routing")
    L.append("            rule that cuts at a threshold.")
    return "\n".join(L)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", default=os.path.join(HERE, "ground_truth.jsonl"))
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args(argv)

    truth = load_truth(args.truth)
    if not truth:
        print(f"no ground truth yet at {args.truth}.")
        print("Run the review console first; this can be re-run at any point to see partial results.")
        return 0
    providers = load_providers()
    report = score(truth, providers)
    print(render(report, len(truth)))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({"n_truth": len(truth), "providers": report}, fh, indent=2)
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
