# normalize_domain_and_name

Clean a raw domain and (optionally) discover or normalize a company name.

## When to use

The first step of nearly every account-level enrichment pipeline. Anywhere a downstream step needs a clean root domain or a clean company name as input, run this first.

## When NOT to use

- You already have a clean domain and don't need a name normalization (just inline the JS, don't pull in the function).
- You need entity-resolution-quality matching (this function is normalization, not resolution — it doesn't do "is this the same company as that company").

## Inputs / outputs

See `function.yaml` for the typed contract.

## Implementation notes

- Domain normalization is deterministic — pure JS, no external calls.
- Name normalization branches on whether the caller passed a raw name. If yes, deterministic JS strips legal suffixes. If no, a single cheap AI web-research call (deeplineagent) discovers the name from the domain.
- The `name_source` output lets the caller audit which path ran without re-deriving it.

## Gotchas

- **Don't pass `domain_raw` containing a path you actually want preserved.** This function trims everything after the first `/`. If you need a full URL preserved alongside, pass it as a separate field.
- **The AI-discovered name may be wrong for very small / unknown companies.** Combine with the LinkedIn verification function downstream before trusting it.
- **`record_id` passthrough** is the simplest way to keep CRM-bound runs correlated end-to-end. Always pass it when calling from a CRM-triggered workflow.

## Smoke test

```bash
# After commands.jsonc is filled in:
deepline workflows apply --payload "$(cat tmp/normalize_domain_and_name.workflow.json)"
deepline workflows call --workflow-id <ID> --payload '{"domain_raw":"https://www.Stripe.com/atlas","company_name_raw":"Stripe, Inc."}'
# Expect: domain_clean=stripe.com, company_name_clean=Stripe, name_source=input
```
