# Employee-count provider benchmark: pre-registered methodology

**This document was committed BEFORE any provider was run.** Its git timestamp is the
proof, and the 100 domains in `domains.csv` were fixed at the same commit.

It has since been amended. Every amendment is its own commit with its reason, so the
original and the change are both public and the sequence is checkable. Three are
material and each says so in place:

- **The reference became the LinkedIn People count** (amended before any truth was
  recorded). The original excluded LinkedIn; that was wrong about the market.
- **Identity and count became separate dimensions** (amended before any truth existed).
- **Scoring became strict same-band** (amended AFTER results were visible). This is
  the one that deserves suspicion: it moved every competitor down and left our own
  play unmoved. Both the strict and the lenient numbers are therefore published side
  by side, permanently, so the effect of the change is visible rather than buried.

Four ground-truth rows were also corrected after provider results were seen. They are
listed with their reasons and their effect on the scores in their own section below.

Amending a benchmark you are competing in is a real hazard. The mitigation here is not
that it never happened, it is that every instance is named, dated, reasoned, and
reported alongside the number it replaced.

## The question

Given only a company's domain, how accurately can each provider tell you how many
people work there, at what cost, and how often does it answer at all?

Three sub-questions, because a single accuracy number hides which of them a
provider actually fails:

1. **Does it find the right company?** Scored against the LinkedIn company page a
   human confirmed. Every contestant is given the same domain and no advantage.
2. **Does it then get the headcount right?** Scored in size bands, strictly, and
   separately over only the rows where the company was right, so a matching
   failure is not misreported as a counting failure.
3. **Does it return an exact number or only a range?** A provider that answers
   "51-200" cannot serve a routing rule that cuts at 100, at any accuracy level,
   so this is recorded as a capability rather than folded into an accuracy score.

## Why we are not a neutral party, and what we did about it

Sculpted's own play is one of the contestants. A benchmark run by a contestant is
worth nothing unless the method removes the ways the author could tilt it. Four
mechanisms, all fixed in advance:

1. **The reference is LinkedIn by design, and our advantage on it is declared.**
   Firmographic providers overwhelmingly derive headcount from LinkedIn-sourced
   profiles, so LinkedIn is the reference they are all approximating and distance
   from it is what a buyer actually cares about. The Sculpted play reads that
   reference directly, so its count score measures reading fidelity rather than
   independent correctness. That is intended, it is not a discovery, and it must
   be said wherever these numbers appear. The findings are the other providers'
   distance from the reference and their cost per correct answer. Identity is a
   separate matter: every contestant resolves a domain to a company page and is
   scored against the same human-confirmed answer, with no advantage to anyone.
2. **The reviewer is blind to the provider.** Ground truth was recorded by a human
   in a purpose-built console. Per company it showed the domain, the company's own
   homepage framed in the page, and the candidate LinkedIn pages deduplicated,
   unlabeled, and shuffled by a domain-seeded ordering, with a path to reject all
   of them and paste the correct page instead. No provider name and no provider's
   employee count was ever rendered, so the reviewer judged a page rather than a
   vendor. The console is `ground_truth_console.py` in this directory and is
   forbidden by construction from reading the provider result files.
3. **The sample is fixed and published before the run.** No dropping hard rows after
   the fact, no adding easy ones.
4. **The raw per-company results are published**, not just the summary table. Anyone
   can recompute every number in the post from the released data.

If our play loses a column, that column gets published exactly as measured.

## Sample: 100 companies, stratified, public

The sample deliberately excludes any company from a customer CRM, for two reasons: a
real book is one company's ICP and would make the result unrepresentative, and
publishing it would expose that company's pipeline.

Strata, fixed in `domains.csv`:

| Tier | Count | What it tests |
|---|---|---|
| Well-known | 25 | The easy case. Everyone should get these. Establishes the floor. |
| Mid-market | 50 | The realistic case. Recognizable in their niche, invisible outside it. |
| Hard | 25 | Where providers actually differ: non-US, recently renamed or rebranded, subsidiaries of larger parents, and companies sharing a name with something more famous. |

The hard tier is where the story is expected to be. Every provider gets Stripe right.

**A redirect is not a failure.** Several domains in the sample redirect to a parent or
to a renamed destination: segment.com to Twilio, looker.com to Google Cloud, chorus.ai
to ZoomInfo, notion.so to notion.com. A provider that follows the redirect and answers
about the right company is correct. A provider is only marked wrong for the wrong
answer, never for handling a redirect the benchmark did not anticipate.

**The sample was fact-checked before publication, and the check changed it.** An
independent pass found one domain that was parked rather than owned by the intended
company, one wrong country, and seven companies sitting in tiers that claim
independence while actually being acquired subsidiaries or renamed entities. All were
corrected before this commit. That pass is itself a finding worth stating plainly: in
a hand-picked list of recognizable software companies, roughly seven percent had
quietly stopped being the company the list assumed they were, which is the same decay
this product exists to measure.

## Ground truth

**Amended 2026-07-28, before any truth was recorded, replacing the earlier
non-LinkedIn rule.** Truth for the employee count is **the LinkedIn company
People-tab count**, read by a human.

The earlier version of this document excluded LinkedIn as a truth source on the
grounds that one contestant reads LinkedIn and scoring against it would be
circular. That reasoning was wrong about what the market actually is. B2B
firmographic providers overwhelmingly derive headcount from LinkedIn-sourced
profile data. If the providers are approximating LinkedIn, then LinkedIn is the
reference they are all approximating, and measuring distance from it is measuring
the thing buyers care about: how stale and how wrong is the copy you are paying
for.

**The consequence must be stated wherever these results are published, and is
stated here first:** the Sculpted play reads the LinkedIn People count directly.
Scoring it against the LinkedIn People count therefore measures its reading
fidelity, not its independent correctness. A high score for the Sculpted play is
EXPECTED, is not a finding, and must never be presented as one. The findings are
the other providers' distance from the reference, and their cost per correct
answer. Any write-up that reports the Sculpted play's accuracy without this
sentence attached is misrepresenting the benchmark.

A second, optional truth value is recorded where a human can find one: an
`independent_count` from a non-LinkedIn source (the company's own about or
careers page, or a filing) with its citation. It will be present for some
companies and absent for others. Where present, accuracy is reported against it
as a secondary table. That table is the closest thing here to a source-neutral
accuracy measure, and it is reported on whatever subset exists rather than
extrapolated.

A company whose LinkedIn page cannot be identified at all is recorded as
`no-ground-truth` and excluded from count scoring for every provider equally,
with the exclusion count published.

### Anchoring control

Providers are run before ground truth is established, so that the spread across
providers can be inspected first. That ordering creates an anchoring risk: someone who
has already read a provider's answer for a company cannot independently verify that
company, they can only agree or disagree with a number they have seen.

The control is that ground truth is logged **blind**. The review worksheet lists the
domain and its tier and nothing else. Provider answers are withheld from the worksheet
and joined to it only after every ground-truth value has been written down and
committed. The aggregate spread may be inspected before review, since disagreement
counts and coverage rates reveal nothing about which value is correct for any
particular company.

## Two dimensions, scored separately

**Amended 2026-07-27, before any ground truth existed.** The original method scored one
thing: is the headcount right. That conflates two different failures. A provider can
find the wrong company and report its headcount accurately, or find the right company
and miscount it. Those have different causes and different fixes, and averaging them
hides both.

Every provider is therefore scored on two independent dimensions:

1. **Identity.** Did it resolve the domain to the correct LinkedIn company page? Scored
   against the correct URL, normalized (lowercased, `www.` and trailing slash removed).
2. **Count.** Is the headcount right, by the band rule below?

Count accuracy is reported twice: over all rows, and over only the rows where identity
was correct. The second number is the provider's counting ability with identity failures
removed. The gap between them is how much of its error is really a matching problem.

A provider that returns no LinkedIn URL is not penalized on identity, it is recorded as
`no-url` and excluded from the identity denominator, because some providers do not
claim to do URL resolution at all. Excluding them is stated here rather than decided
later.

This amendment is recorded in its own commit, before ground truth exists, so it cannot
have been chosen to flatter a result nobody has seen yet.

## Corrections made to the ground truth after results were visible

Four of the 100 ground-truth rows were corrected after provider results had
been seen. This is the single most attackable thing in this benchmark, so it is
stated here rather than left for a reader to find.

Every correction is an appended row in `ground_truth.jsonl` with its reason, and
the file is append-only with last-row-wins, so the original value and the
correction are both in the record and in git history.

| Row | Recorded first | Corrected to | Why |
|---|---|---|---|
| close.com | visionet-systems-inc- | close-crm | The wrong candidate was confirmed during review |
| copper.com | gulfcopper | copper-inc | Gulf Copper is an unrelated company |
| cal.com | globalstaffingsupport | cal-com | The wrong candidate was confirmed during review |
| clay.com | clay-run | grow-with-clay | Owner confirmed grow-with-clay is Clay's page; the recorded People count already matched it, so only the URL field was wrong |

**The corrections cut both ways, which is the point.** The first three moved
PeopleDataLabs from 92.9% to 96.0% identity, because it had those three right and
was being penalized by the bad reference. The fourth moved it back down from 96.0%
to 94.9%, because it had resolved clay.com to clay-run. Over the same four rows
the Sculpted play moved from 91.9% to 98.0% and Exa from 99.0% to 100.0%.

**How they were found.** Three surfaced when the play's answers were compared
against the reference and the disagreements were inspected by hand; the reference
turned out to be wrong rather than the play. The fourth was raised by the repo
owner directly. All four were corrected before the final run.

**The honest risk.** Correcting a reference after seeing which contestants
disagree with it is a route to fitting the reference to a favoured result. The
defences here are that every correction is individually checkable against a live
LinkedIn page, the reasons are recorded, the corrections demonstrably hurt one
contestant as well as helping others, and the raw provider outputs are published
so anyone can rescore against the original values if they disagree.

## Scoring

**Amended 2026-07-28, after results were visible. The direction of the change and
its effect are stated here because that is the honest way to make it.**

A provider's answer is correct when it lands in the **same** size band as the
reference. Adjacent bands are wrong. Bands are the ones the report card uses:

```
1-10, 11-50, 51-200, 201-500, 501-1000, 1001-5000, 5001-10000, 10001+
```

The original rule forgave an adjacent band, on the reasoning that a company with
480 employees might honestly report 500. That was replaced because **routing
rules cut at band boundaries**. An operator who segments at 100 employees sends a
record one way at 99 and the other way at 101. A number that lands in the wrong
band sends the record to the wrong place, and calling that correct hides the
error that actually costs something.

**This change moved every competitor down and left the Sculpted play unmoved**,
which is exactly the shape of a self-serving rule change, so both numbers are
published side by side in every table and the lenient column is never dropped:

| | strict (same band) | lenient (same or adjacent) |
|---|---|---|
| ourplay | 100.0% | 100.0% |
| peopledatalabs | 67.7% | 99.0% |
| crustdata | 55.6% | 86.9% |

The reason the gap is that large is not boundary noise. **PeopleDataLabs' median
relative error on its exact headcount is 24.7%** — when it returns a number, the
typical answer is a quarter away from the reference. The lenient rule was
absorbing that. The Sculpted play's median error is 0.0%, which is the home
advantage restated: it reads the reference, so it does not so much agree with it
as copy it.

**Exact numbers versus bands is itself a product difference.** PeopleDataLabs
returns an exact headcount on 100 of 100. The Sculpted play returns one on 99 of
100. Crustdata returns an exact headcount on **0 of 100**: it only ever answers
with a range. A buyer whose routing rule cuts at a threshold cannot use Crustdata
for that purpose at any accuracy level, so it is reported as `band only` rather
than given a relative-error score it structurally cannot earn.

## Metrics

Reported per provider:

- **Coverage**: share of the 100 that got any answer at all.
- **Accuracy on answered**: of the rows it answered, share that were correct. This is
  the number most benchmarks stop at, and on its own it rewards a provider that
  answers only the easy rows.
- **Cost per company attempted**: total spend divided by 100.
- **Cost per correct answer**: total spend divided by correct answers. This is the
  metric that actually decides what to buy, and it is the headline.
- **Accuracy by tier**, so a provider that is excellent on well-known companies and
  useless on the hard tier cannot hide behind an average.
- **Magnitude of error when wrong**: median absolute difference and median ratio
  against the reference count. Band distance is deliberately coarse and hides how
  wrong a wrong answer is. A provider that says 41 when the answer is 1,214 and one
  that says 900 when the answer is 1,214 are both "wrong by bands" and are not the
  same product.

A provider that answers 40% of rows perfectly and one that answers 100% at 80%
accuracy are different products. Reporting coverage and accuracy separately is the
only honest way to show that.

## Contestants

Every provider is called through Deepline with its default domain-to-firmographics
path, with no per-provider tuning, prompt engineering, or retry logic that the others
do not also get. Where a provider offers several entry points, the one documented as
its standard company enrichment is used.

The Sculpted play is run exactly as shipped, with no special configuration.

Actual per-call prices are recorded from the billing ledger after the run rather than
taken from rate cards, because rate cards and invoices disagree.

## What this benchmark does not measure

- Fields other than headcount. A provider that is weak here may be strong at industry,
  location, funding, or contact data.
- Freshness over time. This is one snapshot on one date.
- Rate limits, latency, support, or contract terms.
- Anything about the 25 hard-tier companies that would generalize to a book of
  well-known enterprises, or the reverse.

## Reproducing this

The domain list, the raw per-provider outputs, the ground-truth records with their
citations, and the scoring script are all published in this directory. Every number in
any post that cites this benchmark can be recomputed from them.

## Known expiry on one row

`intercom.com` is in the hard tier because its parent renamed to Fin, Inc. in May 2026
and a Salesforce acquisition was signed on 15 June 2026 but has not closed. Salesforce
expects it to close in its FY2027 Q4. If a run happens after that close, the row's
identity changes and the note must flip from "signed but not closed" to "closed". This
is stated in advance because a company changing identity mid-benchmark is exactly the
failure this tier exists to expose, and it should not be discovered in the results.
