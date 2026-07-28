"""Exercise buildOutputRows -- the function that assembles employee-count-
accuracy's final per-company rows from round 1's verified rows plus round
2's rescue map -- directly via Node, same pattern as the other play tests.

buildOutputRows answers "what do the merged rows look like." It is
deliberately silent on "how do they get returned" (materialized array vs.
durable dataset handle): that second question is a separate concern, guarded
by test_play_output_is_a_dataset_handle.py, because a past regression got
THIS part right (the merge) while still shipping truncated output by
wrapping the correct merge in `.map(...)` and returning a plain array
instead of a `ctx.dataset(...)` handle. A shape-only test on buildOutputRows
would have kept passing straight through that regression, which is exactly
why it needs its own dedicated test.

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

function verifiedRow(record_id, domain, company_size, verification) {
  return { record_id, domain, company_size, verification };
}

function round1Pass() {
  return {
    passed: true,
    verified_employee_count: 50000,
    source: 'harvestapi via apify',
    verified_range: '10001-50000',
    verified_linkedin_url: 'https://linkedin.com/company/zendesk',
    identity_method: 'website-match:icypeas',
  };
}

function round1Fail(identity_method) {
  return {
    passed: false,
    verified_employee_count: '',
    source: '',
    verified_range: '',
    verified_linkedin_url: '',
    identity_method: identity_method || 'ai-rejected',
  };
}

function round2Rescue() {
  return {
    passed: true,
    verified_employee_count: 7603,
    source: 'harvestapi via apify',
    verified_range: '5001-10000',
    verified_linkedin_url: 'https://linkedin.com/company/zendesk',
    identity_method: 'ai-verified:exa',
  };
}

const verifiedRows1 = [
  // Row A: round-1 pass, round 2 never ran for it (no entry in the map).
  verifiedRow('rec-a', 'stripe.com', '1001-5000', round1Pass()),
  // Row B: round-1 failure, rescued by round 2 (the zendesk.com case from
  // the real run this bug was found against).
  verifiedRow('rec-b', 'zendesk.com', '5001-10000', round1Fail('not-scraped')),
  // Row C: round-1 failure, round 2 also rejected it (segment.com case).
  verifiedRow('rec-c', 'segment.com', '1001-5000', round1Fail('ai-rejected')),
];

const round2ByRecordId = {
  'rec-b': round2Rescue(),
  'rec-c': round1Fail('ai-rejected'),
  // Deliberately no entry for 'rec-a': round 1 already passed for it.
};

const rows = buildOutputRows(verifiedRows1, round2ByRecordId);

assert.strictEqual(rows.length, 3, 'must return exactly one output row per input row');

// Row A: pass-through fields carried straight from the input row, round-1
// verification untouched.
assert.strictEqual(rows[0].record_id, 'rec-a');
assert.strictEqual(rows[0].domain, 'stripe.com');
assert.strictEqual(rows[0].stored_employee_count, '1001-5000');
assert.strictEqual(rows[0].verified_employee_count, 50000);
assert.strictEqual(rows[0].identity_method, 'website-match:icypeas');

// Row B: rescued -- must carry round 2's count, range, source, URL, method.
assert.strictEqual(rows[1].record_id, 'rec-b');
assert.strictEqual(rows[1].domain, 'zendesk.com');
assert.strictEqual(rows[1].stored_employee_count, '5001-10000');
assert.strictEqual(rows[1].verified_employee_count, 7603);
assert.strictEqual(rows[1].verified_range, '5001-10000');
assert.strictEqual(rows[1].source, 'harvestapi via apify');
assert.strictEqual(rows[1].verified_linkedin_url, 'https://linkedin.com/company/zendesk');
assert.strictEqual(rows[1].identity_method, 'ai-verified:exa');

// Row C: rejected both rounds -- stays empty/unverifiable, not a mismatch.
assert.strictEqual(rows[2].record_id, 'rec-c');
assert.strictEqual(rows[2].verified_employee_count, '');
assert.strictEqual(rows[2].identity_method, 'ai-rejected');

// Every row must carry the fields the report card scorer and
// `ctx.dataset('output', ...)` both need -- a dropped key here would ship a
// dataset column silently missing from every row.
const requiredKeys = [
  'record_id', 'domain', 'stored_employee_count', 'verified_employee_count',
  'source', 'verified_range', 'verified_linkedin_url', 'identity_method',
];
for (const row of rows) {
  for (const key of requiredKeys) {
    assert.ok(Object.prototype.hasOwnProperty.call(row, key), `row missing required key: ${key}`);
  }
}

console.log('OK');
"""


def _extract_pure_helpers() -> str:
    source = open(PLAY_TS, encoding="utf-8").read()
    start = source.index(START_MARKER)
    end = source.index(END_MARKER)
    assert start < end, "pure-helpers markers are out of order in play.ts"
    return source[start:end]


def test_build_output_rows_source_is_reachable_via_the_pure_helpers_block():
    helpers = _extract_pure_helpers()
    assert "function buildOutputRows" in helpers, (
        "buildOutputRows must live inside the pure-helpers block so this "
        "test can see it without a runtime"
    )


def test_build_output_rows_shape_covers_pass_rescue_and_double_reject():
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
            f"node buildOutputRows check failed.\nstdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert "OK" in result.stdout
    finally:
        os.unlink(path)
