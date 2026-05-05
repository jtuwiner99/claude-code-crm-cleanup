# Deepline Reference Snapshots

Machine-readable ground truth for a scope compiler. Refresh via:

```bash
deepline workflows schema --subject all --json > deepline-schema.json
deepline tools list --json                      > deepline-tools.json
for t in run_javascript apollo_enrich_company peopledatalabs_company_search \
         crustdata_enrich_company deeplineagent \
         company_to_contact_by_role_waterfall name_and_domain_to_email_waterfall \
         person_linkedin_to_email_waterfall contact_to_phone_waterfall \
         search_contact engagers_to_icp_qualification leadmagic_profile_search \
         enrich_company apollo_people_search hunter_domain_search generic_http_request; do
  deepline tools get "$t" --json > "tools/${t}.json"
done
```

## Files

| File | What's in it |
|---|---|
| `deepline-schema.json` | Top-level playbook JSON Schema. `schemas.enrich_config` is what the compiler emits. |
| `deepline-tools.json` | Provider registry (44 integrations: apollo, pdl, crustdata, hunter, etc.). |
| `tools/*.json` | Per-tool schemas: `toolId`, `inputSchema`, `outputSchema`, `samples.request.payload`, `samples.response.payload`, `cost`, `categories`. The `samples` section is the best source for `extract_js` paths. |

## Playbook schema summary

Top-level: `{ version: number, commands: array, _comments?: array, _expansion_preview?: object }`.

Each `commands[]` item is one of two variants (via `anyOf`):

**Simple command:**
```json
{
  "alias": "string",
  "tool": "string",
  "operation": "string",
  "payload": { ... },
  "extract_js": "(output_data) => { ... }",
  "run_if_js": "return <boolean expression>;",
  "description": "string",
  "disabled": false
}
```
Required: `alias`, `tool`, `payload`.

**Waterfall block:**
```json
{
  "with_waterfall": "string",
  "commands": [ /* simple commands */ ],
  "min_results": 1,
  "description": "string"
}
```
Required: `with_waterfall`, `commands`.

## Templating

Payload strings and `run_if_js` / `extract_js` resolve `{{alias}}` and `{{alias.nested.path}}` against prior step outputs. `row.X` inside JS code refers to the current CSV row; `row.<alias>` refers to a prior command's output.

## Provider tools, tiered by frequency

**Tier 1 — core account waterfall (every run):**
- `apify_run_actor_sync` w/ `harvestapi/linkedin-company` — primary firmographic + LinkedIn-direct website + description (used for identity verification)
- `apollo_enrich_company` — fallback firmographic + LinkedIn URL when Harvest can't resolve from domain alone
- `peopledatalabs_company_search` — fallback firmographic
- `crustdata_enrich_company` — final fallback firmographic

**Tier 2 — AI synthesis (qualified rows only):**
- `deeplineagent` — gateway wrapper around Claude/GPT/Gemini. Use for classification, narrative summary, identity verification, structured extraction. Pass `jsonSchema` for enforced output.

**Tier 3 — people / contact discovery (optional per customer):**
- `company_to_contact_by_role_waterfall` — decision maker lookup (required: `roles`)
- `name_and_domain_to_email_waterfall` — work email (required: `first_name, last_name, domain`)
- `person_linkedin_to_email_waterfall` — email from LinkedIn URL
- `contact_to_phone_waterfall` — phone from identity
- `search_contact` — free sync contact search
- `leadmagic_profile_search` — LinkedIn URL → profile

**Tier 4 — local (free, always available):**
- `run_javascript` — normalize domains, derive booleans, inline qualification gates. Globals: `row`, `extract(tool, data, selector)`, `extractList(tool, data, selector)`.

## How a compiler uses these files

1. Load `deepline-schema.json` → build JSON schema validator; reject any emitted playbook that doesn't match.
2. Load `deepline-tools.json` + `tools/*.json` → whitelist of valid tool IDs; reject compile if recipe references an unknown tool.
3. Read `samples.request.payload` to validate payload shape; read `samples.response.payload` to generate `extract_js` paths.
4. Log any tool ID referenced in the recipe but missing from `tools/*.json` — prompt operator to refresh the reference.

## Related directives

- [`docs/best-practices/deepline-best-practices.md`](../docs/best-practices/deepline-best-practices.md) — opinionated rules for using these tools well, including the four CSV-to-hosted gotchas.
- [`docs/best-practices/provider-preferences.md`](../docs/best-practices/provider-preferences.md) — property-to-tool mapping with default waterfall orders.
