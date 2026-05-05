---
name: ma-and-corporate-structure-playbook
description: Use this skill when scoping or building a enrichment project that involves M&A detection, parent-child relationships, or corporate-structure CRM cleanup. Covers the three-state model (independent / absorbed / division-or-subsidiary), worked examples, when to enable the M&A / corporate-structure / company-division toggles for a customer, recipe composition with the default account-enrichment spine, and what's deferred. Pairs with `detect_acquisition`, `acquired_brand_status`, `detect_corporate_structure`, `detect_company_division` — the four shipped enrichment functions covering this concept cluster.
---

# M&A and corporate-structure playbook

The operational guide for handling acquired companies, parent-child relationships, and brand portfolios in customer CRMs. Covers when to turn the M&A toggle on for a customer, how the three-state model works, and how the relevant enrichment functions compose with the default spine.

## When to invoke this skill

- A you notice "duplicate parent/child records", "we keep prospecting into companies that don't exist anymore", or "our CRM has a lot of acquired brands".
- A your TAM is in an M&A-heavy vertical: PE-backed targeting, strategic-buyer-driven categories, mature SaaS where consolidation is active, financial-services / insurance roll-ups.
- An ABM motion where routing a rep to a parent-record duplicate is a deal-breaker.
- A customer raises subsidiary / division relationships specifically (Delta-style aviation, brand portfolios like Lays under Frito-Lay under PepsiCo).
- You're about to scaffold a new enrichment function for "parent company detection" — read this skill first; the M&A piece is already covered by `detect_acquisition` + `acquired_brand_status`.
- Recipe-composition work where the M&A toggle has been turned on and you need to chain the two functions correctly.

## Why M&A detection is opt-in, not default

Most customers don't need M&A signals. Their TAM is independent operating companies and the cost of two AI calls per row outweighs the signal. The default account-enrichment recipe (`normalize_domain_and_name` → `verify_domain_alive` → `company_summary_from_website` → `linkedin_url_verified` → `extract_hq_address` → `classify_via_latitude`) treats every domain as an independent entity.

The M&A toggle exists for the users where this default is wrong: PE portfolios, consolidation-heavy categories, ABM where a parent-record duplicate breaks routing. Off by default, on per customer when scoping flags it.

## The three-state model

For any acquired company, exactly one of these states applies:

| State | What it means | Signals | CRM behavior |
|---|---|---|---|
| **independent** | Acquired but still operating standalone. Own domain live, own homepage marketing, own employees / LinkedIn page, own brand identity. The acquisition shows up as a press release banner or a footnote, NOT as the dominant homepage message. | Homepage hero pitches the original product. Employees still on `@<acquired-co>.com` emails or tagged with the acquired team. Domain doesn't redirect to acquirer. | Tag as child of the acquirer in CRM. Keep enriching and prospecting. |
| **absorbed** | Acquired and fully merged into the acquirer. Brand dissolved. Domain redirects to acquirer or homepage hero is "we're now part of X / X has joined Y". All employees migrated to acquirer's emails. | Domain 301s to acquirer's site. Homepage primarily pushes visitors to the acquirer. LinkedIn page archived or marked acquired. | Dedupe or merge into the parent record. Route to acquirer's owner. Don't prospect into the acquired brand. |
| **inactive** | Domain offline, registrar-suspended, server error, or holding page. The brand is no longer reachable in any meaningful way. | `verify_domain_alive` returns `is_live=false` or AI parking-page detector fires. | Drop the record or flag as stale. |

Two more states — **subsidiary** (different legal entity, owned by a parent — handled by `detect_corporate_structure`) and **division** (same legal entity, regional or business-unit branch — handled by `detect_company_division`) — cover parent-child relationships that don't involve an acquisition event. Both are separate opt-in toggles in the recipe.

## Worked examples

### Clearbit (acquired by HubSpot, 2023) — absorbed

Sequence:
- `detect_acquisition` returns `is_acquired=true`, `acquirer_name="HubSpot"`, `acquirer_domain="hubspot.com"`, `is_dba_rebrand=false`.
- `verify_domain_alive` shows `is_live=true`, `final_url="https://www.hubspot.com/products/breeze-intelligence"` (clearbit.com 301-redirects to HubSpot's product page).
- `acquired_brand_status` deterministic short-circuit fires on `redirected_to_parent=true` → `status="absorbed"`. No AI call needed.

CRM action: dedupe the Clearbit record into the HubSpot record. Don't route a rep to "Clearbit" — there's no Clearbit anymore.

### Slack (acquired by Salesforce, 2021) — independent

Sequence:
- `detect_acquisition` returns `is_acquired=true`, `acquirer_name="Salesforce"`, `acquirer_domain="salesforce.com"`, `is_dba_rebrand=false`.
- `verify_domain_alive` shows `is_live=true`, `final_url="https://slack.com/"` (no redirect).
- `acquired_brand_status` AI judgment runs (deterministic short-circuits don't fire). Homepage is still pitching Slack as a product → `status="independent"`.

CRM action: tag the Slack record as a child of Salesforce. Keep prospecting into Slack — they have their own decision-makers.

### ClickUp (NOT acquired — DBA / rebrand) — handled by detect_acquisition

ClickUp is the brand; Mango Technologies is the legal entity. Naive M&A detection would flag this as acquired. The detection prompt has explicit DBA-vs-acquisition logic:

- `detect_acquisition` returns `is_acquired=false`, `is_dba_rebrand=true`, `canonical_company_name="ClickUp"`, `canonical_company_domain="clickup.com"`.
- `acquired_brand_status` does NOT run (gated on `is_acquired=true`).

CRM action: keep ClickUp as an independent record. The DBA flag stays in the audit trail for human review if anyone questions it.

## When to enable the M&A toggle for a customer

Strong signals:

- Customer scoping flags duplicate parent/child records as a CRM-quality problem.
- TAM is in a roll-up category: SaaS PE portfolios, regional MSPs, dental / vet practice acquirers, payment processing consolidators.
- Customer is ABM and discovered they were routing reps to dead brands.
- Customer has explicit business rules around acquired-company handling ("drop", "tag-as-child", "route-to-parent's-owner").

Weak signals (don't enable):

- "We have a few acquired companies in the CRM" — every CRM does. Use the default and let the user flag specific records for manual review.
- Customer has no territory or routing assignments — duplicate records aren't a routing problem.
- Your TAM is M&A-light (e.g. early-stage SaaS, services firms).

When in doubt: the default recipe runs without the M&A toggle. Adding it later costs ~$0.008/row of additional AI spend; not adding it costs nothing. Bias toward leaving it off.

## Recipe composition

When the toggle is on, the two functions slot in like this:

```yaml
# Default account-enrichment spine (always-on)
- uses: normalize_domain_and_name
- uses: verify_domain_alive
  gate: "{{verify_domain_alive.is_keepable}}"
- uses: company_summary_from_website

# M&A toggle on
- uses: detect_acquisition
  inputs:
    domain_clean:        "{{normalize_domain_and_name.domain_clean}}"
    company_name_clean:  "{{normalize_domain_and_name.company_name_clean}}"
    company_summary:     "{{company_summary_from_website.summary}}"

- uses: acquired_brand_status
  run_if_js: "row.detect_acquisition.is_acquired === true"
  inputs:
    domain_clean:                    "{{normalize_domain_and_name.domain_clean}}"
    acquirer_domain:                 "{{detect_acquisition.acquirer_domain}}"
    verify_domain_alive_output:      "{{verify_domain_alive}}"

# Continue spine
- uses: linkedin_url_verified
- uses: extract_hq_address
- uses: classify_via_latitude
```

### Pattern A — M&A-aware default (most M&A customers)

`detect_acquisition` and `acquired_brand_status` annotate every row with M&A signals. The recipe doesn't drop or skip — it just enriches. CRM-side logic (recipe-level, NOT function-level) decides what to do with the signals.

### Pattern B — M&A-strict (ABM motions where parent-record duplicates are a deal-breaker)

Same composition, but `classify_via_latitude` and any downstream provider waterfalls are gated:

```yaml
- uses: classify_via_latitude
  run_if_js: "row.acquired_brand_status === undefined || row.acquired_brand_status.status === 'independent'"
```

`acquired_brand_status === undefined` covers the non-acquired branch (function didn't run because `detect_acquisition.is_acquired=false`). Independent acquired brands continue through enrichment; absorbed and inactive brands stop.

## Decision criteria — absorbed vs. independent

Used by the AI judgment step in `acquired_brand_status`. Verbatim from the original Clay-table guidance:

- **Independent (default)** — any of:
  - Homepage hero pitches the original product as a standalone offering.
  - Acquisition mention is a press release banner / footer / small section, not the dominant homepage message.
  - Brand still has its own employees, social presence, customer marketing.
- **Absorbed** — REQUIRES strong evidence:
  - Homepage hero text is "we're now part of X" / "X has joined Y" / "visit Y to learn more".
  - Acquired product is no longer being marketed as standalone.
  - Visitors are explicitly pushed to the acquirer.
- **Inactive**:
  - Domain offline, registrar holding page, server error.
  - Caught upstream by `verify_domain_alive` in most cases.

Bias rule: bias toward **independent** unless >90% confident in absorption. False negatives (incorrectly marking absorbed as independent) cost a duplicate-enrichment downstream; false positives (incorrectly dropping a still-operating brand) cost a relationship.

## The four toggles in this concept cluster

### `m_and_a` (point-in-time acquisition events)

Pair of functions: `detect_acquisition` + `acquired_brand_status`. Detects whether an acquisition event happened AND the post-event status (independent / absorbed / inactive). See "Worked examples" above.

### `corporate_structure` (parent-child across DIFFERENT legal entities)

Function: `detect_corporate_structure`. Detects durable parent-child ownership relationships across distinct legal entities, regardless of whether an acquisition event ever occurred.

Worked examples:

- **Restaurant brand portfolios.** Outback Steakhouse owned by Bloomin' Brands; Bloomin' is the holding entity (a separate legal entity from Outback Steakhouse, Inc.). Same shape: Lays under Frito-Lay under PepsiCo; Long John Silver's under Yum! Brands.
- **Family-owned restaurant groups.** A holding LLC ("Smith Restaurant Group, Inc.") owns 5–10 family restaurants — each its own brand entity, the holding LLC is the parent.
- **Franchise / corporate-parent structures.** Many franchises operate as their own legal entity but roll up to a master franchisor.
- **Conglomerate portfolios.** Berkshire Hathaway owns Geico, Dairy Queen, See's Candies as separate legal entities.

Output: `relationship_type` (independent | parent | subsidiary), `parent_name`, `parent_domain`, `known_subsidiaries`. Default-to-independent on uncertainty.

Strict-mode gate drops subsidiaries before classification (you route to parent records instead).

### `company_division` (regional / BU branches of the SAME legal entity)

Function: `detect_company_division`. Detects regional or business-unit branches of the same legal entity — H&M UK staff are H&M Hennes & Mauritz AB employees, just located in the UK.

The discriminator from `corporate_structure`: SAME LEGAL ENTITY.

Worked examples:

- **Geographic divisions.** H&M UK / H&M Australia / H&M Global. Under Armour regional arms. Nike's country sites with country-specific staff but on the parent's payroll.
- **Business-unit divisions of conglomerates.** Microsoft's Gaming division (Xbox + Activision now folded in), Microsoft's Cloud and AI, Microsoft's Office Productivity. Same Microsoft Corporation, different BUs.
- **Country-domain regional sites that ARE real branches.** hm.co.uk is a real UK arm with UK staff. (Compose with `country_presence_verified` to filter out marketing-only country domains.)

Output: `is_division`, `division_type` (regional | business_unit), `global_parent_name`, `global_parent_domain`, `division_scope` (e.g. "United Kingdom", "Gaming"). Default-to-not-a-division on uncertainty.

Strict-mode gate drops divisional records (you route to global parent record instead).

### Composition (when ALL FOUR are enabled)

The four toggles are independent — a row can be tagged by any combination:

- `is_acquired=true` (M&A event) + `relationship_type=subsidiary` — both fire when acquisition created a subsidiary.
- `is_acquired=false` + `relationship_type=subsidiary` — subsidiary that was always-owned (Lays under Frito-Lay).
- `is_division=true` (regional / BU branch) — the input is part of the SAME legal entity. `relationship_type` will typically be `independent` here (the input legal entity stands alone; it's just got branches).
- All four `false`/`independent` — pure independent operating company.

Recipe authors gate downstream enrichment on the desired combination. Common patterns:

- **M&A-strict + corporate-strict + division-strict**: only enrich pure independent records. Subsidiaries, divisions, and absorbed brands all drop. Operator handles parent-record enrichment in a separate recipe.
- **M&A-strict + everything else aware**: drop absorbed brands, but keep subsidiaries and divisions enriched-with-tags so CRM logic can correlate.
- **All aware**: annotate every row with all four signals, let CRM-side workflows decide. Most flexible, no records dropped at the spine level.

## Where to read more

- `enrichment-functions/detect_acquisition/README.md` — function-level engineer docs.
- `enrichment-functions/acquired_brand_status/README.md` — same.
- `enrichment-functions/detect_corporate_structure/README.md` — same.
- `enrichment-functions/detect_company_division/README.md` — same.
- [`enrichment-functions-catalog`](../enrichment-functions-catalog/SKILL.md) — opt-in add-ons table, decision tree, compose patterns.
