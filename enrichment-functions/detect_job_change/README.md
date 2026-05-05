# detect_job_change

Compare a contact's scraped current employer vs the company on the CRM row. Pure deterministic — no AI calls. Emits `status: still_there | moved | unclear` plus the new role's details when moved, including a `started_role_within_3_months` boolean for high-value-contact triggers.

## Why this exists

Contact CRMs go stale fast. According to LinkedIn's own data, ~25% of B2B SaaS contacts change roles every 18 months. Without a job-change check on every cleanup pass, sales teams call wrong-company contacts, marketing emails bounce off corporate spam filters, and pipeline visibility degrades silently. This function is the cheapest way to detect movement — pure JS over the already-scraped Harvest payload, zero new spend.

## When to use

- Any contact-cleanup recipe (one-time or recurring).
- Specifically as part of the recurring `contact_job_change_loop` recipe — runs on a cron against contacts whose URL is already verified, emits `moved` events to the CRM.

## When NOT to use

- The contact's `profile_json` isn't available (`enrich_contact_linkedin_profile` failed). Function returns `unclear` and the recipe should treat it as "couldn't check."
- You need to detect company-side acquisitions (parent-child rollup of two companies into one). That's `detect_acquisition` (account-side opt-in plugin) — different concern.

## Logic

| Condition | Output |
|---|---|
| `profile_json=null` OR `position[]` empty | `status=unclear`, all new_* fields null |
| Profile current-company matches on-record (name similarity ≥ 0.8 OR domain match) | `status=still_there`, new_* fields equal on-record values |
| Profile current-company differs from on-record | `status=moved`, new_* populated from `position[0]` |

`started_role_within_3_months` = true when status=`moved` AND parsed start_date is within 90 days. Direct port of Ontra's `moment().diff(moment(date), "months") < 3` formula.

## Why fuzzy match (not exact)

Company names rarely match exactly between CRMs and LinkedIn:
- LinkedIn names often include legal suffixes (`Acme Corp` vs CRM's `Acme`)
- Brand consolidation (LinkedIn shows the parent brand; CRM has the sub-brand)
- Punctuation, casing, and whitespace differences
- Regional subsidiaries (`Acme - North America` vs `Acme`)

The function normalizes (lowercase, strip non-alphanumeric, NFD-normalize accents) then runs Levenshtein similarity. Threshold 0.8 catches the common cases without false-matching unrelated companies.

## Why pick `position[0]` as current role

Harvest sorts the position array current-first. When a contact has multiple concurrent roles (board seat + day job, advisor + employee), only the first wins. This is intentional — the function's job is "what's the contact doing primarily right now," not "list every concurrent role." Customers who need finer handling read `profile_json.position[]` directly at the recipe level and override.

## Why no AI

Job-change detection is a pure string comparison. Adding AI for fuzzy company matching would burn cost on every row when the deterministic threshold catches the common cases. The function pre-normalizes aggressively (Levenshtein ≥ 0.8 on the normalized strings catches `Acme Corp` ≈ `Acme`, `Stripe Inc.` ≈ `Stripe`, `Acme - EMEA` ≈ `Acme`).

When the deterministic threshold misses (e.g. brand-renamed companies like `Facebook` ≈ `Meta`), the recipe-level fix is to update the on-record name, not run AI on every row of every cleanup pass.

## Inputs / outputs

See `function.yaml`. The contract REQUIRES `profile_json` and `on_record_company_name`. Pass `on_record_company_domain` when available — it's the strongest tiebreaker for generic-named companies.

## Gotchas

- **Brand-renamed companies trigger false `moved`.** `Facebook → Meta`, `Square → Block`. The function emits `status=moved` even though the person is at the same legal entity. Recipe-level fix: maintain a brand-rename allowlist and post-process. v2 might absorb this into the function with a small list.
- **Non-parseable start_dates emit `started_role_within_3_months=false` even when the role is recent.** The function uses `new Date(profStart)` — formats like "Jan 2026" or "Q1 2026" parse correctly in V8; "Started 3 weeks ago" does not. Most provider data (Harvest, Apify HarvestAPI) returns ISO dates; if your scraper returns relative dates, pre-normalize.
- **Multi-concurrent-role contacts.** `position[0]` is current. Board seats and advisor roles often appear before primary employment in the array — Harvest's sort isn't guaranteed when start dates overlap. If your audience is C-suite executives with many board seats, validate the picked current_role with a smoke test on representative rows.
- **`status=unclear` is NOT `status=still_there`.** A null profile or empty experience array means we don't know — caller MUST treat unclear as "couldn't determine," not as "presumed unchanged." Recipes typically gate the new-company writeback on `status=='moved'` only, leaving `unclear` rows untouched.
- **`started_role_within_3_months` doesn't gate on `status`.** When status=`still_there`, the boolean is always false (the contact didn't START a new role; they're still in the existing one). When status=`moved`, the boolean reflects the recency of the move. When status=`unclear`, false.

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/detect_job_change.workflow.json)"

# Still there:
deepline workflows call --workflow-id <ID> --payload '{
  "profile_json": {"position": [{"companyName": "Stripe", "title": "VP Eng", "startDate": "2022-03-15"}]},
  "on_record_company_name": "Stripe"
}'
# Expect: status="still_there", started_role_within_3_months=false.

# Moved (recent):
deepline workflows call --workflow-id <ID> --payload '{
  "profile_json": {"position": [{"companyName": "Anthropic", "title": "Head of Sales", "startDate": "2026-04-01", "companyWebsite": "anthropic.com"}]},
  "on_record_company_name": "Stripe"
}'
# Expect: status="moved", new_company_name="Anthropic", started_role_within_3_months=true.

# Unclear (no profile):
deepline workflows call --workflow-id <ID> --payload '{
  "profile_json": null,
  "on_record_company_name": "Stripe"
}'
# Expect: status="unclear".
```

## Related

- **Upstream:** `enrich_contact_linkedin_profile`, `validate_contact_identity` (typically gated on `identity_match !== 'mismatch'` before this runs).
- **Downstream:** `score_contact_fit` (uses `status === 'still_there'` as a hard gate input).
- **Recurring recipe caller:** `contact_job_change_loop` — the production use case for this function.
