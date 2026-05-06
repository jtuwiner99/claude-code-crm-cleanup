# How this was built

The judgment work behind the recipe — captured at toy scale so a reader can see what scoping actually looks like before the engineering starts.

## The starting question

Acme came in with: *"clean our CRM and qualify our accounts."* That's not a recipe — it's a goal. Three things had to happen before any enrichment ran:

1. Pin who they actually sell to (ICP), in shapes you can encode in a column
2. Pick the *minimum* set of properties that determines tier, not "everything we wish we knew"
3. Define each property tightly enough that the model returns the same thing across runs

## Pinning the ICP

The first 30 minutes of scoping was Acme talking through closed-won deals — what those companies looked like at the moment of purchase, not at signup. Three patterns emerged:

- **Size mattered, sharply, at 500 employees.** Below that, prospects didn't have a dedicated RevOps function (Acme's economic buyer). Above it, they did. A graduated curve would have been wrong here — the cliff was real.
- **Acquired companies almost never bought.** Even when the on-record domain still operated, post-acquisition tech-stack decisions consolidated to the parent. Three deals that had stalled out in the prior quarter all shared this pattern: prospect was technically still active, but the buyer had moved.
- **The FinTech wedge was profitable but small.** Worth a Tier 2 lane, not a Tier 1 lane.

That's where the rubric in `icp.md` came from. None of it was inferred from the data — it was inferred from the *closed-won and closed-lost histories* by talking to the AE team for an hour.

## Picking the minimum properties

Acme's first list of "what we want enriched" was 14 properties: industry, size, country, funding stage, recent hiring, tech stack, security/compliance certs, AE-handle preferences, and several others. We cut it to 5:

| Kept | Why |
|---|---|
| `industry` | The B2B SaaS / FinTech / everything-else split is the single biggest tier signal |
| `employee_count_tier` | The 500+ cliff is the second-biggest signal |
| `is_acquired` | A hard drop signal that wasn't otherwise visible in the CRM |
| `acquirer_name` | Required to actually act on `is_acquired` (reroute target) |
| `pitch` | Feeds AE personalization at outreach time — the one nice-to-have we kept |

| Cut | Why |
|---|---|
| `hq_country` | Tier 3 captures "international" already; not worth the model precision required |
| `funding_stage` | Volatile, hard to verify, not actually predictive in Acme's data |
| `recent_hiring_velocity` | Costly to enrich, weakly correlated with buying intent |
| `tech_stack` | Real signal but needs technographic providers Acme isn't ready to add |
| `security_certs` | Buyer-side disqualifier, not a tier driver |
| ...and 4 others | Some valuable, none in the v1 critical path |

The cut was driven by one rule: *if removing this property would not change which tier the row lands in, cut it.* Anything that influences personalization but not tier got moved to v2.

## Defining each property tightly

The recipe.yaml descriptions are the result of three iterations on the eval set. Iteration #1 used loose descriptions and the model fuzzed too much:

> Initial: `industry — what kind of company they are`

The model labeled half the marketplace plays as "Services," which collapsed Tier 1 into 60% of what it should have been. Tightening to:

> v2: `industry — One of: B2B SaaS, FinTech, E-commerce, Services, Hardware, Other. Pick the closest match based on what the company sells.`

…fixed most of it. But the model still hedged on payment infrastructure (Stripe, Braintree) — sometimes calling them FinTech, sometimes B2B SaaS. Adding the explicit clause:

> v3: `Marketplaces, payment infrastructure, and developer tools count as B2B SaaS if their primary buyer is a business.`

…locked the FinTech-vs-B2B-SaaS boundary. Stripe stayed FinTech (their primary buyer is the business *paying for payments*); Twilio became B2B SaaS (developer tools).

Same iteration pattern on `is_acquired`. v1 had the model false-positive on subsidiaries (calling GitHub "acquired by Microsoft" — technically true, but Microsoft hasn't absorbed GitHub's procurement). The clause:

> A subsidiary that retains independent procurement... is borderline; mark is_acquired=true only when the parent has clearly absorbed the company's tech-stack decisions.

…drew the right line. GitHub stays `is_acquired=true` (Microsoft's tech stack is fully integrated post-acquisition); a hypothetical "freshly acquired with autonomy" company would be borderline.

## Building the eval set

`expected-output.csv` is 30 rows hand-graded against public information for each company. Two design choices:

1. **15 of the rows match well-known acquisitions or hero patterns.** Not because they're representative of Acme's CRM (most CRM rows are mundane), but because they're recognizable to a reader. If the recipe gets Slack→Salesforce wrong, that's an unambiguous fail; if it gets a fictional company wrong, the reader has no way to evaluate.
2. **The 15 "hero" rows are pre-existing in `tmp/golden-accounts.csv`** so the same eval transfers between this example and the headline `/crm-cleanup` flow. Reusing the golden across examples is a deliberate maintenance decision — one less surface to keep in sync.

The `EXPECTED_pitch` cells use `UNREACHABLE_OR_DEAD_DOMAIN` as a sentinel for the three dead domains in the input — `tools/qa.py` recognizes this and accepts any "this domain is dead"-shaped output rather than requiring exact wording.

## What's NOT in this example

- **Per-property failure analysis after a real run.** When the actual recipe runs against real data, you'll see fields that consistently miss — the iteration loop in `/crm-cleanup` Phase 4 surfaces these and prompts a definition tweak. Out of scope for a frozen example.
- **Stakeholder review on the property descriptions.** Acme's real engagement involved 2–3 rounds of "show this to the AE team, take their edits, regenerate" before the descriptions stabilized. That feedback loop is the operator wrapper; not in this repo.
- **A scoring layer.** `scoring-model.json` declares the rubric, but applying it (turning `industry + size + is_acquired` into a tier number) is a separate step Acme's CRM does internally. The repo's `enrichment-functions/score_account_via_latitude/` has the production-grade pattern.

The whole point: the recipe is the artifact, but the recipe is the *output* of about 90 minutes of scoping conversation, eval-driven definition tightening, and tradeoff calls about what's in v1 vs. v2. None of that ships in a YAML file. Reading the YAML and assuming you can skip the conversation is the most common failure mode for first-timers.
