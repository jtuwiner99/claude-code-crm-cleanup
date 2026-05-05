# country_presence_verified

Determine whether a company has a real, sellable presence in its verified country — distinguishing a legitimate legal entity / regional office from a marketing-only country-level domain.

## Status: opt-in add-on (NOT default)

This function is **opt-in**, not part of the default account-enrichment recipe. Most customers don't need territory-level verification — many sales orgs don't assign by territory at all. Roughly half do, half don't.

**Use this function when:**

- Your market mix has heavy country-level domains (.co.uk, .de, .fr, .com.au, etc.) — typical for EMEA / Europe-heavy engagements
- The your CRM has territory assignments and needs records routed to the correct rep based on geography
- Your project requirements explicitly identify geography qualification as a sales-process requirement
- You have a known false-positive problem (e.g. "our UK reps keep selling to companies that don't actually have UK staff")

**Skip this function when:**

- You don't assign by territory
- Your customer base is overwhelmingly US-domiciled with global reach (typical Series B+ SaaS)
- The cost of three additional AI calls per row exceeds the value of the geography signal
- HQ address (from `extract_hq_address`) is sufficient — many recipes only need to know "where is HQ" for routing, not "is the country-level domain real"

For customers who only need HQ address as a CRM field — use `extract_hq_address` (the default) and skip this function entirely.

## Why this exists

A `.co.uk` domain doesn't always mean the company has a real UK entity. `underarmour.co.uk` may be a marketing-only domain owned by the US parent, with zero UK staff or office. Reps in different territories try to sell the same logical company, conflict, miss the right rep, and burn pipeline. This function emits a programmatic answer so a recipe can drop wrong-geography records before classification or routing touches them.

## Two phases

| Phase | Purpose | Cost |
|---|---|---|
| 1. Resolve verified country | Waterfall: AI ccTLD inference (.co.uk → GB) → caller-supplied LinkedIn country fallback (`linkedin_country` input). | One AI call (~$0.001, gpt-5-mini). The country-name → ISO-code conversion is a deterministic JS map, not an AI call (Clay used AI here; we replaced for cost). |
| 2. Score sellable entity | Two AI calls in parallel: an "office presence" check (does the company have a real office in the verified country?) and an "entity legitimacy" score 0-100 with `realCountryEntity` boolean (does this look like a real sellable entity vs. marketing localization?). | Two AI calls (~$0.005 each, gpt-5-mini). |

Total: three AI calls per row (~$0.012) when a verified country is found. When no country can be resolved, only the ccTLD inference runs and the function emits a default-to-keep decision.

## Pipeline placement

```
normalize_domain_and_name
       ↓
verify_domain_alive (drop if !is_keepable)
       ↓
company_summary_from_website
       ↓
linkedin_url_verified
       ↓
country_presence_verified  ← here
       ↓ (drop if !is_sellable_entity_in_verified_country)
classify_via_latitude
```

This function comes AFTER `linkedin_url_verified` because it consumes the verified LinkedIn URL + cached PDL payload (locations, description) for its scoring inputs. It comes BEFORE `classify_via_latitude` because there's no point classifying a wrong-geography record.

## Inputs / outputs

See `function.yaml` for the typed contract. Three things worth highlighting at the contract level:

1. **`linkedin_full_provider_payload` is required, not optional.** The function reads location signals from the cached PDL payload that `linkedin_url_verified` already produced. Re-fetching would burn a redundant credit and the location data is already there.

2. **`company_summary` is required.** The entity-legitimacy AI prompt uses it to disambiguate marketing-only localization from a real division. Without it, the score is meaningfully less accurate.

3. **`linkedin_country` is optional.** Pass it when upstream extracted a 2-letter ISO from PDL's `data.location.country` field. When absent and the domain has no ccTLD, the function emits `verified_country_code=null` and defaults to `is_sellable_entity_in_verified_country=true` (cannot disprove what cannot be evaluated).

## Default-to-keep semantics

The function defaults to keeping the record when uncertain:

- AI step failure → outputs default to null, NOT false.
- No verified country (no ccTLD AND no `linkedin_country` input) → AI scoring skipped; `is_sellable_entity_in_verified_country` returns `true`.
- The aggregate gate is set to `false` ONLY when one of: (a) entity-legitimacy AI explicitly returned `realCountryEntity: false`, OR (b) office-presence AI explicitly returned `hasOfficeInCountry: false` AND entity-legitimacy did not explicitly say `realCountryEntity: true`.

Why err generous: false negatives (incorrectly dropping a real customer) cost a relationship; false positives (keeping a marketing-only domain through to classification) cost one downstream classification call. Caller code that wants stricter behavior should explicitly check `entity_legitimacy_score >= 70` rather than relying on the aggregate gate.

## Customer-specific layer is NOT in this function

Clay's source table also did:
- HubSpot `lookup_object` to get account owner ID
- Cross-table join to fetch the assigned territory + countries-in-territory
- AI match check against the assigned territory
- Final High/Low fit scoring (territory match × employee count threshold)

Those are CUSTOMER-SPECIFIC business rules. They live at the **recipe** level (the compiler), not the function level. The function emits the verified country + entity signals; the recipe combines those with CRM source-of-truth fields and decides what to do.

Pattern for the calling recipe (sketch):

```yaml
- uses: country_presence_verified
  inputs:
    domain_clean: {{normalize_domain_and_name.domain_clean}}
    company_name_clean: {{normalize_domain_and_name.company_name_clean}}
    company_summary: {{company_summary_from_website.summary}}
    linkedin_url: {{linkedin_url_verified.linkedin_url}}
    linkedin_full_provider_payload: {{linkedin_url_verified.full_provider_payload}}
    linkedin_country: {{linkedin_url_verified.full_provider_payload.location.country}}

# Recipe-level customer logic (HubSpot territory match, etc.)
- alias: customer_territory_check
  operation: run_javascript
  payload:
    code: |
      const verifiedCountry = row.country_presence_verified.verified_country_code;
      const territoryCountries = row.hubspot_territory.countries;
      return {
        territory_match: territoryCountries.includes(verifiedCountry)
      };
```

## v1 limitation: by-country employee count

Clay's source table called MixRank's `get-counts-by-country-for-profiles-with-mixrank` to get an exact LinkedIn employee count for the (company, country) pair. This was a major signal feeding both AI scoring prompts. **Deepline currently has no equivalent tool.**

v1 ships without this signal. The AI prompts get `linkedin_company_employees_in_location: "unknown — Deepline currently has no by-country LinkedIn headcount tool"` as a literal input, and lean more heavily on:

- LinkedIn locations array (whatever PDL exposes — typically one HQ location)
- LinkedIn company description (mentions of country-specific operations)
- The agent's own web research

A future `country_employee_count` function (parallel to `company_core_from_linkedin`) will add this signal once one of these path becomes reliable in Deepline:

- Apify HarvestAPI actor for LinkedIn employee directory + filter by location
- PDL or Crustdata adding a by-country headcount field
- A direct MixRank integration in the Deepline catalog

When that function exists, this one's contract gets a `country_employee_count` optional input, and the AI prompts pick it up automatically.

## Gotchas

- **ccTLD inference and crown dependencies.** `.gg`, `.je`, `.im`, `.gi` (Guernsey, Jersey, Isle of Man, Gibraltar) are UK crown dependencies. The prompt instructs the AI to return UK only when the domain represents a UK business presence — but a fintech using `.io` (British Indian Ocean Territory) is almost always a global tech company, not a BIOT entity. The prompt explicitly excludes `.io` from ccTLD treatment for this reason.
- **`.co` is NOT Colombia in practice.** Same for `.ai` (technically Anguilla but used universally by AI startups), `.tv` (Tuvalu but used for video), `.ly` (Libya but used for "-ly" hacks). The prompt instructs the AI to treat these as global, not country-specific.
- **Multi-segment ccTLDs.** `.co.uk` (UK), `.com.au` (Australia), `.co.jp` (Japan), `.com.br` (Brazil) are recognized as country-level. The prompt explicitly handles these.
- **Crown dependencies vs. UK proper.** The function returns the verified country as `GB` for `.co.uk`, `.uk`, AND for `.gg` / `.je` / `.im` when the AI judges the company has a UK business presence. When a customer needs to distinguish Channel Islands from UK proper, the recipe layer has to do that — this function won't.
- **AI scoring is sensitive to `company_summary` quality.** When `company_summary` came back as `"N/A"` from `company_summary_from_website` (dead site, blocked agent), the entity-legitimacy AI has degraded signal. The function still runs and emits a default-to-keep decision; recipe authors should consider gating this function on `company_summary !== "N/A"`.
- **The `linkedin_country` fallback assumes upstream populated it.** PDL's `enrich_company` returns `data.location` as an object that MAY contain a `country` field — but not always, and not always in 2-letter ISO form. Recipe authors should pre-extract a clean 2-letter code from the PDL payload before passing it.

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/country_presence_verified.workflow.json)"

# Case 1: US company with .com domain, large LinkedIn presence
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "stripe.com",
  "company_name_clean": "Stripe",
  "company_summary": "Stripe is a payments infrastructure company...",
  "linkedin_url": "https://www.linkedin.com/company/stripe",
  "linkedin_full_provider_payload": {"location": {"country": "US"}, "industry": "Financial Services", "name": "Stripe"},
  "linkedin_country": "US"
}'
# Expect: verified_country_code=US, verified_country_source=linkedin (no ccTLD on .com),
#   is_sellable_entity_in_verified_country=true, entity_legitimacy_score≥80

# Case 2: marketing-only country domain (reference example)
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "underarmour.co.uk",
  "company_name_clean": "Under Armour",
  "company_summary": "Under Armour is a US athletic apparel company...",
  "linkedin_url": "https://www.linkedin.com/company/under-armour",
  "linkedin_full_provider_payload": {"location": {"country": "US"}, "name": "Under Armour", "industry": "Sporting Goods"}
}'
# Expect: verified_country_code=GB (.co.uk → UK), verified_country_source=ccTLD,
#   is_sellable_entity_in_verified_country=false, likely_parent_company≈"Under Armour, Inc. (US parent)"

# Case 3: real regional subsidiary (.de domain, real DE presence)
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "accenture.de",
  "company_name_clean": "Accenture",
  "company_summary": "Accenture is a global professional services company...",
  "linkedin_url": "https://www.linkedin.com/company/accenture",
  "linkedin_full_provider_payload": {"location": {"country": "IE"}, "name": "Accenture", "industry": "IT Services"}
}'
# Expect: verified_country_code=DE (.de → Germany), verified_country_source=ccTLD,
#   is_sellable_entity_in_verified_country=true, entity_legitimacy_score≥70
```
