# Employee-count accuracy

Checks whether the employee count stored on your company records is actually
right, by fetching a verified headcount for each domain and comparing bands.

**What it unlocks:** the "Employee-count accuracy, verified vs stored" row on
the report card.

**What it needs:** a companies export with a domain column and an employee-count
column. Records with a blank stored count are skipped, because a blank is a
completeness problem the free scan already grades.

**Providers:** PeopleDataLabs first (exact count, billed only when it matches),
then Exa for anything PeopleDataLabs misses. Both are Deepline-native and
billed to your own Deepline account with credits. There is no key to set up.

**What it costs:** at most $0.14 per matched record, so at most $14 for the
default 100-record sample. That figure is a ceiling: PeopleDataLabs bills only
on a match, so every miss costs nothing and a real run usually lands under it.

**What "wrong" means:** stored and verified fall two or more size bands apart.
Off by a little is not counted as an error. Bands are 1-10, 11-50, 51-200,
201-500, 501-1000, 1001-5000, 5001-10000, 10001+.

**It never writes to your CRM.** It reads a sample, returns numbers, and the
report card grades them locally.
