# Employee-count provider benchmark: results

Run 2026-07-28 against 100 public companies with hand-confirmed ground truth.
Method, and every amendment to it, is in [`METHODOLOGY.md`](METHODOLOGY.md). Read
that first: this benchmark was run by one of its own contestants, and the method
document is where that is dealt with rather than hidden.

Reproduce any number here with `python3 benchmark/score.py`.

## Headline

| Contestant | Answered | Right company | Band correct | (lenient rule) | Median error | Cost per correct |
|---|---|---|---|---|---|---|
| **Sculpted play** | 99/100 | **100.0%** | **100.0%** | 100.0% | 0.0% | **$0.010** |
| PeopleDataLabs | 100/100 | 94.9% | 67.7% | 99.0% | **24.7%** | $0.209 |
| Crustdata | 99/100 | 89.9% | 55.6% | 86.9% | band only | $0.073 |
| Datagma | 0/100 | n/a | 0.0% | 0.0% | n/a | n/a |
| Exa (resolver only) | n/a | **100.0%** | n/a | n/a | n/a | n/a |
| HarvestAPI search (resolver only) | 75/100 | 98.7% | 74.7% | 75.8% | 0.0% | n/a |

**Band correct** means the answer lands in the same size band as the reference.
**(lenient rule)** is the original rule, which also accepted an adjacent band; it
is published permanently because dropping it was a change made after results were
visible. **Median error** is the median relative distance between a provider's
exact headcount and the reference.

## Read the two wins differently

The Sculpted play reads the LinkedIn People count, and the LinkedIn People count
is the reference. **Its 100% on the count is reading fidelity, not independent
correctness, and is not a finding.** It is what "read the source everyone else
resells" looks like when measured, and it would be dishonest to present it as
an accuracy discovery.

**Identity is the fair comparison.** Every contestant is given a domain, has to
resolve it to a company page, and is scored against the same human-confirmed
answer. Nobody has an advantage there. The Sculpted play and Exa both resolved
100 of 100. PeopleDataLabs resolved 94.9%, Crustdata 89.9%.

## Findings

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

**PeopleDataLabs, 5 identity misses**, and in fairness **two or three are
arguable rather than wrong**:

```
clay.com    -> clay-run          (truth: grow-with-clay)
readme.com  -> readme-io         (truth: readme)
braze.com   -> braze-            (truth: braze)
wise.com    -> transferwise      (truth: wiseaccount)
bird.com    -> messagebird-com   (truth: birdhq)
```

`braze-` differs from `braze` by a trailing character. `transferwise` is Wise's
former name and `messagebird-com` is Bird's; both are real pages for the same
businesses. A reviewer could reasonably score two or three of these as correct,
which would put PeopleDataLabs at 97-98% identity rather than 94.9%. The strict
reading is used because it was applied identically to every contestant, but the
ambiguity is real and is stated here rather than left to be discovered.

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

## Raw data

- [`domains.csv`](domains.csv) the 100 companies and their tiers
- [`ground_truth.jsonl`](ground_truth.jsonl) every recorded truth value, append-only, corrections included
- [`raw_results.csv`](raw_results.csv) every provider answer
- [`ourplay_results.csv`](ourplay_results.csv) the Sculpted play's answers
- [`score.py`](score.py) recomputes every number above
