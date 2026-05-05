# extract_hq_address

Extract a company's HQ address (street, city, state, postal_code, country) and emit it in CRM-ready format with user-controlled formatting toggles.

## Why this exists

Every customer wants HQ address as a CRM field — it's a default need across engagements. Two real-world wrinkles this function handles:

1. **Address sources are inconsistent.** LinkedIn-direct providers (Apify HarvestAPI) include structured `headquarters` fields. PDL's `enrich_company` does NOT. Today's PDL-backed `linkedin_url_verified` typically returns no address; tomorrow's Harvest-backed version will. Function reads from whatever the cached payload exposes, falls through to AI web-scrape when incomplete.

2. **CRM formatting conventions vary.** HubSpot defaults to "Maryland" / "United States". Many Salesforce orgs use "MD" / "US". Writing the wrong one silently breaks segmentation and routing. Function accepts `state_format` + `country_format` toggles so you pick the convention once at the recipe level.

## Two-source strategy

| Step | Source | Cost | Runs when |
|---|---|---|---|
| 1 | Cached LinkedIn provider payload | $0 | Always |
| 2 | AI web-scrape (deeplineagent on the company's `/about`, `/contact`, `/imprint`, footer pages) | one cheap-AI call (~$0.005) | Step 1 didn't return a complete address (street + city + country) |

Today (with PDL-backed LinkedIn enrichment) step 2 fires for nearly every row. Once `linkedin_url_verified` upgrades to Apify HarvestAPI as a primary, step 2 will only fire for the long tail.

## Pipeline placement

Default function — runs on every account enrichment recipe. Comes after `linkedin_url_verified` (needs the cached payload). Comes alongside or before `country_presence_verified` (which is opt-in).

```
normalize_domain_and_name
       ↓
verify_domain_alive
       ↓
company_summary_from_website
       ↓
linkedin_url_verified
       ↓
extract_hq_address  ← always-on default
       ↓
[country_presence_verified]  ← opt-in add-on
       ↓
classify_via_latitude
```

## Inputs / outputs

See `function.yaml` for the typed contract. Two things to highlight:

1. **Formatting toggles are per-recipe, not per-row.** `state_format` and `country_format` should be set once at the calling recipe level based on your CRM convention. Don't try to detect them per-row.

2. **`hq_full_address` is concatenated for direct CRM writeback.** When your CRM has a single "Headquarters" string field, write `hq_full_address`. When the CRM has separate Street / City / State / Country fields, write the individual outputs.

## Formatting examples

With `state_format: "abbreviation"` and `country_format: "iso_alpha_2"` (defaults):

```
1455 Market St, San Francisco, CA 94103, US
```

With `state_format: "full"` and `country_format: "full"`:

```
1455 Market St, San Francisco, California 94103, United States
```

For non-US/Canada countries, `state` is whatever the source returned (e.g. "Bavaria", "Greater London") — abbreviation map only covers US states + Canadian provinces.

## Multi-location companies

The function returns the **headquarters only**, not a list. The selection logic (in priority order):

1. LinkedIn payload entry explicitly marked `is_headquarters: true` / `type: "HEADQUARTERS"` (Apify HarvestAPI marks this)
2. First entry in `locations[]` array (LinkedIn's default ordering puts HQ first)
3. The single `headquarters` field if exposed at top level
4. The `location` field if exposed (PDL convention)
5. AI agent picks the HQ from the website (looks for "Corporate", "Global HQ", "Main Office" labels, or matches against the company's primary domain country)

A separate `extract_all_locations` function can be built when you need the full list of offices — not yet scaffolded.

## Default-to-null on failure

When BOTH paths fail to find a complete address:

- `address_source = "none"`
- All address fields null
- Caller decides what to do (keep the row, flag for human review, retry with a different model)

The function does NOT fabricate addresses. Better to write null to the CRM than to write a guessed street.

## Gotchas

- **PDL doesn't expose structured address.** Today's `linkedin_url_verified` uses PDL, so step 1 typically returns mostly nulls. The web-scrape fallback fires. This is expected; document for downstream consumers that the function burns one cheap-AI call per row in current configuration.
- **State abbreviation map covers US + Canada only.** International addresses keep whatever the source returned for state. Don't over-abbreviate Bavarian / Tuscan / Greater London regions.
- **Postal codes vary wildly.** US 5+4 ZIP, UK postcodes, German 5-digit PLZ, French 5-digit CP. Function returns whatever the source emits without normalization. Customer CRM may need its own format-cleaning.
- **Solo founders / very small companies** often have no public address. Web-scrape fallback returns all-null with reasoning explaining why. That's correct — don't push the AI to invent.
- **Multi-HQ companies** (genuinely have two corporate offices, e.g. one in EU and one in US) — function returns ONE. Recipe-level logic decides which to use, or use `country_presence_verified` to drop the wrong-geography one before this step.

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/extract_hq_address.workflow.json)"

# Case 1: US company, LinkedIn payload incomplete (PDL default)
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "stripe.com",
  "company_name_clean": "Stripe",
  "linkedin_full_provider_payload": {"name": "Stripe", "industry": "Financial Services", "website": "stripe.com"}
}'
# Expect: address_source=web_scrape, hq_city="South San Francisco" (or San Francisco), hq_state="CA",
#   hq_country="US", hq_full_address populated.

# Case 2: explicit full-format toggle for HubSpot writeback
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "stripe.com",
  "company_name_clean": "Stripe",
  "linkedin_full_provider_payload": {"name": "Stripe"},
  "state_format": "full",
  "country_format": "full"
}'
# Expect: hq_state="California", hq_country="United States"

# Case 3: LinkedIn payload IS complete (simulates future HarvestAPI upgrade)
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "stripe.com",
  "company_name_clean": "Stripe",
  "linkedin_full_provider_payload": {
    "headquarters": {"street_address": "354 Oyster Point Blvd", "city": "South San Francisco", "region": "California", "postal_code": "94080", "country": "United States"}
  }
}'
# Expect: address_source=linkedin (no AI call burned), hq_state="CA" (default abbreviation),
#   hq_country="US"
```
