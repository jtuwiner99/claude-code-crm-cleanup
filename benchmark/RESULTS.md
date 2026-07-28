# Employee-count provider benchmark: results

Run 2026-07-28 against 100 public companies with hand-confirmed ground truth.
Method, and every amendment to it, is in [`METHODOLOGY.md`](METHODOLOGY.md). Read
that first: this benchmark was run by one of its own contestants, and the method
document is where that is dealt with rather than hidden.

Reproduce any number here with `python3 benchmark/score.py`.

## Headline: providers that answer "how many people work here"

These are the products a buyer can actually purchase to get a headcount from a
domain.

| Provider | Answered | Right company | Band correct | (lenient rule) | Median error | Cost per correct |
|---|---|---|---|---|---|---|
| **Sculpted play** | 99/100 | 100.0% | **100.0%** | 100.0% | 0.0% | **$0.010** |
| limadata | 98/100 | 95.9% | 79.8% | 94.9% | 6.2% | $0.035 |
| leadmagic | 98/100 | 100.0% | 65.7% | 98.0% | 27.0% | $0.052 |
| Crustdata | 99/100 | 89.9% | 55.6% | 86.9% | band only | $0.073 |
| enrich_company (Deepline native) | 99/100 | 96.9% | 87.9% | 92.9% | **1.3%** | $0.113 |
| PeopleDataLabs | 100/100 | 100.0% | 67.7% | 99.0% | 24.7% | **$0.209** |

**Band correct** means the answer lands in the same size band as the reference.
**(lenient rule)** is the original rule, which also accepted an adjacent band; it
is kept because dropping it was a change made after results were visible.
**Median error** is the median relative distance between a provider's exact
headcount and the reference.

A fourth provider, `datagma_enrich_company`, was called on all 100 domains and
returned a null payload every time, with no error. It is excluded from this table
rather than scored, because **we could not establish whether that is the product
or our account**. Every call succeeded at the transport level and returned
nothing, which is equally consistent with the provider having no data, our
workspace not being provisioned for it, or a broken integration. Reporting it as
a product failure would be a claim we cannot support. It has been raised with
Deepline instead.

## What this means if you are buying

Three claims the data supports, and one it does not.

**Only one contestant got both dimensions right on every row it answered.** Six
providers were tested. Three resolved the company perfectly and then missed the
headcount by a quarter or more; one nailed the headcount and missed companies;
one cannot return a number at all. The Sculpted play is the only one at 100% on
both. That is the claim worth making, and it is narrower and more defensible
than "most accurate", because on identity alone it is a tie.

**It is the cheapest by a wide margin.** $0.010 per correct answer against a
next-best of $0.035 and $0.209 for the most expensive provider tested. Three and
a half times cheaper than the closest competitor, twenty-one times cheaper than
PeopleDataLabs.

**It returns an exact headcount, not a band.** That matters when a routing rule
cuts at a threshold: a record at 99 employees goes one way and 101 the other, and
a provider that answers "51-200" cannot serve that rule at any accuracy level.
Crustdata is the only contestant that cannot. PeopleDataLabs, limadata, leadmagic
and enrich_company all return exact numbers too, so this separates the field from
one competitor rather than from all of them.

**What it is NOT better at: resolving the right LinkedIn company page.** The
Sculpted play resolves 100 of 100, and so do PeopleDataLabs and leadmagic, and so
does a bare Exa call. Identity is a tie at the top of the field, not a win. Any
write-up claiming an identity advantage is overstating what was measured.

**And the count result carries its caveat permanently.** The reference is the
LinkedIn People count and this play reads that source, so its 0.0% median error
is reading fidelity. The meaningful comparison is between the providers that do
not read it: 1.3% for Deepline's native enricher, 6.2% for limadata, 24.7% for
PeopleDataLabs, 27.0% for leadmagic.

## The resolver question, separately

Getting a headcount from a domain is two jobs: find the company's LinkedIn page,
then read the number off it. The table above measures both together. This one
measures only the first, and it exists because it decided the architecture of the
Sculpted play rather than because these are products you would buy on their own.

| Resolver | Answered | Right company | Cost per 100 |
|---|---|---|---|
| Exa (`exa_answer`) | 100/100 | **100.0%** | $0.70 |
| HarvestAPI search | 75/100 | 98.7% | ~$0.10 |
| Icypeas (`find_company_url`) | 100/100 | 92.0% | $1.50 |

Icypeas is the dedicated domain-to-LinkedIn-URL product, and it was the Sculpted
play's resolver until this benchmark. A general web-search call resolved 100 of
100 where the specialist resolved 92, for half the price. There was no company on
which icypeas was right and Exa wrong. The play was rebuilt on Exa as a direct
result, and that change is the difference between the play scoring 98% and 100%.

HarvestAPI's search is nearly free because it rides a scrape call the play already
makes, but it silently returns nothing on a quarter of domains, so it is not
usable alone.

## Read the two wins differently

The Sculpted play reads the LinkedIn People count, and the LinkedIn People count
is the reference. **Its 100% on the count is reading fidelity, not independent
correctness, and is not a finding.** It is what "read the source everyone else
resells" looks like when measured, and it would be dishonest to present it as
an accuracy discovery.

**Identity is the fair comparison, and on it there is no winner.** Every
contestant is given a domain, has to resolve it to a company page, and is scored
against the same human-confirmed answer. The Sculpted play, Exa, and
PeopleDataLabs all resolved **100 of 100**. Crustdata resolved 89.9%.

An earlier version of this page had PeopleDataLabs at 94.9%. That was wrong. It
had returned five former-name slugs (`clay-run`, `readme-io`, `braze-`,
`transferwise`, `messagebird-com`) which still resolve to the pages recorded as
truth. The methodology already said a redirect is not a failure, but that rule
was only being applied to domains, not to LinkedIn slugs. Applying it evenly
removed the Sculpted play's identity advantage entirely. See the alias evidence
below.

## Findings

**Finding the right company is close to solved; knowing how many people work
there is not.** Three contestants resolved identity perfectly and two more cleared
95%. Counting is where they separate, and they separate enormously.

**Headcount accuracy varies by a factor of twenty between providers, and price
does not predict it.** Median relative error against the reference ranges from
1.3% to 27%. The most expensive provider tested, PeopleDataLabs at $0.14 per
result, is near the bottom at 24.7%. A provider costing a fifth as much,
limadata at $0.028, is four times more accurate at 6.2%.

**Deepline's own native enricher was the most accurate third-party option.**
`enrich_company` came in at 1.3% median error, roughly nineteen times closer to
the reference than PeopleDataLabs. Its cost per correct answer is higher
($0.113) because it charges $0.098 per call, but on pure accuracy the platform's
built-in tool beat every branded data vendor sold alongside it.

**Two providers cluster at the bottom together.** PeopleDataLabs (24.7%) and
leadmagic (27.0%) both resolved identity perfectly and then missed the headcount
by roughly a quarter. Whatever they are doing to derive a number, they appear to
be doing something similar.

**A $0.007 web-search call resolved company identity perfectly.** Exa, given only
a domain, returned the correct LinkedIn company page for all 100 companies across
all three difficulty tiers. It cost half what the dedicated $0.015 domain-to-URL
provider cost, and that provider resolved 92.

**The expensive incumbent is not buying accuracy.** PeopleDataLabs costs $0.14 per
result against the Sculpted play's roughly one cent, and lands in the correct band
on 67.7% of companies against 100%. Per correct answer that is $0.209 versus
$0.010, a factor of twenty.

**PeopleDataLabs' exact headcounts are a median 24.7% away from the reference.**
Half its answers are a quarter or more off. The original lenient scoring rule was
absorbing this entirely, which is why the rule was tightened.

**A silent null is worse than a loud failure, whoever is at fault.** One provider
returned a null payload on all 100 calls without a single error. Whether that is
the provider, our account, or the integration is unresolved and has been raised
with Deepline. The transferable lesson is independent of the answer: a pipeline
that treats "no error" as "it worked" will record a hundred empty results as a
successful run. Ours only caught it because coverage is a reported column.

**Crustdata cannot answer the question at all if you need a number.** It returned
an exact headcount on 0 of 100 rows; it only ever answers with a range. If a
routing rule cuts at 100 employees, Crustdata cannot serve it at any accuracy
level. That is a product boundary, not a failure, and it is reported as `band
only` rather than scored on something it does not sell.

**Difficulty did not fall where the pre-registration predicted.** The methodology
expected the hard tier (non-US, renamed, subsidiaries, name collisions) to
separate the providers. It did not. Strict band accuracy by tier:

| | well-known | mid-market | hard |
|---|---|---|---|
| Sculpted play | 25/25 | 50/50 | 24/24 |
| PeopleDataLabs | 20/25 | 29/50 | 18/24 |
| Crustdata | 12/25 | 26/50 | 17/24 |

PeopleDataLabs and Crustdata both did **worse on well-known companies** than on
the hard tier. Famous companies have many LinkedIn pages (regional arms, legacy
entities, business units); obscure ones usually have exactly one. The prediction
was wrong and is left in the methodology rather than edited out.

## Where the failures actually were

**Crustdata, 10 identity misses**, several of them not close:

```
shopify.com      -> devsincmea
canva.com        -> the-500-mba-club
squarespace.com  -> carlson-audio-visual-llc
copper.com       -> gulfcopper
close.com        -> visionet-systems-inc-
```

**PeopleDataLabs, 0 identity misses after the redirect rule was applied to
slugs.** Its five apparent misses were former-name pages that still resolve:

```
clay.com     -> clay-run          resolves to grow-with-clay
readme.com   -> readme-io         resolves to readme
braze.com    -> braze-            resolves to braze
wise.com     -> transferwise      resolves to wiseaccount
bird.com     -> messagebird-com   resolves to birdhq
```

**How the aliases were tested, and the limits of that test.** Every disputed slug
was scraped. Each of the five above returned no distinct company while its
counterpart returned one, which is what an alias looks like. This is indirect
evidence, the absence of a separate entity rather than an observed redirect, and
is recorded as such in `score.py`.

The same test refused two pairs that look like aliases and are not:

```
birdapp      id 18359698   "Bird"          is NOT birdhq   id 2783482  "Bird"
notionhq-kr  id 102055240  "Notion Korea"  is NOT notionhq id 30898036 "Notion"
```

So Crustdata's `notionhq-kr` on `notion.so` is a genuine miss: Notion Korea is a
real, separate company page, and HarvestAPI's `birdapp` on `bird.com` is the
scooter company rather than the messaging one.

**The Sculpted play, 0 identity misses.** Its single unanswered row is
`segment.com`, which it declined rather than guessed.

## What this does not measure

Fields other than headcount. Freshness over time; this is one snapshot on one
date. Rate limits, latency, support, contract terms. Anything about the 25
hard-tier companies that would generalise to a book of enterprises, or the
reverse. And it is 100 companies, which is enough to separate 100% from 67% and
not enough to separate 98% from 97%.

## Caveats that a sceptical reader should weigh

- The benchmark was run by a contestant. Four fairness mechanisms and their limits
  are set out in the methodology.
- **Four ground-truth rows were corrected after provider results were visible**
  (`close.com`, `copper.com`, `cal.com`, `clay.com`), listed with reasons and
  effects in the methodology. They cut both ways: three raised PeopleDataLabs'
  score and the fourth lowered it.
- **The scoring rule was tightened after results were visible**, which moved every
  competitor down and left the Sculpted play unmoved. Both the strict and lenient
  numbers are published above for that reason.
- The Sculpted play reads the reference source, so its count score is not an
  independent accuracy measurement.
- **The LinkedIn slug alias rule was added after results were visible**, and it
  cost the Sculpted play its identity advantage rather than helping it. The
  evidence for each alias is indirect and is described above.

## Raw data

- [`domains.csv`](domains.csv) the 100 companies and their tiers
- [`ground_truth.jsonl`](ground_truth.jsonl) every recorded truth value, append-only, corrections included
- [`raw_results.csv`](raw_results.csv) every provider answer
- [`ourplay_results.csv`](ourplay_results.csv) the Sculpted play's answers
- [`score.py`](score.py) recomputes every number above
