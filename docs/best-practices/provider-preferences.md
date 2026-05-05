# Provider Preferences — House Defaults

Property → Deepline primitive mapping a scope compiler uses when the user hasn't specified an explicit preference. Sort order within each row = waterfall order (first in list = primary, later = fallback).

| Property / capability | Primary | Fallback chain |
|---|---|---|
| Company firmographic (industry, employees, founded, funding, HQ, tech stack) | `apify_run_actor_sync` w/ `harvestapi/linkedin-company` actor | `apollo_enrich_company` → `peopledatalabs_company_search` → `crustdata_company_search` |
| LinkedIn URL discovery | returned by Harvest as the URL it scraped; Apollo/PDL/Crustdata return it on fallback | — |
| LinkedIn profile content | live scrape via `harvestapi/linkedin-company` (primary in `company_core` waterfall) | — |
| Company summary (narrative) | `deeplineagent` with JSON schema, fed Harvest's LinkedIn `description` + a Firecrawl pull of the homepage | — |
| Company identity verification (LinkedIn matches input) | deterministic: trim(`company_core.website`) === `domain_clean` (Harvest returns LinkedIn-direct website) | `deeplineagent` fuzzy-match: LinkedIn description vs AI-summarized homepage |
| HQ address | extract from `company_core.headquarters` (Harvest pulls this directly off LinkedIn) | `deeplineagent` web search fallback |
| Decision makers by role | `company_to_contact_by_role_waterfall` | — |
| Work email for a contact | `name_and_domain_to_email_waterfall` | — |
| Personal email for a contact | Fullenrich via Deepline integration | — |
| Classification (any enum property) | `deeplineagent` reading classification library, OR Latitude gateway for prompt-versioned classification | — |
| Domain validation | `run_javascript` normalization + implicit 404 from `apollo_enrich_company` | — |

## Why Harvest is primary

HarvestAPI (via Apify's `harvestapi/linkedin-company` actor) returns LinkedIn-direct firmographics (employee_count, website, HQ, industries, founded year, description) which double as the ground-truth source for identity verification (LinkedIn-claimed website === input domain). Apollo/PDL/Crustdata remain in the waterfall as fallbacks for cases where Harvest can't resolve the LinkedIn URL from the input domain alone.

**Why we changed our mind on Harvest (real numbers).** A prior version of this doc said "never Harvest" — that turned out to be wrong. The validation runs that flipped it:

- **Headcount staleness.** On `sydecar.io`, Apollo reported `estimated_num_employees: 98`. Harvest reported `employeeCount: 84` for the same domain on the same day. That's a 14-employee delta — a >14% miss on the field that drives a `qualification_pre` ≥50-employees gate. Some prospects sit on the fence of that gate; getting it wrong sends real spend to the wrong rows.
- **Identity verification.** Apollo's `apollo_enrich_company` reports `missed`/`no_match` even on cleanly-resolved orgs, making the `missed` step status useless as a "did Apollo find the right company" signal. PDL/Crustdata don't return a description usable for identity-verification fuzzy matching either. Harvest returns the LinkedIn-direct website + description, which double as the ground-truth source for the deterministic + fuzzy verification chain.
- **Institutional knowledge.** Harvest needs real-world handling for URL-encoding Apollo's malformed LinkedIn slugs, falling back from `headquarter` to `locations[]` when Harvest returns null HQ, and stripping UTM tracking params from website fields. Encode this once in your extractor module; don't rediscover it.

## BYOK note

All providers above assume workspace-scoped Bring-Your-Own-Key in Deepline. If you need to override per-project, use a project-specific recipe override.

## Open extensions

- **YAML source of truth.** Currently prose; consider adding `provider-preferences.yaml` for the compiler to parse, with this doc as a rendered view.
- **Cost tiers per primitive.** Document typical credit cost for each to help compile budget estimates.
- **Per-vertical provider preference overrides.** E.g. Fintech customers may prefer Crustdata over Apollo for industry codes.
