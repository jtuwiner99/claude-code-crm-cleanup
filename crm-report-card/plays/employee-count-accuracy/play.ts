// @ts-nocheck
/* eslint-disable */

// Employee-count accuracy: for each company, fetch a verified headcount and return
// it next to the stored one. This play FETCHES; it does not judge. The band
// comparison lives in the report card's Python scorer so the grading rule is
// covered by an offline test suite.
//
// Chain: domain -> LinkedIn company URL (icypeas_find_company_url) -> ONE
// batched scrape of every round-1 URL (apify_run_actor_sync, HarvestAPI's
// linkedin-company actor) -> identity check (deterministic registrable-domain
// match first, ai_inference on disagreement) -> verified employee count.
//
// FAILURE-TRIGGERED two-round waterfall (2026-07-28). Icypeas alone resolves
// the right company on ~92% of rows (first-hit accuracy measured at 91.9%
// against a 100-company benchmark), so the common case stays cheap: one
// icypeas call, one batched scrape, one identity check, done. Only the rows
// that FAIL round 1 (no URL, not scraped, or the identity check rejects it)
// get a second opinion from Exa in round 2 -- resolved, batch-scraped, and
// verified exactly the same way, but over a small alternate-candidate set
// instead of the whole book. Calling Exa on every row regardless of whether
// round 1 already succeeded would pay for 100 Exa calls to rescue roughly 8;
// this only pays for the ~8.
//
// This does NOT rescue a row that passes round 1's deterministic check
// against the WRONG company (a confidently-wrong website match): round 1
// only flags a row for round 2 when its OWN check fails, and a wrong website
// match does not fail that check. That is a known, accepted gap of this
// failure-triggered shape versus resolving both candidates up front; see
// play README / benchmark write-up for the tradeoff.
//
// Five phases, because both scrapes are batched and a per-row call would
// spawn one Apify actor run per company, which is explicitly not wanted:
//   1. a dataset that resolves an Icypeas LinkedIn URL per row
//   2. ONE tool call in the play body, outside any dataset, scraping every
//      round-1 URL at once
//   3. a dataset that checks identity per row against the round-1 batch
//      result and emits the verified count, or a pass/fail flag
//   4. (only if round 1 left any failures) a dataset that resolves an Exa
//      alternate candidate for the failed rows only, ONE tool call outside
//      any dataset scraping every distinct round-2 URL at once, and a
//      dataset that checks identity for those rows against the round-2
//      batch result
//   5. recombine: round-1 passes keep their round-1 result, round-1
//      failures take their round-2 result (or stay unverifiable)
//
// The registry's comparison_rule discloses what "verified" actually means:
// LinkedIn's associated-member count, not payroll headcount. See
// registry.json for the exact wording. That is an owner decision, not a bug.
//
// Restricted plays lib: no encodeURIComponent, no array/string .indexOf, no
// String.charAt. Substring checks below are split-based for that reason.

import { definePlay } from 'deepline';

// --- pure helpers: extracted verbatim by tests/test_play_domain_helpers.py.
// Keep this block free of any import/ctx dependency so it can be evaluated
// standalone; do not move these functions outside the markers below.

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

// True when the URL actually points at a LinkedIn company page, so a
// hallucinated Exa answer cannot spend a batch scrape slot on a URL that was
// never going to be scrapeable in the first place. Split-based containment
// test, no .indexOf, per the restricted plays lib.
function isLinkedInCompanyUrl(value: any): boolean {
  const text = String(value || '').trim().toLowerCase();
  if (!text) return false;
  return text.split('linkedin.com/company/').length > 1;
}

// Strip scheme, "www.", and any path or query, leaving a bare hostname.
function hostnameOnly(value: any): string {
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

// Common two-part public suffixes where the registrable domain is the last
// THREE labels, not the last two ("example.co.uk", not "co.uk"). A suffix
// missing from this list just means an extra ai_inference call on that row,
// which is the safe direction, so a small static list is correct here rather
// than a dependency.
const TWO_PART_PUBLIC_SUFFIXES = [
  'co.uk', 'com.au', 'co.nz', 'co.za', 'com.br', 'co.jp', 'com.mx', 'co.in',
];

// The registrable domain (eTLD+1), so a subdomain such as "get.stripe.com"
// compares equal to the registered domain "stripe.com" instead of failing
// the deterministic identity check and falling through to ai_inference.
function registrableDomain(value: any): string {
  const host = hostnameOnly(value);
  if (!host) return '';
  const labels = host.split('.');
  if (labels.length <= 2) return host;
  const lastTwo = labels.slice(-2).join('.');
  let suffixLabelCount = 2;
  for (const suffix of TWO_PART_PUBLIC_SUFFIXES) {
    if (suffix === lastTwo) {
      suffixLabelCount = 3;
      break;
    }
  }
  return labels.slice(-suffixLabelCount).join('.');
}

// "5001-10000" from { start: 5001, end: 10000 }, or empty when unavailable.
function formatRange(range: any): string {
  if (!range || typeof range !== 'object') return '';
  const start = range.start;
  const end = range.end;
  if (start === null || start === undefined || end === null || end === undefined) return '';
  return `${start}-${end}`;
}

// --- end pure helpers ---

export default definePlay(
  'crm-report-card-employee-count-accuracy',
  async (ctx: any, input: any) => {
    const rows = input.rows || [];

    // ---------------------------------------------------------------
    // Round 1: Icypeas only.
    // ---------------------------------------------------------------

    // Phase 1: resolve an Icypeas LinkedIn company URL per row. A provider
    // miss is not a failed row -- it just means no round-1 candidate.
    const resolved1 = await ctx
      .dataset('resolve', rows)
      .withColumn('icypeas_url', async (row: any) => {
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
          // Best effort: a provider miss is not a failed row.
        }
        return null;
      })
      .run({ key: 'record_id' });

    // Small and bounded (a report-card sample), so loading it into memory to
    // build the batch input and the later lookup is the documented escape
    // hatch, not a large-table anti-pattern.
    const resolvedRows1 = await resolved1.materialize();

    // Phase 2: ONE batch scrape of every round-1 URL, outside any dataset. A
    // static id keeps this replay-safe: a resume reuses the receipt instead
    // of re-scraping.
    const round1Urls: string[] = [];
    const round1Seen: Record<string, boolean> = {};
    for (const row of resolvedRows1) {
      const url = row.icypeas_url;
      if (!url) continue;
      const key = normalizeLinkedInUrl(url);
      if (key && !round1Seen[key]) {
        round1Seen[key] = true;
        round1Urls.push(url);
      }
    }

    // Shared scrape cache across BOTH rounds, keyed by normalized LinkedIn
    // URL, holding only compact scalars. Never persist the raw ~32KB-per-
    // company provider payload.
    const scrapedByUrl: Record<string, any> = {};

    function mergeScraped(items: any[]): void {
      for (const item of items) {
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
    }

    if (round1Urls.length > 0) {
      try {
        const batch = await ctx.tools.execute({
          id: 'harvestapi_company_batch_round1',
          description: 'Scrape LinkedIn company pages in one batch for every Icypeas URL resolved this run (round 1).',
          tool: 'apify_run_actor_sync',
          input: {
            actorId: 'harvestapi/linkedin-company',
            input: { companies: round1Urls },
          },
        });
        const raw = toolRaw(batch);
        mergeScraped(Array.isArray(raw) ? raw : []);
      } catch (err) {
        // Best effort: a batch miss leaves every round-1 row unscraped, not failed.
      }
    }

    // Identity check, shared by both rounds: deterministic registrable-domain
    // match first, ai_inference only on disagreement. Returns null when the
    // candidate does not pass (caller decides the identity_method label).
    async function checkIdentity(domain: string, company: any): Promise<
      { verified_employee_count: number | ''; source: string; verified_range: string; matchedByWebsite: boolean } | null
    > {
      const scrapedDomain = registrableDomain(company.website);
      const storedDomain = registrableDomain(domain);

      let verifiedIdentity = false;
      let matchedByWebsite = false;
      if (scrapedDomain && storedDomain && scrapedDomain === storedDomain) {
        verifiedIdentity = true;
        matchedByWebsite = true;
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
          }
        } catch (err) {
          // Best effort: an identity-check failure is not a verified match.
        }
      }

      if (!verifiedIdentity) return null;
      const employeeCount = toInt(company.employeeCount);
      return {
        verified_employee_count: employeeCount || '',
        source: employeeCount ? 'harvestapi via apify' : '',
        verified_range: formatRange(company.employeeCountRange),
        matchedByWebsite,
      };
    }

    // Phase 3: identity check per row against the round-1 batch result. A
    // row that fails is unverifiable FOR NOW, not a mismatch -- round 2 gets
    // a chance at it below.
    const verified1 = await ctx
      .dataset('verify', resolvedRows1)
      .withColumn('verification', async (row: any) => {
        const domain = String(row.domain || '').trim();
        const icypeasUrl = row.icypeas_url;

        if (!icypeasUrl) {
          return { passed: false, verified_employee_count: '', source: '', verified_range: '', identity_method: 'no-linkedin-url' };
        }

        const key = normalizeLinkedInUrl(icypeasUrl);
        const company = key ? scrapedByUrl[key] : null;
        if (!company) {
          return { passed: false, verified_employee_count: '', source: '', verified_range: '', identity_method: 'not-scraped' };
        }

        const match = await checkIdentity(domain, company);
        if (!match) {
          return { passed: false, verified_employee_count: '', source: '', verified_range: '', identity_method: 'ai-rejected' };
        }
        return {
          passed: true,
          verified_employee_count: match.verified_employee_count,
          source: match.source,
          verified_range: match.verified_range,
          identity_method: match.matchedByWebsite ? 'website-match:icypeas' : 'ai-verified:icypeas',
        };
      })
      .run({ key: 'record_id' });

    const verifiedRows1 = await verified1.materialize();

    // ---------------------------------------------------------------
    // Round 2: Exa alternate candidate, ONLY for round-1 failures. Skipped
    // entirely when round 1 left zero failures -- a clean book never pays
    // for a second batch.
    // ---------------------------------------------------------------

    const failedRows = verifiedRows1.filter((r: any) => !r.verification.passed);

    // record_id -> round-2 verification result, filled in only if round 2 runs.
    const round2ByRecordId: Record<string, any> = {};

    if (failedRows.length > 0) {
      // Phase 4a: resolve an Exa alternate candidate for the failed rows only.
      const resolved2 = await ctx
        .dataset('resolve_alt', failedRows)
        .withColumn('exa_url', async (row: any) => {
          const domain = String(row.domain || '').trim();
          if (!domain) return null;

          try {
            const exa = await ctx.tools.execute({
              id: 'exa_company_url_alternate',
              description: 'Resolve an alternate LinkedIn company page URL via Exa for a row that failed the Icypeas round, so it gets one second opinion instead of shipping wrong or staying unverifiable.',
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
            // Reject anything that is not actually a LinkedIn company page
            // before it can spend a batch scrape slot on a hallucinated URL.
            return url && isLinkedInCompanyUrl(url) ? String(url) : null;
          } catch (err) {
            // Best effort: a provider miss is not a failed row.
            return null;
          }
        })
        .run({ key: 'record_id' });

      const resolvedRows2 = await resolved2.materialize();

      // Phase 4b: ONE batch scrape of every DISTINCT round-2 URL -- distinct
      // from each other, from already-cached round-1 scrapes, AND from the
      // row's own (already-failed) Icypeas URL. If Exa just hands back the
      // same page Icypeas already gave us, there is nothing new to check: do
      // not re-scrape it, mark that row failed, and move on.
      const round2Urls: string[] = [];
      const round2Seen: Record<string, boolean> = {};
      for (const row of resolvedRows2) {
        const exaUrl = row.exa_url;
        if (!exaUrl) continue;
        const exaKey = normalizeLinkedInUrl(exaUrl);
        if (!exaKey) continue;
        const icypeasKey = row.icypeas_url ? normalizeLinkedInUrl(row.icypeas_url) : '';
        if (exaKey === icypeasKey) continue; // duplicate of the already-failed candidate
        if (scrapedByUrl[exaKey]) continue; // already scraped (round 1 or an earlier round-2 dedup)
        if (!round2Seen[exaKey]) {
          round2Seen[exaKey] = true;
          round2Urls.push(exaUrl);
        }
      }

      if (round2Urls.length > 0) {
        try {
          const batch = await ctx.tools.execute({
            id: 'harvestapi_company_batch_round2',
            description: 'Scrape LinkedIn company pages in one batch for every distinct Exa alternate URL resolved this run (round 2, only the rows that failed round 1).',
            tool: 'apify_run_actor_sync',
            input: {
              actorId: 'harvestapi/linkedin-company',
              input: { companies: round2Urls },
            },
          });
          const raw = toolRaw(batch);
          mergeScraped(Array.isArray(raw) ? raw : []);
        } catch (err) {
          // Best effort: a batch miss leaves every round-2 row unscraped, not failed.
        }
      }

      // Phase 4c: identity check per failed row against the round-2 batch
      // result (or the shared cache, for a candidate that happened to already
      // be scraped).
      const verified2 = await ctx
        .dataset('verify_alt', resolvedRows2)
        .withColumn('verification', async (row: any) => {
          const domain = String(row.domain || '').trim();
          const exaUrl = row.exa_url;
          const icypeasUrl = row.icypeas_url;

          if (!exaUrl) {
            // Exa found nothing either. "no-linkedin-url" only if Icypeas
            // never resolved anything to begin with; otherwise Icypeas DID
            // give us a (rejected) candidate, so this stays "ai-rejected".
            return {
              verified_employee_count: '', source: '', verified_range: '',
              identity_method: icypeasUrl ? 'ai-rejected' : 'no-linkedin-url',
            };
          }

          const exaKey = normalizeLinkedInUrl(exaUrl);
          const icypeasKey = icypeasUrl ? normalizeLinkedInUrl(icypeasUrl) : '';
          if (exaKey && icypeasKey && exaKey === icypeasKey) {
            // Same page Icypeas already gave us and that already failed --
            // do not re-check it, just mark it failed and move on.
            return { verified_employee_count: '', source: '', verified_range: '', identity_method: 'ai-rejected' };
          }

          const company = exaKey ? scrapedByUrl[exaKey] : null;
          if (!company) {
            return { verified_employee_count: '', source: '', verified_range: '', identity_method: 'ai-rejected' };
          }

          const match = await checkIdentity(domain, company);
          if (!match) {
            return { verified_employee_count: '', source: '', verified_range: '', identity_method: 'ai-rejected' };
          }
          return {
            verified_employee_count: match.verified_employee_count,
            source: match.source,
            verified_range: match.verified_range,
            identity_method: match.matchedByWebsite ? 'website-match:exa' : 'ai-verified:exa',
          };
        })
        .run({ key: 'record_id' });

      const verifiedRows2 = await verified2.materialize();
      for (const r of verifiedRows2) {
        round2ByRecordId[r.record_id] = r.verification;
      }
    }

    // ---------------------------------------------------------------
    // Recombine: round-1 passes keep their round-1 result; round-1 failures
    // take their round-2 result when round 2 ran, else stay exactly as round
    // 1 left them (unverifiable, not a mismatch).
    // ---------------------------------------------------------------

    return {
      rows: verifiedRows1.map((r: any) => {
        const verification = r.verification.passed
          ? r.verification
          : (round2ByRecordId[r.record_id] || r.verification);
        return {
          record_id: r.record_id,
          domain: r.domain,
          stored_employee_count: r.company_size,
          verified_employee_count: verification.verified_employee_count,
          source: verification.source,
          verified_range: verification.verified_range,
          identity_method: verification.identity_method,
        };
      }),
    };
  },
  {
    description:
      'Fetch a verified employee count per company domain via a LinkedIn-direct chain (Icypeas resolves round 1 for every row; only rows that fail round 1 get a round-2 Exa alternate candidate; each round is one batched HarvestAPI scrape plus an identity check) so the CRM Report Card can grade stored headcount accuracy. Read-only: never writes to a CRM.',
  },
);
