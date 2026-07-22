# CRM Report Card Tier 0: eval criteria

Five binary checks. All five must pass for a build to ship. Runnable commands
for each are in `eval/cases.jsonc`.

1. **Golden fixture duplicates match.** On the golden fixture
   (`fixtures/messy-crm-sample.csv`), the computed `duplicate_records` count
   and `overall_grade` match `fixtures/messy-crm-sample.expected.json`.
2. **403 is bot-blocked, never dead.** A domain that returns HTTP 403 (or
   429) is classified and counted under `bot_blocked`, and is never counted
   under `dead`.
3. **AI numbers are tagged as estimates.** Every number in the rendered HTML
   that comes from the single-pass AI qualified-percent baseline is inside an
   element tagged `ESTIMATE` (and marked `NOT VERIFIED`), so it can never be
   mistaken for a measured fact.
4. **No raw CRM rows in the report.** The rendered HTML contains no raw CRM
   row values from the input CSV (names, emails, company name variants).
   It carries only aggregates (counts, rates, grades).
5. **Sanitization guard passes.** `tests/test_sanitization.py` passes: no
   secret or internal path leaks into any shippable file (`SKILL.md`,
   `README.md`, `scripts/`, `assets/`, `eval/`, `fixtures/`, `tests/`,
   `pyproject.toml`, `requirements-dev.txt`).
