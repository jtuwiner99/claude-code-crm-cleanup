---
name: headcount-by-function
description: Use when the user wants to enrich accounts with the count of employees by job function (sales, RevOps, marketing, engineering, etc.) — typically as a tier-scoring or routing signal. Returns integer counts per (account × function), not lists of people. Surfaces the free purpose-built provider endpoints to use, the JSON payload shapes, the substring-matching trick that makes the title list short, and the coverage caveat to flag before the user trusts the numbers.
---

# Headcount by function — free providers, integer counts

## When to use this

The user wants to know "how many salespeople / RevOps people / engineers / etc. work at each company in this list" and they want the **integer count**, not a list of profiles. Common downstream use:

- A tier-scoring input: "Tier 1 only if ≥5 RevOps people"
- A routing signal: "if sales=0, route to inbound team"
- A demo wow: showing per-account headcount-by-role next to firmographics

If the user instead wants the *people themselves* (profiles, emails), this skill is the wrong tool — use `apollo_search_people_with_match`, `lusha_search_contacts`, or the contact-cleanup skill.

## The recommendation (validated 2026-05-05 on 50 well-known SaaS accounts)

| Tool | Cost | Best for | Caveat |
|---|---|---|---|
| **`dropleads_get_lead_count`** ⭐ | **FREE** | Primary. Sales is a built-in `departments` enum (no title list needed). Title-substring + OR for ops cohorts. | Coverage skews mid-market US; long-tail can return 0 on real companies (saw 5/50 zero rows on legit accounts in validation). |
| **`icypeas_count_people`** | **FREE** | Fallback. 700M profiles — the broadest LinkedIn-style coverage. | Title-only filtering (no department abstraction). Slightly noisier counts. |
| **`apollo_search_people`** (free preview) | **FREE** | Fallback for Apollo-rich workspaces. Returns `data.total_entries`. | Apollo's free tier obfuscates names — fine for count-only, useless if you ever want to enrich the people. |
| ~~`apollo_people_search` (paid)~~ | ~~$0.017/call~~ | Don't use for count-only — the free preview returns the same `total_entries`. | Paid endpoints make sense only when you also need the people records. |

**Prospeo doesn't have a count-by-title endpoint** — they're an email-finder + firmographic provider (`prospeo_enrich_company` returns total headcount only). Skip Prospeo for this task.

## The substring-matching trick (saves you from authoring exhaustive title lists)

Dropleads' `filters.jobTitles` is **substring-matched + OR'd**. So a 3-element seed list catches all reasonable variants:

```json
{ "filters": {
    "companyDomains": ["stripe.com"],
    "jobTitles": ["Revenue Operations", "Marketing Operations", "Sales Operations"]
} }
```

That payload catches: Revenue Operations Manager, Senior RevOps Analyst, Director of Revenue Operations, VP RevOps, Marketing Operations Manager, Sales Operations Lead, etc. — every operations-y title in one query.

For Sales specifically, use the **`departments` enum** instead of titles — it's cleaner:

```json
{ "filters": {
    "companyDomains": ["stripe.com"],
    "departments": ["Sales"]
} }
```

Dropleads' `departments` enum: `Engineering, Sales, Marketing, Operations, Finance, HR, Product, Customer Success, Legal, IT`. Note: no "Revenue Operations" department — that's why ops queries use `jobTitles` substring instead.

## Response shape

All three free providers return a similar shape. Dropleads:

```json
{ "result": {
    "data": { "success": true, "count": 167 },
    "meta": { "status": 200 }
} }
```

In a Deepline `run_javascript` verdict step, with the standard `unwrap()` helper from `recipes/default-cleanup-template.jsonc`:

```js
const salesResp = unwrap(row.sales_count) || {};
const sales_headcount = (salesResp.data && typeof salesResp.data.count === 'number')
  ? salesResp.data.count : null;
```

Apollo `apollo_search_people` returns the count at `result.data.total_entries`. Icypeas `icypeas_count_people` returns at `result.data.count` (same shape as Dropleads).

## Two ways to wire it up

### Option A — embed in the playbook (end-to-end pipeline)

Add two steps before the `verdict` step in `tmp/playbook.jsonc`. Pattern (also lives in `tools/headcount.py` as the standalone caller):

```jsonc
{
  "alias": "sales_count",
  "tool": "dropleads_get_lead_count",
  "operation": "dropleads_get_lead_count",
  "payload": {
    "filters": {
      "companyDomains": ["{{inputs.domain_clean}}"],
      "departments": ["Sales"]
    }
  }
},
{
  "alias": "revops_count",
  "tool": "dropleads_get_lead_count",
  "operation": "dropleads_get_lead_count",
  "payload": {
    "filters": {
      "companyDomains": ["{{inputs.domain_clean}}"],
      "jobTitles": ["Revenue Operations", "Marketing Operations", "Sales Operations"]
    }
  }
}
```

Then read in the verdict step (see `unwrap()` snippet above) and add `sales_headcount` + `revops_headcount` to the return object.

Use this when headcount is part of the same end-to-end run as Apollo + Harvest. Free, so no cost concern about firing it on every row.

### Option B — `tools/headcount.py` (standalone, post-hoc)

Already shipped at `tools/headcount.py`. Doesn't need the Apollo/Harvest pipeline; reads any flat CSV with a `domain` column and appends `sales_headcount` + `revops_headcount`. Use this when:

- The user already has an enriched CSV and just wants headcount appended
- You don't want to recompile the full playbook
- The full Deepline-native CSV got wiped (lost work recovery)

```bash
python3 tools/headcount.py \
  --input tmp/enriched-flat.csv \
  --output tmp/enriched-flat.csv \
  --revops-titles "Revenue Operations,Marketing Operations,Sales Operations"
```

## Coverage caveat — flag this before the user trusts the numbers

Free count endpoints return **provider DB coverage**, not ground truth. In the 2026-05-05 validation against 50 well-known SaaS accounts, Dropleads returned `0` for 5 companies that almost certainly have non-zero sales orgs in reality (Typeform, Chorus, Hotjar, 6sense, Braintree). Coverage gaps cluster on:

- Mid-market companies acquired by larger parents (data freshness lag)
- Companies with predominantly non-US sales orgs (Dropleads has a US lean)
- Niche / domain-renamed accounts

**Tier-bucketing is reliable** (rank-ordering across accounts is correct — a 4095-sales company will rank above a 102-sales company every time). **Absolute precision is not** — don't promise "exact" counts to operators.

If a session needs higher coverage on the tail, layer in `icypeas_count_people` or `apollo_search_people` as a fallback waterfall. All three are free — running 3 in parallel and taking the max is cheap insurance.

## Cost

A 50-row × 2-function run = 100 calls = **$0**. All three providers above are billed `$0/call` (`no_bill` in the tool catalog) for these specific count endpoints.

The paid Apollo `apollo_people_search` is $0.017/call — only worth using if you also need the people records (in which case you're paying for the `total_entries` as a side effect).

## Future iteration ideas (don't do unless asked)

- Department-level fan-out: Engineering / Marketing / Customer Success / Product as additional columns. Each is one more Dropleads call (free) — natural extension.
- Seniority breakdown: `seniority: ["VP", "Director"]` overlay tells you "how many *senior* salespeople" vs "any salespeople." Useful for ICP-fit when the user's target is a Director persona.
- Cross-provider waterfall in a single column: Dropleads → Icypeas → Apollo, take the max non-zero count. Mitigates the coverage tail caveat above.
- Latitude-managed prompt for ambiguous title cases (e.g. "marketing ops" people who actually do RevOps work). Out of scope for the free deterministic path.
