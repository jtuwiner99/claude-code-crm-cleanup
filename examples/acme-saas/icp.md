# Acme SaaS — ICP & tier rubric

*Fictional client. Imagine Acme sells a sales-analytics platform to B2B SaaS revenue teams.*

## Who Acme sells to

**Best-fit:** US-headquartered B2B SaaS companies with 500+ employees that are still operating independently (not absorbed by a larger acquirer). Why this shape:

- B2B SaaS — Acme's product is built around B2B sales motion patterns. Consumer / E-commerce / Hardware sales motions don't map.
- 500+ employees — below this, prospects don't usually have a dedicated RevOps function (Acme's economic buyer).
- US-HQ — Acme's onboarding team only supports US time zones in v1; international expansion is roadmapped.
- Independent — acquired companies route their tooling decisions to the parent. If Slack is owned by Salesforce, the buyer is Salesforce, not Slack.

## Tier rubric

| Tier | Definition | What sales does |
|---|---|---|
| **1 — Ideal** | B2B SaaS, 501+ employees, US-HQ, independent | Multi-touch outbound sequence + AE assignment within 24h |
| **2 — Acceptable** | B2B SaaS 51–500 (US, independent), OR FinTech 501+ (US, independent) | Single-touch nurture; promote to Tier 1 if they hit 500 employees |
| **3 — Stretch** | International B2B SaaS 501+, OR US E-commerce/Services 501+ | Quarterly newsletter only; no AE time |
| **Drop** | Acquired (route to acquirer instead), dead domain, < 50 employees, or non-target industry | Remove from active outreach |

## Scoping decisions Acme made (and why)

**Why "501+" not "200+":** Acme initially tested 200+ as the threshold. The under-500 segment converted at 1/4 the rate of 500+ and required 2x the AE touches per closed deal. Cleaner cutoff at 500.

**Why "is_acquired" matters more than relationship_type:** A subsidiary (e.g. GitHub under Microsoft) often retains independent procurement authority, so it's still routable. A fully acquired/integrated company (e.g. Mailchimp under Intuit) doesn't — buying decisions roll up to the parent's tech stack. Acme treats "acquired" as a hard drop signal; "subsidiary" as a verify-routing flag.

**Why "FinTech" gets a Tier 2 lane:** Acme has a small but profitable wedge among FinTech SaaS companies (Stripe-adjacent infrastructure plays). Worth keeping warm even if not the primary motion.

**What we deliberately ignored:** funding stage, recent hiring momentum, technographic fit (CRM platform, marketing automation stack). These were cut from v1 to keep the cleanup tight; they're roadmap candidates if the v1 motion plateaus.

## Properties Acme wants enriched

| Property | Why |
|---|---|
| `industry` | Filter to B2B SaaS, FinTech as Tier 2 lane |
| `employee_count_tier` | The 500+ vs 51–500 split is the single biggest tier signal |
| `is_acquired` | Hard drop / reroute signal — biggest source of wasted AE time |
| `acquirer_name` | When acquired, who to reroute to |
| `pitch` | One-sentence "what they sell" — feeds AE personalization at outreach time |
| `reasoning` | Per-row evidence trail for QA + stakeholder trust |

That's the whole list. Acme deliberately cut other properties they considered (`hq_country`, `funding_stage`, `tech_stack`) to keep v1 fast — see `how-this-was-built.md` for the conversation behind those cuts.
