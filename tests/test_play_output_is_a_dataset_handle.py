"""Structural regression guard: employee-count-accuracy's play.ts must return
its merged rows as a durable DATASET HANDLE (`ctx.dataset('output',
...).run(...)`), never a materialized plain array.

This is the exact class of bug a real paid run caught: the round-1/round-2
merge (mergeVerification, buildOutputRows) was correct, and every unit test
on that merge logic passed, but the play still returned
`verifiedRows1.map(...)` -- a plain JS array -- as `rows`. The Deepline
runtime caps a play's inline return payload (the run-event document has a
size limit), so a 100-row array silently truncated to 20 rows on the real
run. `deepline runs export --dataset result.rows` then failed outright
("did not return a dataset at result.rows") because there was no dataset
backing it at all.

A shape-only test on the merge function cannot catch this: the shape was
always right. What has to be asserted is the RETURN PLUMBING itself -- that
`result.rows` is a dataset handle, not a value -- and `deepline plays check`
is the authoritative, money-free source for that: its static analysis
reports `isDataset` per return field precisely because that is the
information a human reviewing a diff cannot easily eyeball out of a
`return { rows: ... }` statement.

Skips (does not fail) when `deepline` is not on PATH, since it is a Deepline
CLI prerequisite rather than a Python test dependency, same policy as the
`node` skip in the other play tests.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess

import pytest

PLAY_TS = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "crm-report-card", "plays",
    "employee-count-accuracy", "play.ts"))


def _run_plays_check() -> dict:
    result = subprocess.run(
        ["deepline", "plays", "check", PLAY_TS],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, (
        f"deepline plays check exited non-zero.\nstdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    # The CLI can print a one-line update notice ahead of the JSON payload
    # ("A newer Deepline SDK/CLI is available..."); skip any line that isn't
    # part of the JSON object rather than assuming the JSON is on line 1.
    lines = result.stdout.splitlines()
    json_lines = [ln for ln in lines if ln.strip().startswith("{")]
    assert json_lines, f"no JSON object found in deepline plays check output:\n{result.stdout}"
    return json.loads(json_lines[0])


def test_deepline_plays_check_reports_the_play_as_valid():
    if shutil.which("deepline") is None:
        pytest.skip("deepline CLI is not on PATH")

    report = _run_plays_check()
    assert report["valid"] is True
    assert report["errors"] == []


def test_final_return_field_rows_is_a_dataset_handle_not_an_inline_array():
    """The regression test. `rows` must be isDataset: true, backed by a named
    `ctx.dataset(...)` table -- NOT a plain array/value return -- so a full
    100+ row run is retrievable via `deepline runs export`, not capped at
    whatever the inline run-event document limit truncates a JSON array to.
    """
    if shutil.which("deepline") is None:
        pytest.skip("deepline CLI is not on PATH")

    report = _run_plays_check()
    return_fields = report["staticPipeline"]["returnFields"]
    by_name = {f["name"]: f for f in return_fields}

    assert "rows" in by_name, f"play must return a top-level `rows` field, got: {by_name.keys()}"
    rows_field = by_name["rows"]

    assert rows_field["isDataset"] is True, (
        "result.rows regressed to a plain value/array return. It must be a "
        "ctx.dataset(...).run(...) HANDLE (not `.materialize()`-d, not "
        "wrapped in `.map(...)`), or large runs will silently truncate to "
        "the platform's inline-return row cap instead of being fully "
        "retrievable via `deepline runs export`."
    )
    assert rows_field.get("datasetName"), (
        "rows is flagged as a dataset but has no backing datasetName -- "
        "the return statement should read `return { rows: <dataset handle "
        "variable> }` where that variable came straight from "
        "`ctx.dataset(key, ...).run(...)` with no `.materialize()` in between."
    )


def test_source_return_statement_does_not_materialize_the_output_dataset():
    """Belt-and-suspenders source check alongside the `deepline plays check`
    assertion above: guards the one line that actually caused the
    regression (materializing the dataset before returning it), readable
    without needing the CLI at all.
    """
    source = open(PLAY_TS, encoding="utf-8").read()

    assert "return { rows: output };" in source, (
        "expected the final return to hand back the raw `output` dataset "
        "handle directly, e.g. `return { rows: output };` -- if this "
        "assertion needs updating because the variable was renamed, also "
        "confirm the new variable is never `.materialize()`-d first"
    )
    assert "await output.materialize()" not in source and "output.materialize(" not in source, (
        "the `output` dataset handle must never be materialized before "
        "being returned -- materializing it turns the return back into a "
        "plain array and reintroduces the truncation bug"
    )
