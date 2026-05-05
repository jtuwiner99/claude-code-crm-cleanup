# detect_company_division

Detect whether a record represents a regional or business-unit branch of the **same legal entity** — H&M UK is part of H&M Hennes & Mauritz AB, not a separately-owned subsidiary.

## Status: opt-in add-on (NOT default)

Spine-only — only injectable when `recipe.use_agency_spine: true` (the spine produces the upstream `domain_clean`, `company_name_clean`, `company_summary` outputs this function consumes).

**Use this function when:**

- Your TAM heavily features regional or BU branches of global brands — H&M UK / H&M Australia / H&M Global, Under Armour regional arms, conglomerate BUs (Microsoft Gaming / Cloud / Office), global retail or QSR chains with country-specific sites.
- Sales is territory-assigned and routing reps to "the UK arm of H&M" should automatically correlate to the global H&M parent for credit / coverage purposes.
- Customer is concerned about country-domain duplicates: `country_presence_verified` already validates that hm.co.uk is a real UK entity (vs marketing-only); this function adds the identity layer ("this record IS the UK division of H&M").

**Skip this function when:**

- Your TAM is independent operating companies.
- Geographic / BU branches don't matter to routing or qualification.
- Cost of one AI call per row outweighs the signal.

## The discriminator: same vs different legal entity

This is the central judgment call and the boundary with `detect_corporate_structure`:

| Case | Verdict | Function |
|---|---|---|
| H&M UK (hm.co.uk) — regional branch of H&M Hennes & Mauritz AB; UK staff are H&M employees | `is_division=true`, regional, scope="United Kingdom" | **detect_company_division** |
| Outback Steakhouse owned by Bloomin' Brands; Outback's staff are Outback Steakhouse, Inc. employees (separate legal entity) | NOT a division here; tagged `subsidiary` by the OTHER function | **detect_corporate_structure** |
| Microsoft Gaming — Xbox + Activision now folded in; staff are Microsoft Corporation employees | `is_division=true`, business_unit, scope="Gaming" | **detect_company_division** |
| Stripe — independent operating company | `is_division=false` (and `relationship_type=independent` in the other function) | neither |

The two functions are designed to coexist. A given row's correct answer comes from one function or the other, not both — though both can run safely (a `subsidiary` row will be `is_division=false` and vice-versa).

## Why this exists

CRMs frequently ingest regional sites as separate company records (because they have separate domains: hm.co.uk vs hm.com). Without identity tagging, sales routing treats them as unrelated companies. Common failure modes:

- Two reps prospecting H&M UK and H&M Global as if they're different accounts.
- Marketing campaigns targeting Microsoft Gaming separately from Microsoft Cloud, missing that the buying committee is shared.
- ABM teams running parallel motions on hm.com (US-targeted) and hm.co.uk (UK-targeted) without coordination.

This function emits `is_division` + `global_parent_name` + `division_scope` so HubSpot workflows can correlate divisional records to the global parent and route accordingly.

## Output (the gate)

`is_division` is the gate boolean. When true:
- `division_type` distinguishes `regional` (geographic) from `business_unit` (functional).
- `global_parent_name` + `global_parent_domain` identify the global brand.
- `division_scope` describes the branch (country for regional, BU name for business_unit).

`confidence` (0-100) is the AI's self-graded confidence. Below 50 should be treated as "uncertain — default to not-a-division".

## Default-to-not-a-division semantics

The function defaults to `is_division=false` when uncertain. Same bias rationale as `detect_corporate_structure`: false positives (tagging an independent company as a division of some other company) corrupt routing more than missing a true division.

## Cost

One AI call per row, ~$0.004 (gpt-5-mini, ~2500 tokens). Predictable.

## Pipeline placement

```
normalize_domain_and_name
       ↓
verify_domain_alive
       ↓
company_summary_from_website
       ↓
detect_company_division  ← here (opt-in)
       ↓ (recipe-defined gating)
linkedin_url_verified
       ↓ ...
```

Composable in parallel with `detect_acquisition`, `detect_corporate_structure`, and `country_presence_verified` — they answer independent questions about the same input record.

## Composes with `country_presence_verified`

The two functions are complementary:

- `country_presence_verified` answers: "is hm.co.uk a real UK-staffed entity, or marketing-only?"
- `detect_company_division` answers: "is hm.co.uk the UK arm of H&M global?"

A real UK division will be `is_sellable_entity_in_verified_country=true` AND `is_division=true, division_type=regional, scope="United Kingdom"`. A marketing-only country domain will be `is_sellable_entity_in_verified_country=false` (drop) — `detect_company_division` may still tag it as a division but the sellability gate drops it first.

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/detect_company_division.workflow.json)"

# Case 1: classic regional division (H&M UK)
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "hm.co.uk",
  "company_name_clean": "H&M",
  "company_summary": "H&M is a Swedish multinational fashion retailer; this is the UK regional site with UK-specific stock and shipping."
}'
# Expect: is_division=true, division_type=regional, global_parent_name="H&M",
#   global_parent_domain="hm.com", division_scope="United Kingdom", confidence>=80

# Case 2: business-unit division
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "xbox.com",
  "company_name_clean": "Xbox",
  "company_summary": "Xbox is the gaming brand owned by Microsoft, now part of Microsoft Gaming."
}'
# Expect: is_division=true, division_type=business_unit, global_parent_name="Microsoft",
#   division_scope="Gaming"

# Case 3: NOT a division — separate legal entity (subsidiary case)
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "outback.com",
  "company_name_clean": "Outback Steakhouse",
  "company_summary": "Outback Steakhouse is a casual-dining steakhouse chain..."
}'
# Expect: is_division=false (Outback is a separate legal entity owned by
#   Bloomin' Brands; detect_corporate_structure handles that case.)

# Case 4: independent global company
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "stripe.com",
  "company_name_clean": "Stripe",
  "company_summary": "Stripe is a payments infrastructure company..."
}'
# Expect: is_division=false, global_parent_name=null, confidence>=80
```

## Pointers

- M&A and Corporate Structure Playbook: `the M&A and Corporate Structure Playbook`
- Composes with: `detect_corporate_structure` (parent-child across legal entities), `detect_acquisition` (M&A events), `country_presence_verified` (validates regional records are real).
- Catalog: `the enrichment-functions catalog`
