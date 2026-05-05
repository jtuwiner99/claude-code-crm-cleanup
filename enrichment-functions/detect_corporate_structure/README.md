# detect_corporate_structure

Detect durable parent-child relationships across **different legal entities** — independent of any acquisition event. Distinct from `detect_acquisition` (which detects M&A *events*) and from `detect_company_division` (which detects same-legal-entity regional/BU branches).

## Status: opt-in add-on (NOT default)

Spine-only — only injectable when `recipe.use_agency_spine: true` (the spine produces the upstream `domain_clean`, `company_name_clean`, `company_summary` outputs this function consumes).

**Use this function when:**

- Your TAM heavily features parent-child relationships across distinct legal entities — restaurant brand portfolios (Outback / Bloomin' Brands), franchise chains, family-owned restaurant groups (a holding LLC owns 5–10 brands), conglomerate portfolios (Berkshire Hathaway companies), aviation portfolios.
- Scoping flagged duplicate parent/child records as a CRM-quality problem — but the duplicates aren't from M&A events; they're from the team ingesting both the parent and several subsidiaries as separate records.
- ABM motion where routing reps to multiple subsidiaries of the same parent wastes pipeline.

**Skip this function when:**

- Your TAM is independent operating companies (most B2B SaaS).
- Subsidiary structure isn't relevant to routing or qualification.
- M&A events are the only parent-child relationships you care about — use `detect_acquisition` alone.

## Why this exists

Three CRM failure modes that the default recipe + `detect_acquisition` don't catch:

1. **Subsidiary that was never acquired** (always-owned). Lays was created by Frito-Lay; never had a separate independent existence. `detect_acquisition` returns `is_acquired: false` because there's no event. But Lays IS a subsidiary of Frito-Lay (which itself is a subsidiary of PepsiCo). CRM routing for "Lays" should know about the parent chain.

2. **Restaurant brand portfolios.** A holding LLC ("Smith Restaurant Group, Inc.") owns 5-10 family restaurants — beyond just one family business but under one parent entity. Each restaurant is its own brand and may have its own domain. The CRM needs to tag each restaurant as a subsidiary of the holding LLC for accurate sales coverage.

3. **Franchise / corporate-parent structures.** Many franchises operate as their own legal entity but roll up to a master franchisor. Recognizing the structure helps avoid double-prospecting parent + franchisee.

This function emits the structural signal so the calling recipe can route accordingly.

## What this function does NOT cover

- **M&A events.** `detect_acquisition` does that. A subsidiary created via acquisition will be tagged `subsidiary` HERE *and* `is_acquired=true` THERE — both signals coexist.
- **Same-legal-entity divisions.** H&M UK is part of H&M Hennes & Mauritz AB (one legal entity, regional branch) — that's `detect_company_division`'s scope. This function returns `independent` for H&M UK.
- **DBA / rebrand.** ClickUp dba Mango Technologies is ONE legal entity with two names — `independent` here.

## Output (the gate)

`relationship_type` is the gate enum: `independent` | `parent` | `subsidiary`. Recipe authors who want to drop subsidiaries from downstream enrichment (and let CRM logic merge them into parents) should gate on `relationship_type !== 'subsidiary'`. Recipe authors who want to do the opposite (only enrich subsidiaries — e.g. consumer brands targeting end-customer-facing brands) should gate on `relationship_type === 'subsidiary'`.

When `relationship_type=subsidiary`: `parent_name` + `parent_domain` are populated for HubSpot parent-record correlation.

When `relationship_type=parent`: `known_subsidiaries` is an array of 3-7 most-notable owned brands (best-effort). Null when too many to enumerate cleanly (Berkshire-style conglomerates).

## Default-to-independent semantics

The function defaults to `independent` when uncertain:

- AI step failure → `relationship_type=null`, all subsidiary fields null. Caller distinguishes null ("not checked") from explicit `independent`.
- AI uncertain but emits a verdict → that verdict is honored, but `confidence < 50` is a signal to recipe authors that the answer is shaky.

False positives (incorrectly tagging an independent company as subsidiary) corrupt CRM routing more than missing a true subsidiary — hence the bias.

## Cost

One AI call per row, ~$0.005 (gpt-5-mini, ~3000 tokens for system prompt + grounding summary + structured output). Predictable.

## Pipeline placement

```
normalize_domain_and_name
       ↓
verify_domain_alive (drop if !is_keepable)
       ↓
company_summary_from_website
       ↓
detect_corporate_structure  ← here (opt-in)
       ↓ (recipe-defined gating)
linkedin_url_verified
       ↓ ...
```

Composable in parallel with `detect_acquisition` and `detect_company_division` — they answer independent questions about the same input record.

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/detect_corporate_structure.workflow.json)"

# Case 1: classic restaurant portfolio subsidiary
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "outback.com",
  "company_name_clean": "Outback Steakhouse",
  "company_summary": "Outback Steakhouse is a casual-dining steakhouse chain founded in 1988..."
}'
# Expect: relationship_type=subsidiary, parent_name="Bloomin'\'' Brands",
#   parent_domain="bloominbrands.com", confidence>=80

# Case 2: conglomerate parent
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "bloominbrands.com",
  "company_name_clean": "Bloomin'\'' Brands",
  "company_summary": "Bloomin'\'' Brands is a US restaurant holding company that owns multiple casual-dining brands..."
}'
# Expect: relationship_type=parent, known_subsidiaries containing
#   "Outback Steakhouse", "Carrabba'\''s", "Bonefish Grill", confidence>=80

# Case 3: independent (most B2B SaaS)
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "stripe.com",
  "company_name_clean": "Stripe",
  "company_summary": "Stripe is a payments infrastructure company..."
}'
# Expect: relationship_type=independent, parent_name=null, confidence>=70

# Case 4: regional branch — should be independent (different function handles divisions)
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "hm.co.uk",
  "company_name_clean": "H&M",
  "company_summary": "H&M is a Swedish multinational fashion retailer; hm.co.uk is the UK regional site."
}'
# Expect: relationship_type=independent (same legal entity as H&M global —
#   detect_company_division would tag this differently; not this function'\''s scope)
```

## Pointers

- M&A and Corporate Structure Playbook: `the M&A and Corporate Structure Playbook`
- Composes with: `detect_acquisition` (M&A events), `detect_company_division` (same-entity branches)
- Catalog: `the enrichment-functions catalog`
