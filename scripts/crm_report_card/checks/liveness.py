"""Domain liveness: live / bot-blocked / dead via HEAD ping.

The default fetcher uses only the standard library. It is injected so tests
never hit the network. Bot-blocked (401/403/429/503) is NEVER counted dead.
"""
from __future__ import annotations
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

_LIVE = {200, 301, 302, 307, 308}
_BLOCKED = {401, 403, 429, 503}
_UA = "Mozilla/5.0 (compatible; CRM-Report-Card/0.1)"


def classify(status, error: bool) -> str:
    if error:
        return "dead"
    if status in _LIVE:
        return "live"
    if status in _BLOCKED:
        return "bot_blocked"
    return "dead"


def default_fetcher(domain: str, timeout: float = 6.0):
    url = domain if domain.startswith("http") else f"https://{domain}"
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, False
    except urllib.error.HTTPError as exc:
        return exc.code, False
    except Exception:
        return None, True


def check_liveness(records, fetcher=default_fetcher, max_domains=None, workers: int = 16) -> dict:
    domains = []
    seen = set()
    for rec in records:
        dom = (rec.get("domain") or "").strip().lower()
        if dom and dom not in seen:
            seen.add(dom)
            domains.append(dom)
    if max_domains is not None:
        domains = domains[:max_domains]

    counts = {"live": 0, "bot_blocked": 0, "dead": 0}
    if domains:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = pool.map(lambda d: classify(*fetcher(d)), domains)
        for bucket in results:
            counts[bucket] += 1

    checked = len(domains)
    return {
        "checked": checked,
        "live": counts["live"],
        "bot_blocked": counts["bot_blocked"],
        "dead": counts["dead"],
        "live_rate": (counts["live"] / checked) if checked else 0.0,
        "dead_rate": (counts["dead"] / checked) if checked else 0.0,
    }
