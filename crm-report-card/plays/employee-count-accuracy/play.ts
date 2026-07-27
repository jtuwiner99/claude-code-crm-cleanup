// @ts-nocheck
/* eslint-disable */

// Employee-count accuracy: for each company, fetch a verified headcount and return
// it next to the stored one. This play FETCHES; it does not judge. The band
// comparison lives in the report card's Python scorer so the grading rule is
// covered by an offline test suite.
//
// Chain: domain -> LinkedIn company URL (icypeas_find_company_url, falling back
// to exa_answer on a miss) -> ONE batched scrape of every resolved URL
// (apify_run_actor_sync, HarvestAPI's linkedin-company actor) -> identity check
// (deterministic domain match first, ai_inference only on disagreement) ->
// verified employee count.
//
// Three phases, because the scrape is batched and a per-row call would spawn
// one Apify actor run per company, which is explicitly not wanted:
//   1. a dataset that resolves a LinkedIn URL per row
//   2. ONE tool call in the play body, outside any dataset, scraping every
//      resolved URL at once
//   3. a dataset that checks identity per row against the batch result and
//      emits the verified count
//
// The registry's comparison_rule discloses what "verified" actually means:
// LinkedIn's associated-member count, not payroll headcount. See
// registry.json for the exact wording. That is an owner decision, not a bug.
//
// Restricted plays lib: no encodeURIComponent, no array/string .indexOf, no
// String.charAt. Substring checks below are split-based for that reason.

import { definePlay } from 'deepline';

function toolRaw(result: any): any {
  if (result == null) return null;
  return result.toolResponse?.raw ?? result.toolResponse ?? result.toolOutput?.raw ?? result;
}

function toInt(value: any): number | null {
  if (value === null || value === undefined || value === '') return null;
  const n = Math.round(Number(String(value).split(',').join('')));
  if (!isFinite(n) || n <= 0) return null;
  return n;
}

// Lowercase, drop a "www." prefix, drop a trailing slash. The URL we send to
// the scraper and the URL it echoes back can differ in exactly these ways.
function normalizeLinkedInUrl(value: any): string {
  let url = String(value || '').trim().toLowerCase();
  if (!url) return '';
  if (url.slice(-1) === '/') {
    url = url.slice(0, -1);
  }
  const schemeSplit = url.split('://');
  if (schemeSplit.length === 2) {
    const scheme = schemeSplit[0];
    let rest = schemeSplit[1];
    if (rest.split('www.')[0] === '') {
      rest = rest.slice(4);
    }
    url = scheme + '://' + rest;
  }
  return url;
}

// Strip scheme, "www.", and any path or query, so a stored bare domain and a
// scraped full website URL compare equal when they name the same company.
function domainOnly(value: any): string {
  let text = String(value || '').trim().toLowerCase();
  if (!text) return '';
  const schemeSplit = text.split('://');
  let rest = schemeSplit.length === 2 ? schemeSplit[1] : text;
  rest = rest.split('/')[0];
  rest = rest.split('?')[0];
  if (rest.split('www.')[0] === '') {
    rest = rest.slice(4);
  }
  return rest;
}

// "5001-10000" from { start: 5001, end: 10000 }, or empty when unavailable.
function formatRange(range: any): string {
  if (!range || typeof range !== 'object') return '';
  const start = range.start;
  const end = range.end;
  if (start === null || start === undefined || end === null || end === undefined) return '';
  return `${start}-${end}`;
}

export default definePlay(
  'crm-report-card-employee-count-accuracy',
  async (ctx: any, input: any) => {
    const rows = input.rows || [];

    // Phase 1: resolve a LinkedIn company URL per row. Icypeas first, Exa as
    // the fallback on a miss. Folded into one column returning the URL string
    // or null; a provider miss is not a failed row.
    const resolved = await ctx
      .dataset('resolve', rows)
      .withColumn('linkedin_url', async (row: any) => {
        const domain = String(row.domain || '').trim();
        if (!domain) return null;

        try {
          const icypeas = await ctx.tools.execute({
            id: 'icypeas_company_url',
            description: 'Resolve the LinkedIn company page URL for this domain via Icypeas.',
            tool: 'icypeas_find_company_url',
            input: { companyOrDomain: domain },
          });
          const raw = toolRaw(icypeas) || {};
          if (raw.status === 'FOUND' && raw.result) {
            return String(raw.result);
          }
        } catch (err) {
          // Best effort: fall through to the Exa fallback.
        }

        try {
          const exa = await ctx.tools.execute({
            id: 'exa_company_url_fallback',
            description: 'Fall back to Exa to find the LinkedIn company page URL when Icypeas misses.',
            tool: 'exa_answer',
            input: {
              query: `What is the LinkedIn company page URL for the company at ${domain}?`,
              text: true,
              outputSchema: {
                type: 'object',
                properties: {
                  linkedin_url: { type: 'string' },
                },
                required: ['linkedin_url'],
              },
            },
          });
          const raw = toolRaw(exa) || {};
          const answer = raw.answer || {};
          const url = answer.linkedin_url;
          return url ? String(url) : null;
        } catch (err) {
          // Best effort: a provider miss is not a failed row.
          return null;
        }
      })
      .run({ key: 'record_id' });

    // Small and bounded (a report-card sample), so loading it into memory to
    // build the batch input and the later lookup is the documented escape
    // hatch, not a large-table anti-pattern.
    const resolvedRows = await resolved.materialize();

    // Phase 2: ONE batch scrape of every resolved URL, outside any dataset.
    // A static id keeps this replay-safe: a resume reuses the receipt instead
    // of re-scraping.
    const urlsToScrape = resolvedRows
      .map((r: any) => r.linkedin_url)
      .filter((url: any) => !!url);

    let scraped: any[] = [];
    if (urlsToScrape.length > 0) {
      try {
        const batch = await ctx.tools.execute({
          id: 'harvestapi_company_batch',
          description: 'Scrape LinkedIn company pages in one batch for every URL resolved this run.',
          tool: 'apify_run_actor_sync',
          input: {
            actorId: 'harvestapi/linkedin-company',
            input: { companies: urlsToScrape },
          },
        });
        const raw = toolRaw(batch);
        scraped = Array.isArray(raw) ? raw : [];
      } catch (err) {
        // Best effort: a batch miss leaves every row unscraped, not failed.
        scraped = [];
      }
    }

    // Lookup keyed by normalized linkedinUrl, holding only compact scalars.
    // Never persist the raw ~32KB-per-company provider payload.
    const scrapedByUrl: Record<string, any> = {};
    for (const item of scraped) {
      const key = normalizeLinkedInUrl(item && item.linkedinUrl);
      if (!key) continue;
      scrapedByUrl[key] = {
        website: item.website,
        employeeCount: item.employeeCount,
        employeeCountRange: item.employeeCountRange,
        name: item.name,
        tagline: item.tagline,
        companyType: item.companyType,
        foundedYear: item.foundedOn && item.foundedOn.year,
      };
    }

    // Phase 3: identity check per row against the batch result, deterministic
    // domain match first, ai_inference only when that fails. A row that fails
    // the identity check is unverifiable, not a mismatch: we could not confirm
    // we were looking at the right company.
    const verified = await ctx
      .dataset('verify', resolvedRows)
      .withColumn('verification', async (row: any) => {
        const domain = String(row.domain || '').trim();
        const linkedinUrl = row.linkedin_url;

        if (!linkedinUrl) {
          return { verified_employee_count: '', source: '', verified_range: '', identity_method: 'no-linkedin-url' };
        }

        const key = normalizeLinkedInUrl(linkedinUrl);
        const company = key ? scrapedByUrl[key] : null;
        if (!company) {
          return { verified_employee_count: '', source: '', verified_range: '', identity_method: 'not-scraped' };
        }

        const scrapedDomain = domainOnly(company.website);
        const storedDomain = domainOnly(domain);

        let verifiedIdentity = false;
        let identityMethod = '';

        if (scrapedDomain && storedDomain && scrapedDomain === storedDomain) {
          verifiedIdentity = true;
          identityMethod = 'website-match';
        } else {
          try {
            const prompt = `Is the company below the same company that owns the domain "${domain}"? `
              + `Name: ${company.name || 'unknown'}. Website: ${company.website || 'unknown'}. `
              + `Tagline: ${company.tagline || 'none'}. Type: ${company.companyType || 'unknown'}. `
              + `Founded: ${company.foundedYear || 'unknown'}. Answer with a single word, YES or NO.`;
            const result = await ctx.tools.execute({
              id: 'ai_identity_check',
              description: 'Ask the model whether the scraped LinkedIn company is the same company as the stored domain.',
              tool: 'ai_inference',
              input: { model: 'openai/gpt-5.4-mini', prompt },
            });
            const raw = toolRaw(result) || {};
            const answer = String(raw.output || '').trim().toUpperCase();
            if (answer === 'YES') {
              verifiedIdentity = true;
              identityMethod = 'ai-verified';
            } else {
              // Anything not clearly YES counts as not verified.
              identityMethod = 'ai-rejected';
            }
          } catch (err) {
            // Best effort: an identity-check failure is not a verified match.
            identityMethod = 'ai-rejected';
          }
        }

        if (!verifiedIdentity) {
          return { verified_employee_count: '', source: '', verified_range: '', identity_method: identityMethod };
        }

        const employeeCount = toInt(company.employeeCount);
        return {
          verified_employee_count: employeeCount || '',
          source: employeeCount ? 'harvestapi via apify' : '',
          verified_range: formatRange(company.employeeCountRange),
          identity_method: identityMethod,
        };
      })
      .run({ key: 'record_id' });

    // Lean return: one compact row per record, no raw provider payloads.
    return {
      rows: verified.map((r: any) => ({
        record_id: r.record_id,
        domain: r.domain,
        stored_employee_count: r.company_size,
        verified_employee_count: r.verification.verified_employee_count,
        source: r.verification.source,
        verified_range: r.verification.verified_range,
        identity_method: r.verification.identity_method,
      })),
    };
  },
  {
    description:
      'Fetch a verified employee count per company domain via a LinkedIn-direct chain (Icypeas or Exa to resolve the company URL, one batched HarvestAPI scrape, then an identity check) so the CRM Report Card can grade stored headcount accuracy. Read-only: never writes to a CRM.',
  },
);
