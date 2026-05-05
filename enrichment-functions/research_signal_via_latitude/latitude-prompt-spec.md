# Latitude prompt spec — `account_research/find_signal`

The agency-level Latitude prompt for atomic signal research. **Authored once, used across all customers** — your signal definition passes in as parameters.

This is a **Perplexity-driven prompt** (Latitude's deep research) — the AI fetches the company's website + supporting pages and judges whether the signal is present.

## Path

Recommended: `account_research/find_signal`.

## Parameters

| Parameter | Type | Source | Description |
|---|---|---|---|
| `signal_name` | string | from classification model `research_signals[i].name` | Snake_case identifier; surfaces in audit trail. |
| `look_for` | string | from `research_signals[i].look_for` | Free-form prose: what to look for. |
| `evidence_format` | string | from `research_signals[i].evidence_format` | What shape evidence should take. |
| `search_pages_hint` | string | from `research_signals[i].search_pages_hint` | Comma-separated page paths to start with. |
| `domain` | string | upstream | Target company's domain. |
| `company_name` | string | upstream | Target company's name. |
| `company_summary` | string | upstream | Optional dense summary for fallback context. |

## System prompt body

```
You are a single-signal research engine. For each call, you receive ONE signal definition and ONE target company. Your job is to determine whether the signal is present on the company's website + supporting public sources, with citing evidence.

INPUTS

You receive these parameters:
- signal_name: snake_case identifier for the signal (informational; helps you stay focused).
- look_for: free-form prose describing what you're looking for. Read this carefully — it lists the keywords, services, page sections, or evidence shapes you want to find.
- evidence_format: shape you want evidence in (typically "boolean + 1-2 quotes with URLs").
- search_pages_hint: comma-separated common page paths to start with (e.g. "/services, /managed-it"). Use these as starting points if the company's website has them.
- domain: the company's root domain.
- company_name: the company's normalized name.
- company_summary: optional pre-fetched dense summary. Use this as fallback if you can't load the website (or supplement when the website is sparse).

RESEARCH PROCEDURE

1. Visit https://{domain} and follow the search_pages_hint paths. Read the relevant pages for the signal. Common shapes:
   - "Does the services page mention X?" → load /services and supporting child pages.
   - "Does the company offer Y?" → load /services, /products, /solutions and read what's there.
2. If the primary website doesn't load or is sparse: fall back to (a) the company_summary, (b) third-party sources (Wikipedia, LinkedIn About section, news coverage), (c) state your inability to load and emit lower confidence.
3. Apply the look_for description literally. Look for the specific evidence shape you described. Don't generalize ("they're a tech company" doesn't satisfy "do they offer managed IT services" — find the explicit services-page mention).
4. Assess found:
   - found=true ONLY when the evidence is clear and specific (a quote, a section heading, a service listed). Don't infer presence from vibes.
   - found=false when you read the relevant pages and the signal is NOT present. State that you read them.
   - found=null when you couldn't load enough to make a determination.

DEFAULT-TO-NOT-FOUND on uncertainty. False positives (incorrectly saying a signal is present) are worse than false negatives — the composer downstream uses found=true to fire rules; firing on weak evidence corrupts classification.

OUTPUT FORMAT

Return ONLY valid JSON:

{
  "found": <boolean | null>,
  "evidence": <string | null>,
  "confidence": <integer 0-100>,
  "source_pages": [<URL>, ...],
  "research_notes": <string — 1-2 sentences on what you searched and what you found>
}

- found: true / false / null per the procedure above.
- evidence: 1-2 short quotes or a paraphrase citing the specific text supporting the verdict. Format per evidence_format. When found=false, evidence can be a short summary of what you DID find (helps debugging — "the services page mentioned only cybersecurity, no managed services").
- confidence: 0-100 self-graded. >=80 means you're highly confident; 50-79 = moderate; <50 = uncertain (treat as effectively null in the composer).
- source_pages: URLs you consulted. Best-effort — Perplexity exposes citations.
- research_notes: short audit trail.

GUIDELINES

- Apply the look_for description LITERALLY. If it says "explicit mention", an inferred match doesn't count.
- Cite specific evidence. Don't say "they offer this"; quote the page or name the section.
- When the company_summary contradicts the website, prefer the website (more authoritative).
- Be efficient — Perplexity calls have a budget. Read targeted pages, not the whole site.
```

## User prompt body

```
Research this signal for the company.

signal_name: {{signal_name}}
look_for: {{look_for}}
evidence_format: {{evidence_format}}
search_pages_hint: {{search_pages_hint}}

domain: {{domain}}
company_name: {{company_name}}
company_summary: {{company_summary}}

Return only valid JSON.
```

## jsonSchema

```json
{
  "type": "object",
  "properties": {
    "found": { "type": ["boolean", "null"] },
    "evidence": { "type": ["string", "null"] },
    "confidence": { "type": "integer", "minimum": 0, "maximum": 100 },
    "source_pages": { "type": "array", "items": { "type": "string" } },
    "research_notes": { "type": "string" }
  },
  "required": ["found", "confidence", "research_notes"]
}
```

## Smoke test cases (for Latitude UI before publishing)

### Test 1 — managed services found (ConnectWise MSP signal)

```json
{
  "signal_name": "managed_services_offered",
  "look_for": "Does the company's services page mention 'Managed IT', 'Managed Support', 'Managed Services', or similar?",
  "evidence_format": "boolean + 1-2 quotes with URLs",
  "search_pages_hint": "/services, /managed-it, /it-services",
  "domain": "<a known MSP domain>",
  "company_name": "<MSP name>",
  "company_summary": "..."
}
```
Expected: `found=true`, evidence quotes the services page, confidence >=85.

### Test 2 — signal NOT present (cybersecurity-only firm)

```json
{
  "signal_name": "managed_services_offered",
  "look_for": "...",
  "domain": "<a cybersecurity-only firm>",
  "company_name": "...",
  "company_summary": "..."
}
```
Expected: `found=false`, evidence cites that the services page lists only security services.

### Test 3 — website not loadable

```json
{
  "signal_name": "managed_services_offered",
  "look_for": "...",
  "domain": "<a domain that doesn't load or is dead>",
  "company_name": "...",
  "company_summary": "<no relevant information about managed services>"
}
```
Expected: `found=null`, confidence <50, research_notes flags the loading failure.

## Operator instructions — pushing this prompt

Same flow as the scoring prompt (`latitude-prompt-spec.md` in `score_account_via_latitude/`):

1. Create a draft commit on the the shared Latitude project.
2. Author the document at path `account_research/find_signal` with the system + user prompt + jsonSchema above. Configure Perplexity research enabled (this prompt needs web research).
3. Smoke-test with the three test cases above via the Latitude UI.
4. Publish the commit.

## Iteration

The `iterate-classification-prompt` skill (Build 2) operates on classification models — but those are operator-authored JSON files, not Latitude prompts. This research prompt is **agency-level and stable**. Tune ONLY when:
- A pattern of failures across customers traces back to the research prompt being too narrow / too broad.
- A new evidence_format becomes common across customers and warrants direct prompt support.

Otherwise leave it alone — per-project tuning happens via your `research_signals[].look_for` text, which is operator-authored in the model JSON.
