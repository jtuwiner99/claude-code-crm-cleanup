"""Exercise mergeVerification -- the function that decides, for each row in
employee-count-accuracy's play.ts, whether the final output keeps round 1's
identity-check result or takes round 2's rescue -- directly via Node, same
pattern as test_play_domain_helpers.py and test_play_name_corroboration.py.

This is the fix for a real data-loss bug: round 2 (the Exa alternate-
candidate rescue) computed correct verified counts in its own durable
`verify_alt` dataset, but the play's final `return { rows: ... }` kept
shipping round 1's rejected state for those same rows. Root cause was a
column-name collision -- round 2's `.withColumn` reused the name
`verification`, which already existed on its input rows (carried forward
from round 1's failed outcome), so the round-2 value never reliably reached
the in-memory row the return statement read from. The fix renames round 2's
column to `altVerification` and routes every row through mergeVerification()
so there is exactly one place, tested here, that decides which round wins.

Reads the live pure-helper block out of play.ts every run (same
START_MARKER/END_MARKER extraction as the other two play tests) so a future
edit that reintroduces the collision, or breaks the merge precedence, fails
this test rather than a parallel Python reimplementation that could drift.

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

function round1Pass(overrides) {
  return Object.assign({
    passed: true,
    verified_employee_count: 250,
    source: 'harvestapi via apify',
    verified_range: '201-500',
    verified_linkedin_url: 'https://linkedin.com/company/stripe',
    identity_method: 'website-match:icypeas',
  }, overrides || {});
}

function round1Fail(overrides) {
  return Object.assign({
    passed: false,
    verified_employee_count: '',
    source: '',
    verified_range: '',
    verified_linkedin_url: '',
    identity_method: 'ai-rejected',
  }, overrides || {});
}

function round2Rescue(overrides) {
  return Object.assign({
    passed: true,
    verified_employee_count: 1205,
    source: 'harvestapi via apify',
    verified_range: '1001-5000',
    verified_linkedin_url: 'https://linkedin.com/company/airtable',
    identity_method: 'website-match:exa',
  }, overrides || {});
}

function round2StillRejected(overrides) {
  return Object.assign({
    passed: false,
    verified_employee_count: '',
    source: '',
    verified_range: '',
    verified_linkedin_url: '',
    identity_method: 'ai-rejected',
  }, overrides || {});
}

// 1. A round-1 PASS is untouched, even when (implausibly) a round-2 entry
// exists for it -- round 2 must never override a row that already succeeded.
{
  const r1 = round1Pass();
  const result = mergeVerification(r1, round2Rescue());
  assert.strictEqual(result, r1, 'round-1 pass must be returned untouched, same reference');
}

// 2. A round-1 failure that round 2 rescues takes the alternate's URL,
// count, range, source, and identity_method -- the airtable.com case from
// the real run this bug was found in.
{
  const r1 = round1Fail();
  const r2 = round2Rescue();
  const result = mergeVerification(r1, r2);
  assert.strictEqual(result.verified_employee_count, 1205);
  assert.strictEqual(result.verified_range, '1001-5000');
  assert.strictEqual(result.verified_linkedin_url, 'https://linkedin.com/company/airtable');
  assert.strictEqual(result.source, 'harvestapi via apify');
  assert.strictEqual(result.identity_method, 'website-match:exa');
}

// 3. A round-1 failure that round 2 ALSO rejects keeps round-1 state exactly
// -- segment.com in the real run, correctly rejected both times.
{
  const r1 = round1Fail({ identity_method: 'ai-rejected' });
  const r2 = round2StillRejected();
  const result = mergeVerification(r1, r2);
  assert.strictEqual(result, r2, 'both rounds failed: round-2 rejected state stands (round 2 is the last word tried)');
  assert.strictEqual(result.verified_employee_count, '');
  assert.strictEqual(result.passed, false);
}

// 4. A row never seen by round 2 at all (no entry in round2ByRecordId --
// e.g. round 2 never ran because round 1 had zero failures, or this
// particular record_id has no key in the map) is unchanged: falls back to
// round 1's own (failed) state.
{
  const r1 = round1Fail({ identity_method: 'not-scraped' });
  const result = mergeVerification(r1, undefined);
  assert.strictEqual(result, r1, 'no round-2 entry: round-1 state must pass through unchanged');
}

console.log('OK');
"""


def _extract_pure_helpers() -> str:
    source = open(PLAY_TS, encoding="utf-8").read()
    start = source.index(START_MARKER)
    end = source.index(END_MARKER)
    assert start < end, "pure-helpers markers are out of order in play.ts"
    return source[start:end]


def test_merge_verification_source_is_reachable_via_the_pure_helpers_block():
    """A rename or relocation of mergeVerification out of the marked block
    would make the extraction below silently test nothing useful."""
    helpers = _extract_pure_helpers()
    assert "function mergeVerification" in helpers, (
        "mergeVerification must live inside the pure-helpers block so this "
        "test (and deepline's static analyzer) can see it without a runtime"
    )


def test_merge_verification_round1_pass_rescue_rejection_and_unseen_row():
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
            f"node mergeVerification check failed.\nstdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert "OK" in result.stdout
    finally:
        os.unlink(path)
