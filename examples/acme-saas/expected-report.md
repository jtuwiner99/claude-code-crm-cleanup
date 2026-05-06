# CRM cleanup — Acme SaaS
*Run completed 2026-05-05 20:58 — 30 accounts*

## What we measured

- **industry** — Industry classification. One of: B2B SaaS, FinTech, E-commerce, Services, Hardware, Other. Pick the closest match based on what the compa…
- **employee_count_tier** — Approximate company size bucket: "1-50", "51-500", or "501+". Use LinkedIn employee count when available; fall back to web research (Crun…
- **is_acquired** — Has this company been acquired by or merged into a structurally different parent company? Default to false on weak evidence — this is a h…
- **acquirer_name** — When is_acquired=true, the parent company's primary brand name. Empty string when is_acquired=false.
- **pitch** — One sentence describing what the company sells. Plain English, ≤25 words. Skip marketing fluff ("revolutionary", "best-in-class") — focus…
- **reasoning** — 1–2 sentences citing specific evidence behind the most surprising verdict on this row (e.g. "is_acquired=true because Salesforce acquired…

## Top findings

### 9 acquired companies — reroute to acquirer

Sales motion should target the parent. The on-record domain is no longer the buying entity.

| On record | Acquired by | Domain |
|---|---|---|
| Braintree | PayPal | braintree.com |
| Chorus | ZoomInfo | chorus.ai |
| Clearbit | HubSpot | clearbit.com |
| GitHub | Microsoft | github.com |
| LinkedIn | Microsoft | linkedin.com |
| Loom | Atlassian | loom.com |
| Mailchimp | Intuit | mailchimp.com |
| Segment | Twilio | segment.com |
| Slack Technologies | Salesforce | slack.com |

### industry distribution

| industry | count | % |
|---|---|---|
| B2B SaaS | 22 | 73% |
| Other | 3 | 10% |
| FinTech | 2 | 7% |
| Services | 2 | 7% |
| E-commerce | 1 | 3% |

## Sample rows

| company | industry | employee_count_tier | is_acquired | acquirer_name | pitch |
|---|---|---|---|---|---|
| Slack Technologies | B2B SaaS | 501+ | true | Salesforce | Channel-based business messaging platform. |
| Mailchimp | B2B SaaS | 501+ | true | Intuit | Email marketing and marketing automation platform. |
| Clearbit | B2B SaaS | 51-500 | true | HubSpot | B2B data enrichment and identification for sales and market… |
| Segment | B2B SaaS | 501+ | true | Twilio | Customer data platform for collecting unifying and routing … |
| Stripe | FinTech | 501+ | false |  | Online payment processing infrastructure for internet busin… |

## Next steps

- **Reroute 9 acquired-company accounts** to their acquirers before the next QBR.
- Review the per-row enriched output at `tmp/enriched-flat.csv` and write back to your CRM.

