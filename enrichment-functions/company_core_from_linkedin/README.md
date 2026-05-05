# company_core_from_linkedin

Given a verified LinkedIn company URL, return canonical firmographics.

## Why this exists

Multiple downstream features (qualification gates, segmentation, routing) depend on consistent, accurate company-level fields: employee count, HQ country, industry, founded year. We standardize the extraction in one function so every pipeline reads the same shape.

## When to use

After `linkedin_url_verified` returns `verified=true`. Anywhere account-level firmographics are needed.

## When NOT to use

- The LinkedIn URL is unverified — running this on a wrong-company URL will quietly emit wrong firmographics.
- You only need a single field that the verification step already exposes (e.g. `harvest.website`) — just read it directly.

## Inputs / outputs

See `function.yaml` for the typed contract.

## Caching contract

If the caller passes `harvest_payload_cached` (typically `linkedin_url_verified.harvest_payload`), this function does NOT make a Harvest API call. Pass the cache; save the credit. The compiler should make this passthrough automatic when both functions are invoked in sequence — see open question in the top-level README.

## Gotchas

- **Employee count from LinkedIn is sometimes inflated** by counting all profile-affiliated members rather than current employees. For deal-routing thresholds (e.g. ≥50 employees gate), the noise floor is around ±10%. Don't build cliff-edge gates on a single LinkedIn count alone — combine with a second source (Crustdata, PDL) when the threshold is critical.
- **`headquarters.country` may be null** for very small or non-public companies. Downstream qualification logic that requires a country must handle null explicitly.
- **`founded_year` can be wrong** for rebrands or carve-outs (LinkedIn often shows the parent's founded year). Treat as informational, not authoritative.

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/company_core_from_linkedin.workflow.json)"
deepline workflows call --workflow-id <ID> --payload '{
  "linkedin_url": "https://linkedin.com/company/stripe"
}'
# Expect: employee_count populated, headquarters.country=US, industry=Financial Services, company_size_band="10001+"
```
