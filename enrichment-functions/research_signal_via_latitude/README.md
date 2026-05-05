# research_signal_via_latitude

Atomic research primitive: look for ONE specific signal on a target company's website and return whether it's present + supporting evidence. Routes through Latitude with Perplexity-driven research.

## Status: opt-in primitive (NOT default)

Spine-only. Not invoked directly by recipes — composers like `classify_via_research_agents` fan out to this once per signal.

**Use this function when:**

- You're building a composer (classification, scoring extension, contact-finder) that needs to find specific evidence on a company's website.
- The signal is well-scoped enough to express in a single prose `look_for` description.
- The signal is one of many — the composer does the rules-applying logic with synthesized signal evidence.

**Don't invoke directly:**

- For single-fact lookups, the existing `classify_via_latitude` (with Perplexity) is more cost-efficient.
- For multi-step research that requires reasoning across multiple findings, use `deeplineagent` with a richer prompt.

This function is the **atomic primitive** in the fan-out-then-compose pattern. It's intended to be called many times per row, each time looking for a different specific signal.

## Why this exists

ConnectWise's MSP detection (and similar signal-heavy classifications) needs:
1. Has the company explicitly listed managed IT services on their services page?
2. Has the company explicitly listed cybersecurity services?
3. Has the company explicitly listed printer / office supplies?

Three independent yes/no questions, each requiring evidence from a specific section of the website. The accuracy gain over a single research-and-classify prompt comes from FOCUS: each call has one job and uses its full Perplexity budget on it.

## Output shape

```json
{
  "found": <boolean | null>,
  "evidence": "Services page header reads 'Managed IT Services'; subsection lists 'Managed Support, Managed Network, Managed Security'.",
  "confidence": 90,
  "source_pages": ["https://example.com/services", "https://example.com/managed-it"],
  "research_notes": "Loaded /services and /managed-it. Both contain explicit 'Managed' service listings."
}
```

## Cost

One Latitude call per invocation. ~$0.005 with gpt-5-mini (gpt-4o-mini class). Default-to-not-found on failure.

## Pipeline placement (when invoked by a composer)

The composer fans out N parallel calls (one per signal) AFTER `company_summary_from_website` (which provides a fallback context). Each call is independent — Deepline can parallelize them within the row.

```
... default spine through company_summary_from_website ...
       ↓
research_signal_via_latitude × N (one per signal)
       ↓
classify_via_research_agents (composer applies rules to synthesized evidence)
       ↓
... downstream enrichment ...
```

## Smoke test

```bash
deepline workflows apply --payload "$(cat tmp/research_signal_via_latitude.workflow.json)"

# Test: managed services on a known MSP domain
deepline workflows call --workflow-id <ID> --payload '{
  "signal_name": "managed_services_offered",
  "look_for": "Does the company services page explicitly mention Managed IT, Managed Support, Managed Services?",
  "evidence_format": "boolean + 1-2 quotes with URLs",
  "search_pages_hint": "/services, /managed-it, /it-services",
  "domain": "<MSP-domain>",
  "company_name": "<MSP-name>",
  "latitude_api_key": "<key>"
}'
# Expect: found=true, evidence quotes services page, confidence>=85.
```

## Pointers

- Latitude prompt source: `latitude-prompt-spec.md` in this directory
- Composer that uses this: `enrichment-functions/classify_via_research_agents/`
- Schema for signal definitions: `wiki/classification-research-signals-schema.md`
- Classification catalog: `skills/enrichment-functions-catalog/SKILL.md`
