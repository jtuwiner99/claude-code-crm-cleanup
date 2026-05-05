# verify_domain_alive

Cheap, two-layer domain liveness check. Runs early in the pipeline so dead domains don't burn provider/AI credits downstream.

## Why this exists

Every CSV import or CRM dump has 5-25% domains that are dead, parked, or registrar-holding-page placeholders. Running the full enrichment chain on those rows wastes credits — at scale this is the single biggest source of avoidable cost. This function is the gate.

## Two layers, two costs

| Layer | What it catches | Cost |
|---|---|---|
| 1. HTTP status check | Domain doesn't resolve, server unreachable, 4xx, 5xx, connection timeout | **Free** — `generic_http_request` to your own domain. No third-party paid call. |
| 2. AI parking-page detector | Domain loads but renders a GoDaddy holding page, blank lander, registrar placeholder | One cheap-AI call (~$0.002, gpt-5-mini default per agency policy) — only on layer-1 survivors |

The Clay version of this function paid APIVoid for layer 1. We replicated it free with `generic_http_request`. Layer 2 is new — APIVoid catches *deindexed* URLs but not "domain loaded but it's a parking page" — so the AI step extends the check rather than just substituting.

## Output: one decision, full audit

The caller reads `is_keepable` (boolean) — that's the single gate. Everything else is for debugging:

- `is_live` — did layer 1 pass?
- `is_real_business` — did layer 2 pass? (null if skipped or not run)
- `http_status_code`, `final_url` — layer 1 raw output
- `ai_reasoning` — layer 2's 1-2 sentence justification
- `verification_signals` — full audit trail with run / error info per layer

## Default-to-keep semantics

When layer 2 fails to produce a verdict (model error, parse failure, network issue on the agent side), `is_real_business` is **null**, NOT false. The aggregate `is_keepable` then defaults to `is_live` — i.e. we keep the domain. This is intentional:

- **False positive** (keeping a parking page) costs you one downstream enrichment call's worth of wasted credits.
- **False negative** (removing a legitimate small-business domain) costs you a customer relationship.

Caller code that wants stricter behavior (e.g. "only keep verified-real businesses") should explicitly check `is_real_business === true`, not rely on `is_keepable`.

## When to use

After `normalize_domain_and_name`, before everything else. Specifically:

```
normalize_domain_and_name
       ↓
verify_domain_alive   ← gates the rest
       ↓ (only if is_keepable=true)
company_summary_from_website
linkedin_url_verified
classify_via_latitude
...
```

## When NOT to use

- The domain has already been validated upstream (e.g. CRM with active inbound traffic — they're definitionally live).
- You're enriching a single high-value row where the cost of one wasted enrichment chain doesn't matter (e.g. a single hand-curated demo lookup).
- Layer 1 alone is enough for the use case (set `skip_ai_verification=true` to skip layer 2 — saves AI cost when the deterministic check is sufficient).

## Inputs / outputs

See `function.yaml`.

## Configuration knobs

- **`http_timeout_ms`** (default 10s) — upper bound on the HTTP ping. Most live sites respond in <2s; legitimate slow sites in <8s. Anything over 10s is functionally dead for downstream purposes anyway.
- **`accepted_status_codes`** (default 200-308) — what counts as "live". Customers with stricter requirements (e.g. only 200, no redirects) override at the recipe level.
- **`skip_ai_verification`** (default false) — skip layer 2 when running cost-sensitive bulk operations.
- **`ai_verification_model`** (default `openai/gpt-5-mini`, the default as of 2026-05-01) — bump up if your domain mix has lots of edge cases (rare).

## Gotchas

- **Variant order is fixed.** The four-variant chain always tries https-bare → http-bare → https-www → http-www in that order. If a domain lives only on `http://www.<bare>` (rare in 2026 but real for legacy small businesses), three calls will fail before the fourth succeeds — that's by design. The cost is one extra burst of failed requests on a small minority of rows, vs. the alternative of always running all four in parallel (4x the HTTP calls per row at scale).
- **CDN / WAF false negatives.** Cloudflare, AWS WAF, and similar may serve a 403 to non-browser User-Agents. Function sets `User-Agent: ClaudeCodeCRMCleanup/1.0` — if your mix has heavy CDN-protected sites and you see legitimate domains marked dead across all four variants, override the User-Agent at the recipe level to a browser string.
- **AI may not actually fetch.** The `deeplineagent` invocation gives the URL and tells the agent to fetch the page. Whether it actually does so is dependent on the agent runtime's web tools. If the agent returns `unverified — could not fetch` reasoning, that's the documented fallback (default-to-keep). Watch for a high rate of this in production — if it happens >5% of the time, swap to a `firecrawl_scrape` pre-fetch step that hands content into the agent.
- **AI on highly-localized non-English sites.** gpt-5-mini can mis-judge non-English parking pages occasionally. For customers whose mix is heavily international, audit a sample of `is_real_business=false` decisions before fully trusting the gate.
- **Default model is gpt-5-mini** as of 2026-05-01. This is the default cheap-AI model, replacing prior gpt-4o-mini default. Override per-recipe via `ai_verification_model` if a specific customer needs something else.

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/verify_domain_alive.workflow.json)"

# Live legitimate domain
deepline workflows call --workflow-id <ID> --payload '{"domain_clean":"stripe.com"}'
# Expect: is_live=true, is_real_business=true, is_keepable=true, http_status_code=200

# Dead domain (DNS fails)
deepline workflows call --workflow-id <ID> --payload '{"domain_clean":"this-domain-definitely-does-not-exist-123456.com"}'
# Expect: is_live=false, is_real_business=null, is_keepable=false

# Parked domain (loads but is a holding page) — find one in your test set
deepline workflows call --workflow-id <ID> --payload '{"domain_clean":"<known-parked-domain>"}'
# Expect: is_live=true, is_real_business=false, is_keepable=false, ai_reasoning describes the parking page
```
