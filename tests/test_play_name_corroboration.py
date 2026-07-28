"""Exercise the name-corroboration guard inside employee-count-accuracy's
play.ts directly, via Node -- same pattern as test_play_domain_helpers.py.

The website-match fast path answers "does this LinkedIn page claim this
website," which is weaker than "is this the right company": a parent and its
regional pages, or an old legal entity, can legitimately claim the same
website. nameCorroboratesDomain() is the guard added on top of the website
match; this test exercises it directly against the three measured benchmark
failures (must escalate) and a set of ordinary correct matches (must not
escalate), reading the live pure-helper block out of play.ts every run so a
future edit that breaks the guard fails this test rather than a parallel
Python reimplementation that could drift.

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

function company(name) {
  return { name };
}

// --- Must escalate: the three measured benchmark failures. Each is a
// website match against the WRONG entity, so nameCorroboratesDomain must
// return false to send the row to ai_inference instead of auto-accepting.

// intercom.com -> intercom-latinamerica: a regional page. Brand token
// present, but an unexplained region qualifier rides along.
assert.strictEqual(
  nameCorroboratesDomain(
    'intercom.com',
    company('Intercom LatinAmerica'),
    'https://www.linkedin.com/company/intercom-latinamerica/',
  ),
  false,
  'intercom.com / intercom-latinamerica must escalate',
);

// chorus.ai -> affectlayer-inc: Chorus.ai's former legal entity. Zero
// shared token with the brand at all.
assert.strictEqual(
  nameCorroboratesDomain(
    'chorus.ai',
    company('AffectLayer, Inc.'),
    'https://www.linkedin.com/company/affectlayer-inc./',
  ),
  false,
  'chorus.ai / affectlayer-inc must escalate',
);

// clay.com -> grow-with-clay: ground truth is clay-run. Brand token present
// but riding along with unexplained extra tokens ("grow", "with").
assert.strictEqual(
  nameCorroboratesDomain(
    'clay.com',
    company('Grow with Clay'),
    'https://www.linkedin.com/company/grow-with-clay/',
  ),
  false,
  'clay.com / grow-with-clay must escalate',
);

// --- Must NOT escalate: ordinary correct matches.

assert.strictEqual(
  nameCorroboratesDomain('stripe.com', company('Stripe'), 'https://www.linkedin.com/company/stripe/'),
  true,
  'stripe.com / stripe must not escalate',
);

assert.strictEqual(
  nameCorroboratesDomain('shopify.com', company('Shopify'), 'https://www.linkedin.com/company/shopify/'),
  true,
  'shopify.com / shopify must not escalate',
);

// Hyphenated multiword brand: slug carries both brand words, nothing else.
assert.strictEqual(
  nameCorroboratesDomain(
    'big-commerce.com',
    company('BigCommerce'),
    'https://www.linkedin.com/company/big-commerce/',
  ),
  true,
  'big-commerce.com / big-commerce must not escalate',
);

// A benign legal-entity suffix on an otherwise-correct page must not trip
// the guard by itself (this is the documented false-positive boundary, not
// a case that should escalate).
assert.strictEqual(
  nameCorroboratesDomain('acme.com', company('Acme Inc'), 'https://www.linkedin.com/company/acme-inc/'),
  true,
  'acme.com / acme-inc (benign legal suffix) must not escalate',
);

console.log('OK');
"""


def _extract_pure_helpers() -> str:
    source = open(PLAY_TS, encoding="utf-8").read()
    start = source.index(START_MARKER)
    end = source.index(END_MARKER)
    assert start < end, "pure-helpers markers are out of order in play.ts"
    return source[start:end]


def test_name_corroboration_guard_catches_benchmark_failures_and_spares_ordinary_matches():
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
            f"node name-corroboration check failed.\nstdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert "OK" in result.stdout
    finally:
        os.unlink(path)
