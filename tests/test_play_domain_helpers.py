"""Exercise the pure string-matching helpers inside employee-count-accuracy's
play.ts directly, via Node, so the identity-check fixes are covered by a real
test rather than by a parallel Python reimplementation that could drift.

play.ts is TypeScript that imports the `deepline` package, so it cannot be
required as-is outside a Deepline runtime. Instead of duplicating the logic
in Python (and risking the two copies disagreeing), this test reads the
literal pure-helper block out of play.ts between its marker comments, appends
a small assertion script, and runs the result through Node's built-in
experimental type-stripping (no framework, no install, no network). If a
future edit changes registrableDomain or isLinkedInCompanyUrl, this test
re-reads the current source every run and fails against the real logic.

Skips (does not fail) when `node` is not on PATH, since Node is a Deepline
CLI prerequisite rather than a Python test dependency.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import tempfile

import pytest

PLAY_TS = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "crm-report-card", "plays",
    "employee-count-accuracy", "play.ts"))

START_MARKER = "// --- pure helpers"
END_MARKER = "// --- end pure helpers ---"

ASSERTIONS = r"""
const assert = require('node:assert/strict');

// Subdomain match: a LinkedIn website on a subdomain must reduce to the same
// registrable domain as the stored bare domain.
assert.strictEqual(registrableDomain('https://get.stripe.com/pricing'), 'stripe.com');
assert.strictEqual(registrableDomain('stripe.com'), 'stripe.com');
assert.strictEqual(
  registrableDomain('https://get.stripe.com/pricing'),
  registrableDomain('stripe.com'),
);

// Two-part public suffix: must not collapse to the suffix itself.
assert.strictEqual(registrableDomain('https://www.example.co.uk/about'), 'example.co.uk');
assert.notStrictEqual(registrableDomain('example.co.uk'), 'co.uk');
assert.strictEqual(registrableDomain('sub.example.co.uk'), 'example.co.uk');

// Genuine mismatch must still fail identity.
assert.notStrictEqual(registrableDomain('acme.com'), registrableDomain('stripe.com'));

// LinkedIn company URL validation, used to reject a hallucinated Exa answer.
assert.strictEqual(isLinkedInCompanyUrl('https://www.linkedin.com/company/stripe/'), true);
assert.strictEqual(isLinkedInCompanyUrl('https://linkedin.com/company/stripe'), true);
assert.strictEqual(isLinkedInCompanyUrl('https://example.com/not-linkedin'), false);
assert.strictEqual(isLinkedInCompanyUrl('https://www.linkedin.com/in/someperson'), false);
assert.strictEqual(isLinkedInCompanyUrl(''), false);
assert.strictEqual(isLinkedInCompanyUrl(null), false);

console.log('OK');
"""


def _extract_pure_helpers() -> str:
    source = open(PLAY_TS, encoding="utf-8").read()
    start = source.index(START_MARKER)
    end = source.index(END_MARKER)
    assert start < end, "pure-helpers markers are out of order in play.ts"
    return source[start:end]


def test_pure_helpers_are_still_bracketed_by_their_markers():
    """A missing marker would make this whole test silently pass on stale
    logic, so check the markers exist before trusting the extraction."""
    source = open(PLAY_TS, encoding="utf-8").read()
    assert source.count(START_MARKER) == 1
    assert source.count(END_MARKER) == 1
    assert source.index(START_MARKER) < source.index(END_MARKER)


def test_registrable_domain_and_linkedin_url_checks():
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH (a Deepline CLI prerequisite, not a Python test dependency)")

    helpers = _extract_pure_helpers()
    script = helpers + "\n" + ASSERTIONS

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ts", delete=False, encoding="utf-8"
    ) as f:
        f.write(script)
        path = f.name

    try:
        result = subprocess.run(
            ["node", "--no-warnings", "--experimental-strip-types", path],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            f"node helper-function check failed.\nstdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert "OK" in result.stdout
    finally:
        os.unlink(path)
