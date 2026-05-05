# validate_contact_identity

Confirm that a scraped LinkedIn profile belongs to the right person. Two-tier strategy: deterministic name + company match, with an AI tiebreaker (gpt-5-mini) only when the two signals split.

## Why this exists

Scraping a LinkedIn URL doesn't tell you the URL was correct. URL discovery (`find_contact_linkedin_url`) returns plausible candidates; profile scraping (`enrich_contact_linkedin_profile`) returns whatever profile the URL points at. Without an identity check, every downstream function — job-change detection, persona classification, scoring — operates on the wrong person's data when the URL was wrong. This is the gate that catches it.

## When to use

- After `enrich_contact_linkedin_profile` and before any function that conditions on the scrape (job-change detection, persona/seniority classification, scoring).
- Recipe-level pattern: gate downstream functions on `validate_contact_identity.identity_match !== 'mismatch'`.

## When NOT to use

- The `linkedin_url` came from the CRM as a hand-validated field by a human. Skip the function — trust the source.
- You only need persona classification and don't care whether the profile is the right person (rare — almost always you do).

## Verdict ladder

| Verdict | Meaning | Recipe should... |
|---|---|---|
| `confirmed` | Both name AND company matched deterministically (no AI cost) | Continue all downstream functions. |
| `weak` | Deterministic signals split; AI tiebreaker leaned match | Continue, but flag for human QA when stakes are high (CRM writeback). |
| `mismatch` | AI tiebreaker leaned no-match, OR name fundamentally mismatched (similarity < 0.5) | Stop the row. Do NOT scrape further, do NOT classify, do NOT score. |

## Strategy

| Tier | Logic | Cost |
|---|---|---|
| Deterministic | Levenshtein name match (with 50+ nickname-dictionary expansions) + experience-history company search (fuzzy name OR domain match against ALL experience entries, not just current) | zero |
| AI tiebreaker | gpt-5-mini judgment, runs ONLY when name matches but company doesn't, OR vice versa | one cheap call |

When name AND company both match deterministically → `confirmed`, AI doesn't run.

When name fundamentally mismatches (similarity < 0.5) → `mismatch`, AI doesn't run.

When deterministic signals are split → AI tiebreaker fires.

This gating cuts AI cost by ~60% vs Ontra's "run AI on every row" approach in their Clay table.

## Why search the FULL experience history for company match

Contacts move companies between scrape and CRM update. A row whose `expected_company_name` is the contact's *prior* employer (because the CRM is stale) should still validate as the same person — the function just confirms the contact ever worked there. Job-change detection (`detect_job_change`) is the function that decides whether they're still there.

If the function only matched against the current role, every row whose contact had moved would emit `mismatch`, the recipe would stop, and the cleanup engine would never tag those contacts as "moved" — defeating the whole point of contact cleanup.

## Why title is a SOFT signal only

Title is captured (input + AI prompt) but never causes a deterministic mismatch. Reasons:
- Senior-to-junior moves (especially M&A absorption) keep the same person at the same company with a different title.
- Cross-department moves (Sales → CS, Eng → Product) keep the same person at the same company with a different title.
- AI-generated titles in CRMs (auto-enrichment from data providers) drift fast.

The agency rule: title goes into `classify_multi_dim_via_latitude` (where it's the right signal), not `validate_contact_identity` (where it's noise).

## Inputs / outputs

See `function.yaml`. The contract REQUIRES `profile_json` (from `enrich_contact_linkedin_profile`) and the expected name + company. Title and domain are optional softer signals.

## Gotchas

- **First-name nicknames.** The deterministic step expands ~50 common English nicknames (Bill→William, Bob→Robert, etc.). Non-English nicknames or name-variant transliterations are NOT covered — the AI tiebreaker catches those (e.g. "Eduardo" vs "Edward", "Sasha" vs "Alexander"). If you see deterministic name-mismatches firing on legitimate transliterations, expand the dictionary or trust the AI.
- **Domain match is strict.** The function does `expected_domain === experience_domain` OR substring containment in either direction. Doesn't handle parent-domain ↔ subsidiary-domain (e.g. `acme.com` vs `acme-eu.com`). When stakes are high, pre-normalize domain in the recipe before passing.
- **AI tiebreaker prompt is INPUT-FORMAT-FRAGILE.** The prompt expects `profile_companies[]` as a JSON array. The runtime templating does this correctly today, but template-engine changes could break it. Smoke-test the AI step in isolation if upgrading Deepline.
- **`weak` is a real outcome.** Don't collapse `confirmed | weak` to a single boolean at the recipe level — the downstream `score_contact_fit` function reads the verdict to decide tier, and weak should map to a lower tier.
- **No `identity_match: 'unclear'`.** When in doubt, the function returns `mismatch`. The agency philosophy: false-negatives (good rows dropped) are easier to recover from than false-positives (bad rows enriched and written back to CRM).

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/validate_contact_identity.workflow.json)"

# Confirmed — name + company both match deterministically:
deepline workflows call --workflow-id <ID> --payload '{
  "profile_json": {
    "firstName": "Bill",
    "lastName": "Gates",
    "position": [{"companyName": "Bill & Melinda Gates Foundation", "title": "Co-chair"}]
  },
  "expected_first_name": "William",
  "expected_last_name": "Gates",
  "expected_company_name": "Bill & Melinda Gates Foundation"
}'
# Expect: identity_match="confirmed", ai_tiebreaker.ran=false.

# Mismatch — fundamental name mismatch:
deepline workflows call --workflow-id <ID> --payload '{
  "profile_json": {"firstName": "Sundar", "lastName": "Pichai", "position": [{"companyName": "Google"}]},
  "expected_first_name": "Bill",
  "expected_last_name": "Gates",
  "expected_company_name": "Microsoft"
}'
# Expect: identity_match="mismatch", ai_tiebreaker.ran=false.

# Tiebreaker — name matches but expected company isn't in experience history:
deepline workflows call --workflow-id <ID> --payload '{
  "profile_json": {
    "firstName": "Tim",
    "lastName": "Cook",
    "position": [{"companyName": "Apple", "title": "CEO"}, {"companyName": "Compaq", "title": "VP"}]
  },
  "expected_first_name": "Tim",
  "expected_last_name": "Cook",
  "expected_company_name": "Microsoft"
}'
# Expect: ai_tiebreaker.ran=true, ai says is_match=false (Tim Cook never worked at Microsoft),
#   identity_match="mismatch".
```

## Related

- **Upstream:** `enrich_contact_linkedin_profile` (provides `profile_json`).
- **Downstream:** `detect_job_change`, `classify_multi_dim_via_latitude`, `score_contact_fit` (typically gated on `identity_match !== 'mismatch'`).
- **Sibling (account-side):** `linkedin_url_verified`'s tier_1_verify / tier_2_verify steps — same matching-engine philosophy, applied to companies instead of people.
