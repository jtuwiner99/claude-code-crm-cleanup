"""Guard test: fails if any secret / internal path leaks into shippable files.

Scans only the shippable source tree (the parts of this repo that get
published / bundled), not SDD scratch, build output, or per-run artifacts.

The patterns match the SHAPE of an internal path rather than naming individual
repositories. Listing the real repo names here would publish, in a public repo,
the exact strings this guard exists to keep out of it.
"""
import os, re

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

# Each entry is (name, regex). The name is what a failure reports, so a hit
# reads as a category rather than as the leaked value itself.
FORBIDDEN = [
    # Any absolute home-directory path: /Users/<someone>/... or /home/<someone>/...
    ("absolute home-directory path", r"/(?:Users|home)/[A-Za-z0-9._-]+"),
    # A checkout inside a local repositories/ root, e.g. repositories/<internal-repo>.
    ("internal repository checkout path", r"\brepositories/[A-Za-z0-9._-]+"),
    # Credentials and credential-shaped strings.
    ("api key env var", r"[A-Z0-9_]*(?:RESEND|HARVEST|OPENAI|ANTHROPIC)[A-Z0-9_]*_API_KEY"),
    ("api key literal", r"sk-[A-Za-z0-9]{20}"),
    ("secret-store command", r"deepline secrets"),
]

SCAN_EXT = {".py", ".md", ".html", ".json", ".jsonc", ".txt", ".toml", ".csv",
            ".yaml", ".yml", ".ts", ".sh"}
# .superpowers = SDD scratch (task briefs/reports/ledger, full of internal paths).
# dist = built bundle output (Task 18), not source.
# docs = internal-facing spec/plan, stripped from the published bundle (see Task 18).
SKIP_DIRS = {".git", "__pycache__", "docs", ".superpowers", "dist"}
# This file itself necessarily contains the FORBIDDEN patterns as literals
# (not a leak) -- skip it so the guard doesn't flag itself.
SKIP_FILES = {os.path.basename(__file__)}


def violations(text: str) -> list[str]:
    """The names of every forbidden pattern this text matches."""
    return [name for name, pat in FORBIDDEN if re.search(pat, text)]


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
        for name in violations(text):
            hits.append((os.path.relpath(path, ROOT), name))
    assert not hits, f"sanitization leak: {hits}"


def test_the_guard_catches_a_planted_violation():
    """A guard nobody has seen fail is a guard nobody knows works. Each of
    these is a realistic leak that has to be caught after the patterns were
    genericized away from naming specific repositories."""
    planted = [
        "see /Users/someone/repositories/internal-tools/notes.md for context",
        "cd /home/someone/work/internal-thing",
        "the recipe lives in repositories/some-internal-repo/enrichment.yaml",
        "RESEND_API_KEY=abc123",
        "export ANTHROPIC_API_KEY=xyz",
        "sk-abcdefghijklmnopqrstuvwxyz",
        "run `deepline secrets set FOO` first",
    ]
    for text in planted:
        assert violations(text), f"guard missed a planted violation: {text!r}"


def test_the_guard_does_not_flag_legitimate_shipped_strings():
    """It must stay usable: these all appear in files we do ship."""
    allowed = [
        "cp -R dist/crm-report-card ~/.claude/skills/crm-report-card",
        "/plugin install crm-report-card@sculpted-plugins",
        "jacob@sculpted.agency",
        "https://meetings.hubspot.com/tuwiner/sculpted-intro-meeting",
        'PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m crm_report_card.cli',
    ]
    for text in allowed:
        assert violations(text) == [], f"guard false-positived on {text!r}"


def test_the_guard_scans_the_file_types_this_repo_ships():
    """play.ts was the first shippable .ts in a repo the house rules designate
    a security boundary, and the scanner did not look at .ts files at all."""
    for ext in (".py", ".md", ".html", ".json", ".ts", ".sh", ".yaml"):
        assert ext in SCAN_EXT
    scanned = {os.path.relpath(p, ROOT) for p in _files()}
    assert "crm-report-card/plays/employee-count-accuracy/play.ts" in scanned
    assert "scripts/build_bundle.sh" in scanned
