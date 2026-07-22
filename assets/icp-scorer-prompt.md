# ICP scorer prompt (AI baseline)

Use this prompt when you (the model) are asked to produce the `ai_baseline` block
for a CRM Report Card run. This is Step 4 of `SKILL.md`. It is a single pass over
a small CSV sample: a rough guess, not a measurement. Never present it as more
than that.

## Inputs you will be given

1. The natural-language ICP the user described in intake (verbatim).
2. A sample of the loaded CSV rows (roughly 20 to 50 rows is enough; do not read
   the whole export into context).

## What to do

1. Read the natural-language ICP and derive a short, explicit set of qualifying
   rules from it in your own words (for example: "US-based", "50 to 500
   employees", "SaaS or software category", "has a filled company_size"). Write
   these rules down before you score anything, so the scoring is at least
   internally consistent even though it is still unverified.
2. Go row by row through the sample and mark each record qualified or not
   qualified against your derived rules. If a field needed to judge a rule is
   missing or blank, treat that row as not qualified rather than guessing.
3. Compute `qualified_estimate` as the fraction of sampled rows you marked
   qualified, as a float between 0.0 and 1.0.
4. Write `reasons`: a non-empty list of short strings. These reasons must be
   framed around the missing rigor behind the number, never around measured
   accuracy. Always include something equivalent to each of the following
   three ideas, in your own words:
   - No evidence grounding: the ICP rules were applied by reading text, not by
     verifying each row against a real source (no enrichment, no lookups).
   - No test bench: there is no locked, human-reviewed definition of "qualified"
     for this ICP to compare against, so there is nothing to score this guess
     against.
   - No production QA: this number has not gone through any review pass, so
     treat it as a rough directional guess, not a report.
   Do not write a reason like "high confidence" or "verified against records".
   That claim is false for this step.
5. Set `sample_size` to the number of rows you actually scored (an int).
6. Output exactly this shape (no other keys, no prose outside the object):

```json
{
  "qualified_estimate": 0.35,
  "reasons": [
    "single-pass read of a small CSV sample, no evidence grounding per row",
    "no test bench or locked definition for this ICP yet",
    "no production QA pass; treat as a rough directional guess only"
  ],
  "sample_size": 40
}
```

## Hard rules

- Never set or imply `verified: true`. The pipeline's `validate_ai_baseline`
  forces `verified` to `False` regardless of what you write, but do not write
  a `reasons` entry that claims otherwise either.
- Never claim a measured accuracy figure ("this is accurate to within X%").
  There is no ground truth to measure against at this step.
- Keep `qualified_estimate` a plain float in `[0.0, 1.0]`, not a percentage
  string, not a boolean.
- If the sample is too small or too messy to say anything useful, it is fine
  for `qualified_estimate` to be a rough midpoint estimate. Say so plainly in
  `reasons` rather than inventing false precision.
