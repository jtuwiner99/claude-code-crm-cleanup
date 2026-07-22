"""Guard test: fails if any secret / internal path leaks into shippable files.

Scans only the shippable source tree (the parts of this repo that get
published / bundled), not SDD scratch, build output, or per-run artifacts.
"""
import os, re

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
FORBIDDEN = [
    r"/Users/JT", r"sculpted-gtm", r"sculpted-studio", r"client-repositories",
    r"RESEND_API_KEY", r"HARVEST_API_KEY", r"sk-[A-Za-z0-9]{20}", r"deepline secrets",
]
SCAN_EXT = {".py", ".md", ".html", ".json", ".jsonc", ".txt", ".toml", ".csv"}
# .superpowers = SDD scratch (task briefs/reports/ledger, full of internal paths).
# dist = built bundle output (Task 18), not source.
# docs = internal-facing spec/plan, stripped from the published bundle (see Task 18).
SKIP_DIRS = {".git", "__pycache__", "docs", ".superpowers", "dist"}
# This file itself necessarily contains the FORBIDDEN strings as pattern
# literals (not a leak) -- skip it so the guard doesn't flag itself.
SKIP_FILES = {os.path.basename(__file__)}


def _files():
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in names:
            if n in SKIP_FILES:
                continue
            if os.path.splitext(n)[1] in SCAN_EXT:
                yield os.path.join(base, n)


def test_no_internal_paths_or_secrets():
    hits = []
    for path in _files():
        text = open(path, encoding="utf-8", errors="ignore").read()
        for pat in FORBIDDEN:
            if re.search(pat, text):
                hits.append((os.path.relpath(path, ROOT), pat))
    assert not hits, f"sanitization leak: {hits}"
