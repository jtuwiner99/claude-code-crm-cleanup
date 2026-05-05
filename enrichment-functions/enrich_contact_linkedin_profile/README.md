# enrich_contact_linkedin_profile

Fetch a contact's full LinkedIn profile from a verified URL using Harvest's direct API. Returns the raw provider payload plus convenience-extracted fields (current_role, current_company_name, location, name) that downstream contact-side functions consume directly.

## Why this exists

Contact cleanup, identity validation, job-change detection, and persona/seniority classification all share one upstream concern: getting accurate, current LinkedIn data for a person. Without a reliable scrape, every downstream function operates on stale CRM data and the whole pipeline produces noise. Harvest's direct API is the agency's chosen scraper because it returns LinkedIn-direct data (more current than provider-metadata waterfalls) at a credit cost that keeps cleanup runs viable.

## When to use

- Any contact-side recipe that needs current employer, current title, location, or full work history.
- The single Harvest call site in a recipe — every downstream contact-side function should read off this function's output, not hit Harvest themselves.

## When NOT to use

- The CRM already has hand-validated current_company + current_title and the recipe only needs persona/seniority. Use `classify_multi_dim_via_latitude` directly with title + company_name.
- You need batch-friendly bulk LinkedIn scraping (>10k profiles in one run). Harvest's per-call cost adds up — fall back to Apify HarvestAPI's batch actor for jobs at that scale.
- The `linkedin_url` on the row is unverified. Resolve via `find_contact_linkedin_url` first — Harvest will happily scrape any URL, including the wrong person.

## Provider choice

| Provider | Why chosen | Why not the alternative |
|---|---|---|
| **Harvest direct API** (`api.harvest-api.com/linkedin/profile`) | LinkedIn-direct, lower latency than the Apify actor, separate API key from Apify usage | — |
| Apify HarvestAPI actor | (Available via `apify` Deepline tool) | Higher latency (actor-startup cost), batch-oriented, billed via Apify credits — preferred for >10k-row batch scrapes |
| MixRank `enrich-person-with-mixrank-v2` | (Used in Ontra's source Clay table) | Not available as a Deepline tool. Substituted with Harvest direct. |
| PDL `enrich_person` | (Available) | Provider-metadata; lags LinkedIn by weeks for current_company. Reserved for non-time-sensitive use cases. |

## Optional flags (Layer-3 add-ons)

| Flag | Default | Cost impact | Use when |
|---|---|---|---|
| `find_email` | false | Higher per call | Recipe wants email + profile in one call instead of running a separate `find_contact_email` waterfall. Good for cost-conscious cleanup. |
| `skip_smtp` | false | Cheaper than `find_email` alone | Combined with `find_email` to skip SMTP verification — faster, cheaper, less reliable. Use for low-stakes outbound. |
| `include_about_profile` | false | Higher per call | Trust/QA signal — flags accounts created <30 days ago (likely fake) or with recent name changes. Use for high-stakes outbound. |
| `main_only` | false | Cheapest | Returns truncated profile (5 experiences, 2 educations). Use when downstream only needs current_role + one prior employer (e.g. job-change-loop recipe). |

## Inputs / outputs

See `function.yaml`. The contract REQUIRES a verified `linkedin_url` and `harvest_api_key`. Outputs hoist convenience fields:

- `current_role` — `{ title, company_name, company_linkedin_url, company_domain, started_at, location }` from the first experience entry
- `current_company_name` — direct input to `detect_job_change`
- `name` — direct input to `validate_contact_identity`
- `experience[]` — full work history for downstream callers that need it
- `profile_json` — raw Harvest `element` object for any field this function doesn't hoist

## Caching `profile_json`

The function exposes the full Harvest payload. Downstream functions (`validate_contact_identity`, `detect_job_change`, `classify_multi_dim_via_latitude`) consume specific fields off `profile_json` rather than re-spending a Harvest credit. Recipe authors: pass `profile_json` to every downstream function that needs richer signals than the convenience hoists.

## Gotchas

- **`linkedin_url` must be a profile URL.** `linkedin.com/in/<slug>`, not `linkedin.com/company/<slug>`. The function does not validate this — Harvest will return a meaningless or empty `element` if you pass a company URL. Caller is responsible (typically `find_contact_linkedin_url` only returns profile URLs).
- **`current_role` picks the FIRST experience entry.** Harvest sorts current-first, but contacts with multiple concurrent roles (e.g. board seats + day job) lose the secondary roles in this hoist. Read `profile_json.position[]` directly when you need all concurrent positions.
- **Field-name drift across Harvest endpoint versions.** The compose_output JS coalesces between `firstName`/`first_name`, `position`/`experience`, `companyName`/`company`, etc., based on observed Harvest response shapes. If Harvest changes their schema, the EXTRACT_JS may silently null fields that were previously populated. The `verification_signals.harvest.response_excerpt` (first 500 chars of the raw body) is the audit hook for diagnosing schema drift.
- **`email.is_risky=true` doesn't mean unusable.** Catch-all domains, SMTP-skipped, and SMTP-failed all flag as risky. Catch-all is by far the most common — Harvest can't verify the address but the domain *might* deliver. Treat as a sender-risk-tolerance signal, not a hard reject.
- **`main_only=true` cripples job-change detection if the on-record company isn't in the top 5 experiences.** Don't combine `main_only=true` with `detect_job_change` for contacts whose tenure history is long.
- **Harvest's `findEmail` is not the same as the `find_contact_email` waterfall** (a Layer-3 plugin that's deferred). The flag here returns one Harvest-found email; the waterfall would chain leadmagic → datagma → bettercontact. Use the flag when one provider's coverage is acceptable; build the waterfall when you need the long-tail.

## Smoke test

```bash
# From a client repo with .env loaded:
deepline workflows apply --payload "$(cat tmp/enrich_contact_linkedin_profile.workflow.json)"
deepline workflows call --workflow-id <ID> --payload '{
  "linkedin_url": "https://www.linkedin.com/in/williamhgates",
  "harvest_api_key": "<YOUR_KEY>"
}'
# Expect: profile_json.firstName="Bill", current_role.company_name contains "Bill & Melinda Gates Foundation",
#   name.full="Bill Gates", verification_signals.harvest.ok=true.
```

For the email + about-this-profile flags:
```bash
deepline workflows call --workflow-id <ID> --payload '{
  "linkedin_url": "https://www.linkedin.com/in/williamhgates",
  "harvest_api_key": "<YOUR_KEY>",
  "find_email": true,
  "include_about_profile": true
}'
# Expect: email.address populated (or null with reasoning in raw),
#   about_this_profile populated with Harvest's popup fields.
```

## Related

- **Upstream:** `find_contact_linkedin_url` (when URL not on row).
- **Downstream:** `validate_contact_identity`, `detect_job_change`, `classify_multi_dim_via_latitude`.
- **Sibling (account-side):** `linkedin_url_verified` — verified company URL + firmographics from Lusha→PDL waterfall.
- **Profile extractor:** the HarvestAPI profile extractor (companion script in your project).
