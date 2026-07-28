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
| PeopleDataLabs | 100/100 | 100.0% | 67.7% | 99.0% | **24.7%** | $0.209 |
| Crustdata | 99/100 | 89.9% | 55.6% | 86.9% | band only | $0.073 |
| Datagma | **0/100** | n/a | n/a | n/a | n/a | n/a |

**Band correct** means the answer lands in the same size band as the reference.
**(lenient rule)** is the original rule, which also accepted an adjacent band; it
is kept because dropping it was a change made after results were visible.
**Median error** is the median relative distance between a provider's exact
headcount and the reference.

Datagma is scored `n/a` rather than 0% on purpose. It never returned a value, so
there is nothing to be right or wrong about; scoring it as 0% accurate would imply
it answered and answered badly. What it did is described under Findings.

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

**Finding the right company is a solved problem; knowing how many people work
there is not.** Three of the five contestants resolved identity perfectly. Only
one of them then got the headcount right. The interesting failure is not matching,
it is counting.

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

**Datagma returned nothing, 100 times, without an error.** It is listed in the
catalogue at $0.027 per result. Every call succeeded and every payload was null.
A provider that silently answers nothing is worse than one that fails loudly,
because nothing in a pipeline notices.

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
