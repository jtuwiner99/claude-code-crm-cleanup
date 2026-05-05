# company_summary_from_website

Visit a company's website and produce a dense, multi-paragraph summary describing what they do, who they sell to, and how they're positioned.

## Why this exists

Almost every downstream AI step in the enrichment chain benefits from a single, consistent "what is this company" grounding paragraph. Generating it once and reusing it across:

- LinkedIn URL fuzzy-match verification (`linkedin_url_verified`)
- Company classification (SaaS / E-commerce / etc.)
- Persona / ICP segmentation
- Outbound personalization

…is much cheaper than re-summarizing in each step, and produces more consistent decisions because every downstream gate sees the same view of the company.

## When to use

Right after `normalize_domain_and_name`, before any AI step that needs to reason about the company.

## When NOT to use

- The summary already exists upstream (e.g. CRM has a "company description" field that's known to be fresh and accurate).
- You only need a single specific field that the website's structured data exposes (e.g. just the meta description) — fetch it directly with `firecrawl_scrape`, don't summon a full agent.

## Inputs / outputs

See `function.yaml`.

## Why summaries (plural) are in the contract

Clay's source table also produced two narrower sub-summaries: target-audience-only, and products-services-only. They're useful for downstream prompts that only need one slice (e.g. ICP scoring only needs target audience). Contract preserves them as nullable outputs; commands.jsonc has them commented out by default. Uncomment when a calling pipeline actually needs them — they each cost an extra cheap-AI call.

## Gotchas

- **The agent occasionally returns "N/A" verbatim** — for dead domains, blocked sites, or sites that don't describe the business (login walls, parked pages). Downstream consumers must handle the literal string `"N/A"` as a sentinel, not a real summary. The verification function in particular should treat `summary == "N/A"` as a signal to skip fuzzy-matching.
- **The default model is the agent's default (currently `openai/gpt-5.4-mini`).** This is a research-grade call with tool use (web search + bash). Cheap relative to a full Opus call, but not free. Don't invoke this function speculatively on rows you don't actually plan to enrich.
- **Sub-summary outputs are non-authoritative.** When uncommented, they are derived from a separate AI call, NOT extracted from the main `summary`. They may diverge slightly. If you need consistency between the main summary and the sub-summaries, derive the sub-summaries from the main summary in JS instead — that's a different function.

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/company_summary_from_website.workflow.json)"
deepline workflows call --workflow-id <ID> --payload '{"domain_clean":"stripe.com"}'
# Expect: summary = a 4-6 paragraph dense description of Stripe (payments
#   infrastructure, B2B+B2C, online businesses + enterprises, etc.)
```
