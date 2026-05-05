# acquired_brand_status

For a company already flagged as acquired, decide whether the acquired brand is still operating standalone (`independent`), has been fully absorbed into the acquirer (`absorbed`), or is no longer reachable (`inactive`).

## Status: opt-in add-on (NOT default)

This function is **opt-in**, paired with `detect_acquisition` in the M&A toggle. Don't enable it without enabling `detect_acquisition` upstream — there's no acquirer to compare against.

**Use this function when:**

- You're already running `detect_acquisition` (M&A toggle on) and need to differentiate independently-operated acquired brands (e.g. Slack still operating standalone after the Salesforce acquisition) from fully absorbed ones (e.g. Clearbit's domain redirecting to HubSpot's site post-acquisition — both are public M&A facts, used here as illustrative examples).
- Your CRM rules treat the two cases differently — e.g. independent → keep + tag as child, absorbed → drop or merge into parent.
- ABM-style targeting where routing reps to a fully-absorbed brand wastes pipeline.

**Skip this function when:**

- M&A detection alone is sufficient ("flag as acquired, route to a manual reviewer" — this function automates that review).
- The your TAM is M&A-light enough that the cost of running this on every acquired row isn't justified.

## Why this exists

`detect_acquisition` answers "did an M&A event happen?" — a durable historical fact. This function answers "is the acquired brand still operating today?" — a volatile, current-state question. The split matters for CRM routing:

- **Independent** (e.g. Slack under Salesforce): slack.com still active, hero copy still pitches Slack as a product, employees still on slack.com or @salesforce.com but tagged with the Slack team. CRM record should be tagged as child of Salesforce + kept active for prospecting.
- **Absorbed** (e.g. Clearbit under HubSpot): clearbit.com homepage hero is "Clearbit has joined HubSpot", visitors pushed to hubspot.com, all employees migrated. CRM record should be deduped or routed to HubSpot's owner.
- **Inactive**: domain expired, registrar holding page, server error. CRM record likely stale and droppable.

This three-state model is the canonical decision shape across cleanup engagements — see `skills/ma-and-corporate-structure-playbook` for the full operational playbook.

## Three-step pipeline

| Step | What | Cost |
|---|---|---|
| 1. Deterministic redirect-to-parent check | JS host-comparison: does `verify_domain_alive.final_url` resolve to a host on `acquirer_domain`? www / subdomain prefixes stripped. | $0 — pure compute. |
| 2. Deterministic short-circuits | `is_live=false` → `status=inactive` (no AI call). `redirected_to_parent=true` → `status=absorbed` (no AI call). | $0. Hits the AI step only when neither condition fires. |
| 3. AI homepage-language judgment | Visit the acquired-co homepage. Judge whether the page is still pitching the acquired brand standalone (independent) or has been replaced by acquisition language (absorbed). Bias toward independent unless >90% confident in absorption — verbatim from the Clay source. | One AI call (~$0.004, gpt-5-mini, ~2000 tokens). Skipped on deterministic short-circuit. |

Total: $0 when the deterministic checks fire (a meaningful share of input — fully absorbed brands typically redirect; inactive domains fail liveness in `verify_domain_alive` upstream). ~$0.004/row when the AI step runs.

## Pipeline placement

```
normalize_domain_and_name
       ↓
verify_domain_alive (drop if !is_keepable)  ← provides is_live, final_url
       ↓
company_summary_from_website
       ↓
detect_acquisition (opt-in)                 ← provides acquirer_domain
       ↓ (gate on is_acquired === true)
acquired_brand_status                       ← here (opt-in)
       ↓ (gate downstream on status === 'independent' for M&A-strict pattern)
linkedin_url_verified
       ↓ ...
```

This function consumes outputs from BOTH `verify_domain_alive` (liveness + final_url) AND `detect_acquisition` (acquirer_domain). It must run after both. Because of the gate, it only runs on rows that the acquisition detector flagged.

## Inputs / outputs

See `function.yaml` for the typed contract. Things worth highlighting:

1. **`verify_domain_alive_output` is required, not optional.** The function reuses upstream liveness + redirect signals instead of paying for a second HTTP probe (a deliberate library-wide consolidation — see Clay parity below).
2. **`acquirer_domain` is required.** Without it the redirect-to-parent check can't run; calling this function on a non-acquired row is meaningless.
3. **`status` is the canonical output.** `is_active` is just `(status === 'independent')` for callers who only need a binary gate.

## Default-to-independent semantics

Matches Clay table's explicit "bias toward Active unless >90% confident inactive" rule:

- AI step failure → `status=independent`. False negatives (incorrectly marking absorbed as independent) cost a duplicate-enrichment downstream; false positives (incorrectly dropping a still-operating brand) cost a relationship.
- AI returns `status=independent` by default when the homepage has any normal product marketing — only `status=absorbed` when the homepage is primarily about the acquisition.
- Recipe authors who want stricter behavior (e.g. drop anything not explicitly flagged independent with high confidence) should branch on `verification_signals.ai_judgment.confidence === 'high'`.

## What this function does NOT cover

- **The acquisition event itself.** Was this company acquired and by whom? — `detect_acquisition`'s job. This function takes the acquirer as input.
- **Native subsidiaries / divisions WITHOUT an acquisition event.** A Delta-style aviation subsidiary that has its own legal entity but no M&A event won't have an `acquirer_domain` to compare against. Tracked as the planned `detect_corporate_structure` future-extension function.
- **CRM dedup or merge logic.** This function emits the status; the calling recipe decides what to do with it (merge into parent, route to acquirer's owner, drop, tag-and-keep).

## Gotchas

- **The redirect-to-parent check is host-only, not URL-match.** `https://www.clearbit.com/about` → `https://www.hubspot.com/products/breeze-intelligence` matches because the final-URL host (hubspot.com) equals `acquirer_domain` (hubspot.com). Subdomains of the acquirer (e.g. clearbit.hubspot.com) also match because we use `endsWith('.' + acquirer_domain)`.
- **`final_url` may be null** when upstream `verify_domain_alive` only ran the deterministic HTTP layer with `skip_ai_verification=true`. The function handles this — `redirected_to_parent` defaults to false, AI step proceeds normally with whatever `final_url` is available.
- **Inactive RARELY fires from the AI step.** The deterministic short-circuit (`is_live=false`) catches most inactive cases upstream in `verify_domain_alive`. The AI step's `inactive` enum exists as a defense-in-depth — if the AI sees a parking-page-style site that somehow passed verify_domain_alive, it can still flag it.
- **The Clay source had a "Suspended Page" formula reading ApiVoid's registrar-suspended flag.** We dropped it — `verify_domain_alive`'s AI parking-page detector covers the same class of pages (registrar holding pages, blank landers). If a customer reports false negatives on registrar-suspended domains, the right fix is to extend `verify_domain_alive`'s AI detector, not to add an ApiVoid call here.
- **Bias direction is INTENTIONAL.** This function defaults to `independent` aggressively. Recipe authors who notice too many false-positive-independent results should NOT change the function's bias — they should add a recipe-level filter on `verification_signals.ai_judgment.confidence` instead. The bias reflects a deliberate principle: false drops (incorrectly removing a still-operating brand) are more expensive than false keeps (a duplicate enrichment downstream).

## Future integration

A configuration UI for "always-on defaults vs. opt-in toggles" is not yet built. Once it ships, this function will appear under the M&A toggle alongside `detect_acquisition`. Until then, recipe authors enable the pair explicitly per project.

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/acquired_brand_status.workflow.json)"

# Case 1: absorbed (a brand whose domain redirects to its acquirer's site)
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "clearbit.com",
  "acquirer_domain": "hubspot.com",
  "verify_domain_alive_output": {
    "is_live": true,
    "final_url": "https://www.hubspot.com/products/breeze-intelligence",
    "http_status_code": 200,
    "is_keepable": true
  }
}'
# Expect: status=absorbed (deterministic short-circuit on redirect-to-parent),
#   redirected_to_parent=true, is_active=false, ai_reasoning=null (AI didn'\''t run)

# Case 2: independent (Slack still operating standalone under Salesforce)
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "slack.com",
  "acquirer_domain": "salesforce.com",
  "verify_domain_alive_output": {
    "is_live": true,
    "final_url": "https://slack.com/",
    "http_status_code": 200,
    "is_keepable": true
  }
}'
# Expect: status=independent (AI judges homepage is still pitching Slack standalone),
#   redirected_to_parent=false, is_active=true

# Case 3: inactive (acquired and domain went dark)
deepline workflows call --workflow-id <ID> --payload '{
  "domain_clean": "olddefunctcompany.com",
  "acquirer_domain": "bigco.com",
  "verify_domain_alive_output": {
    "is_live": false,
    "final_url": null,
    "http_status_code": null,
    "is_keepable": false
  }
}'
# Expect: status=inactive (deterministic short-circuit on is_live=false),
#   redirected_to_parent=false, is_active=false, ai_reasoning=null
```

## Clay parity

Source: Clay table `Active/Inactive Company Check` (28 columns). Two AI calls in the Clay version (Status Research → Status Decision, both gpt-4o); we collapse to one structured-JSON deeplineagent call on gpt-5-mini.

Field-by-field mapping vs. Clay table outputs:

| Clay column | Port output | Notes |
|---|---|---|
| `Active` | `is_active` | Same boolean. Convenience mapping of `status === 'independent'`. |
| `Acquisition Status research` (Active/Inactive enum) | `status` (independent/absorbed/inactive enum) | Three-state instead of two — distinguishes "absorbed" (no longer marketed standalone) from "inactive" (domain dead). The original Clay column collapsed both into "Inactive". |
| `Reasoning` | `ai_reasoning` | Same string. Null when deterministic short-circuit fired. |
| `Site Down` | `verification_signals.liveness.is_live === false` | Available in audit trail. |
| `Redirected to Parent Company` | `redirected_to_parent` | Same boolean — promoted to top-level output. |
| `Http Status Code` | `verification_signals.liveness.http_status_code` | Available in audit trail. Sourced from upstream `verify_domain_alive`, not a fresh ApiVoid call. |
| `Url Taken Down` (ApiVoid registrar flag) | NOT PORTED | Functionally covered by `verify_domain_alive`'s AI parking-page detector. If domain is registrar-suspended, upstream returns `is_live=false`. |
| `Suspended Page` (ApiVoid suspended-page flag) | NOT PORTED | Same as above. |
| `HTTP Inactive Check (True Means Inactive)` | Subsumed into `status` (inactive or absorbed) | The Clay formula was `Site Down OR Redirected to Parent`; the port handles both cases via the `status` enum. |

Clay's `HTTP API` call (paid ApiVoid third-party service for HTTP status / redirect / suspended-page) — DROPPED entirely. `verify_domain_alive` already exposes `is_live`, `final_url`, and `http_status_code`; consuming those upstream outputs costs $0 and avoids a redundant paid HTTP probe. This is the most material deviation from the Clay table.

Clay's `Lookup Single Row in Other Table` (cross-table parent-domain lookup) — replaced by the `acquirer_domain` input parameter. The calling recipe binds `detect_acquisition.acquirer_domain` directly into this function's input.

Clay's `Write to Other Table` (downstream-tracking writeback) — DROPPED. CRM writeback is a recipe-level concern, not a function-level one.
