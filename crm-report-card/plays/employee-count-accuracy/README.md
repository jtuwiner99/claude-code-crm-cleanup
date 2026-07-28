# Employee-count accuracy

Checks whether the employee count stored on your company records is actually
right, by fetching a verified headcount for each domain and comparing bands.

**What it unlocks:** the "Employee-count accuracy, verified vs stored" row on
the report card.

**What it needs:** a companies export with a domain column and an employee-count
column. Records with a blank stored count are skipped, because a blank is a
completeness problem the free scan already grades.

**Providers:** Exa resolves the domain to a LinkedIn company URL (`exa_answer`,
one query per record). Every resolved URL is then scraped in one batched call
to Apify's HarvestAPI LinkedIn-company actor, so a 100-record sample runs one
scrape, not a hundred. An identity check confirms the scraped company is the
one you meant: deterministic domain match first, and a small model call
(`ai_inference`) only when that match fails or the scraped page has no usable
website field. All three are Deepline-native and billed to your own Deepline
account with credits. There is no key to set up.

Exa is the sole resolver as of 2026-07-28, replacing a two-round Icypeas+Exa
waterfall. Measured against a 100-company, hand-confirmed benchmark, Exa alone
resolved 98/100 correctly -- more accurate than the old two-round waterfall
(96/100) and Icypeas alone (92/100) -- for about half of what Icypeas's own
resolver call cost by itself.

**What it costs:** at most $0.01 per matched record, so at most $1 for the
default 100-record sample. That figure is a ceiling: a miss at any step costs
nothing, and the identity-check model call only runs on the smaller set of
rows where the domain match fails.

**What "wrong" means:** the play reports LinkedIn's associated-member count,
not payroll headcount, and the two are not the same number. Associated
members counts every profile that lists the company, which typically runs
higher than the number of people actually on payroll. Mismatch is defined as
the stored count and that associated-member count falling two or more size
bands apart, so this can flag some correct CRMs as wrong if the CRM is closer
to true headcount than to LinkedIn's number. That is a disclosed tradeoff, not
a bug. Bands are 1-10, 11-50, 51-200, 201-500, 501-1000, 1001-5000, 5001-10000,
10001+.

**When a row is unverifiable:** if no LinkedIn URL could be resolved, the
resolved URL was not in the scrape batch, or the identity check could not
confirm it was looking at the right company, the row is marked unverifiable
rather than scored. An unverifiable row is never counted as a mismatch: we
either could not find the company or could not confirm it was the right one.

**It never writes to your CRM.** It reads a sample, returns numbers, and the
report card grades them locally.
