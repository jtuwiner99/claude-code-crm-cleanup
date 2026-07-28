// @ts-nocheck
/* eslint-disable */

// Employee-count accuracy: for each company, fetch a verified headcount and return
// it next to the stored one. This play FETCHES; it does not judge. The band
// comparison lives in the report card's Python scorer so the grading rule is
// covered by an offline test suite.
//
// Chain: domain -> LinkedIn company URL (exa_answer) -> ONE batched scrape of
// every resolved URL (apify_run_actor_sync, HarvestAPI's linkedin-company
// actor) -> identity check (deterministic registrable-domain match, GATED by
// a name-corroboration guard, then ai_inference on disagreement or on a
// website match the name does not corroborate) -> verified employee count.
//
// SINGLE-RESOLVER (2026-07-28, replaces the two-round icypeas+exa waterfall).
// Measured across a 100-company benchmark against hand-confirmed ground
// truth: exa_answer alone resolves 98/100 correctly (24/24 hard, 25/25
// well-known, 49/50 mid-market), icypeas alone resolves 92/100, and the old
// two-round waterfall (icypeas first, exa as a round-2 rescue for round-1
// failures) resolved 96/100 as a whole. Of the disagreements, exa was right
// and icypeas wrong on 6 rows; icypeas was never right where exa was wrong.
// Exa alone beat the entire waterfall while costing half of what the
// waterfall's own first step (icypeas) cost by itself. There is no case in
// the data for calling a second, cheaper-but-worse provider once a better one
// is already resolving every row, so the round-2 rescue is gone entirely:
// no second resolver, no second batched scrape, no merge step. That removes
// the exact code that produced two separate data-loss bugs in the old
// waterfall (a dataset column-name collision between round 1's and round 2's
// verification columns, and a return that truncated 100 rows to 20) by
// deleting the code path they lived in, not by patching around it.
//
// NAME CORROBORATION GUARD (2026-07-28, unchanged by the single-resolver
// switch -- it guards a wrong candidate regardless of which resolver
// produced it). A website match alone answers "does this LinkedIn page claim
// this website," not "is this the right company" -- a parent and its
// regional pages, or an old legal entity that migrated its domain forward,
// can all legitimately claim the same website (measured: intercom.com ->
// intercom-latinamerica, chorus.ai -> affectlayer-inc, clay.com ->
// grow-with-clay, all website-matched, all wrong). checkIdentity requires the
// LinkedIn slug/name to actually carry the domain's brand before the website
// match is trusted; a match whose name does not corroborate is escalated to
// ai_inference rather than auto-accepted or silently shipped wrong. See
// nameCorroboratesDomain in the pure-helpers block. Deliberately NOT applied
// by running ai_inference on every row: the verifier has its own measured
// false-refusal (outreach.io, confirmed correct by URL ground truth and two
// independent providers, still rejected), so the escalation stays narrow to
// keep clean rows away from it.
//
// Three phases, because the scrape is batched and a per-row call would spawn
// one Apify actor run per company, which is explicitly not wanted:
//   1. a dataset that resolves an Exa LinkedIn URL per row
//   2. ONE tool call in the play body, outside any dataset, scraping every
//      resolved URL at once
//   3. a dataset that checks identity per row against the batch result and
//      emits the verified count, or a pass/fail flag; the flat output rows
//      are then persisted as their own durable dataset and that HANDLE is
//      returned, never a materialized array
//
// The registry's comparison_rule discloses what "verified" actually means:
// LinkedIn's associated-member count, not payroll headcount. See
// registry.json for the exact wording. That is an owner decision, not a bug.
//
// Restricted plays lib: no encodeURIComponent, no array/string .indexOf, no
// String.charAt. Substring checks below are split-based for that reason.

import { definePlay } from 'deepline';

// --- pure helpers: extracted verbatim by tests/test_play_domain_helpers.py,
// tests/test_play_name_corroboration.py, and tests/test_play_output_rows.py.
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

// The bare brand label of a domain: "clay.com" -> "clay", "example.co.uk" ->
// "example". Built on registrableDomain so a two-part public suffix still
// leaves just the brand, not the suffix's first label.
function brandLabel(domain: any): string {
  const reg = registrableDomain(domain);
  if (!reg) return '';
  return reg.split('.')[0];
}

// The slug segment of a LinkedIn company URL: ".../company/intercom-latinamerica/..."
// -> "intercom-latinamerica". Empty when the URL does not contain that path.
function linkedInSlug(url: any): string {
  const text = String(url || '').trim().toLowerCase();
  if (!text) return '';
  const parts = text.split('linkedin.com/company/');
  if (parts.length < 2) return '';
  let rest = parts[1];
  rest = rest.split('/')[0];
  rest = rest.split('?')[0];
  return rest;
}

// Split on the delimiters a domain label or LinkedIn slug actually uses
// (hyphen, underscore, dot, space), lowercase, drop empty pieces. Chained
// split/join instead of a regex or delimiter array; restricted plays lib
// only forbids .indexOf/.charAt/encodeURIComponent, not this.
function tokenize(value: any): string[] {
  let text = String(value || '').trim().toLowerCase();
  if (!text) return [];
  text = text.split('-').join(' ').split('_').join(' ').split('.').join(' ');
  const pieces = text.split(' ');
  const tokens: string[] = [];
  for (const piece of pieces) {
    if (piece) tokens.push(piece);
  }
  return tokens;
}

function tokenInList(token: string, list: string[]): boolean {
  for (const item of list) {
    if (item === token) return true;
  }
  return false;
}

// Assemble the final per-company output rows from the verify dataset's
// materialized rows. Extracted as its own named function -- rather than
// inlined in the play body -- so a test can assert the exact row shape
// handed to `ctx.dataset('output', ...)` without needing a live ctx. This
// function only decides WHAT the output rows look like; it is deliberately
// silent on HOW they get returned (materialized array vs. durable dataset
// handle) -- that is a separate concern, guarded by a separate source-level
// test, because a past regression got a shape like this right and still
// shipped truncated output by wrapping it in `.map(...)` and returning a
// plain array instead of a dataset handle.
function buildOutputRows(verifiedRows: any[]): any[] {
  return verifiedRows.map((r: any) => ({
    record_id: r.record_id,
    domain: r.domain,
    stored_employee_count: r.company_size,
    verified_employee_count: r.verification.verified_employee_count,
    source: r.verification.source,
    verified_range: r.verification.verified_range,
    verified_linkedin_url: r.verification.verified_linkedin_url,
    identity_method: r.verification.identity_method,
  }));
}

// Legal-entity suffixes that show up on plenty of genuinely-correct LinkedIn
// pages ("acme-inc" for domain "acme.com"). Filtered out of the "extra
// token" count below so spelling out a corporate suffix does not by itself
// trigger an escalation. This is NOT a list of things that excuse a
// mismatch -- an unlisted extra token (a region qualifier, a rebrand
// fragment, an unrelated word) still fails corroboration.
const BENIGN_LEGAL_SUFFIXES = [
  'inc', 'incorporated', 'llc', 'ltd', 'limited', 'corp', 'corporation',
  'co', 'group', 'holding', 'holdings', 'gmbh', 'plc',
];

// NAME CORROBORATION GUARD. The website-match fast path answers "does this
// LinkedIn page claim this website," which several different pages can
// legitimately claim at once: a parent and its regional pages, or an old
// legal entity whose domain migrated forward with it. This asks the
// narrower question the fast path skips: does the LinkedIn page's own
// name/slug actually carry the domain's brand, with nothing else riding
// along that would explain a DIFFERENT entity --
//   - a region ("intercom.com" -> "intercom-latinamerica")
//   - a former legal name ("chorus.ai" -> "affectlayer-inc", zero shared token)
//   - an unrelated rebrand fragment ("clay.com" -> "grow-with-clay")
//
// Returns true (corroborates, fast path stands) only when the brand token
// is present AND every other token is either absent or a benign legal
// suffix. Returns false -- caller escalates to ai_inference instead of
// auto-accepting -- when the brand token is missing entirely, or when an
// unexplained extra token rides along with it.
function nameCorroboratesDomain(domain: any, company: any, linkedinUrl: any): boolean {
  const brandTokens = tokenize(brandLabel(domain));
  if (brandTokens.length === 0) return true; // nothing to check the name against

  let candidateTokens = tokenize(linkedInSlug(linkedinUrl));
  if (candidateTokens.length === 0) {
    candidateTokens = tokenize(company && company.name);
  }
  if (candidateTokens.length === 0) return true; // nothing to corroborate or refute with

  let overlapFound = false;
  const extraTokens: string[] = [];
  for (const token of candidateTokens) {
    if (tokenInList(token, brandTokens)) {
      overlapFound = true;
    } else if (!tokenInList(token, BENIGN_LEGAL_SUFFIXES)) {
      extraTokens.push(token);
    }
  }

  return overlapFound && extraTokens.length === 0;
}

// --- end pure helpers ---

export default definePlay(
  'crm-report-card-employee-count-accuracy',
  async (ctx: any, input: any) => {
    const rows = input.rows || [];

    // Phase 1: resolve an Exa LinkedIn company URL per row. A provider miss
    // is not a failed row -- it just means no candidate to scrape.
    //
    // Prompt and outputSchema are ported verbatim from the 100-company
    // benchmark run that measured 98/100 correct. Deploying a different
    // phrasing would mean deploying something unmeasured.
    const resolved = await ctx
      .dataset('resolve', rows)
      .withColumn('linkedin_url', async (row: any) => {
        const domain = String(row.domain || '').trim();
        if (!domain) return null;

        try {
          const exa = await ctx.tools.execute({
            id: 'exa_company_url',
            description: 'Resolve the official LinkedIn company page URL for this domain via Exa.',
            tool: 'exa_answer',
            input: {
              query: `What is the official LinkedIn company page URL for the company at ${domain}? Return the primary global company page, not a regional, subsidiary, or legacy page.`,
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
        }
        return null;
      })
      .run({ key: 'record_id' });

    // Small and bounded (a report-card sample), so loading it into memory to
    // build the batch input and the later lookup is the documented escape
    // hatch, not a large-table anti-pattern.
    const resolvedRows = await resolved.materialize();

    // Phase 2: ONE batch scrape of every resolved URL, outside any dataset.
    // A static id keeps this replay-safe: a resume reuses the receipt
    // instead of re-scraping.
    const urls: string[] = [];
    const urlsSeen: Record<string, boolean> = {};
    for (const row of resolvedRows) {
      const url = row.linkedin_url;
      if (!url) continue;
      const key = normalizeLinkedInUrl(url);
      if (key && !urlsSeen[key]) {
        urlsSeen[key] = true;
        urls.push(url);
      }
    }

    // Keyed by normalized LinkedIn URL, holding only compact scalars. Never
    // persist the raw ~32KB-per-company provider payload.
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

    if (urls.length > 0) {
      try {
        const batch = await ctx.tools.execute({
          id: 'harvestapi_company_batch',
          description: 'Scrape LinkedIn company pages in one batch for every Exa URL resolved this run.',
          tool: 'apify_run_actor_sync',
          input: {
            actorId: 'harvestapi/linkedin-company',
            input: { companies: urls },
          },
        });
        const raw = toolRaw(batch);
        mergeScraped(Array.isArray(raw) ? raw : []);
      } catch (err) {
        // Best effort: a batch miss leaves every row unscraped, not failed.
      }
    }

    // Identity check: deterministic registrable-domain match first, gated by
    // the name-corroboration guard, ai_inference on disagreement OR on a
    // website match the name does not corroborate. `path` tells the caller
    // which of the three ways this was decided, so it can label
    // identity_method precisely instead of collapsing a name-escalated
    // result into the plain website-match or plain ai labels.
    async function checkIdentity(domain: string, company: any, linkedinUrl: any): Promise<
      {
        verified: boolean;
        verified_employee_count: number | '';
        source: string;
        verified_range: string;
        verified_linkedin_url: string;
        path: 'website' | 'website-escalated' | 'ai';
      }
    > {
      const scrapedDomain = registrableDomain(company.website);
      const storedDomain = registrableDomain(domain);
      const websiteMatches = Boolean(scrapedDomain && storedDomain && scrapedDomain === storedDomain);

      let verifiedIdentity = false;
      let path: 'website' | 'website-escalated' | 'ai';

      if (websiteMatches && nameCorroboratesDomain(domain, company, linkedinUrl)) {
        verifiedIdentity = true;
        path = 'website';
      } else {
        path = websiteMatches ? 'website-escalated' : 'ai';
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

      const employeeCount = verifiedIdentity ? toInt(company.employeeCount) : null;
      return {
        verified: verifiedIdentity,
        verified_employee_count: verifiedIdentity ? (employeeCount || '') : '',
        source: verifiedIdentity && employeeCount ? 'harvestapi via apify' : '',
        verified_range: verifiedIdentity ? formatRange(company.employeeCountRange) : '',
        verified_linkedin_url: verifiedIdentity ? normalizeLinkedInUrl(linkedinUrl) : '',
        path,
      };
    }

    // Phase 3: identity check per row against the batch result. A row that
    // fails is unverifiable, not a mismatch.
    const verified = await ctx
      .dataset('verify', resolvedRows)
      .withColumn('verification', async (row: any) => {
        const domain = String(row.domain || '').trim();
        const linkedinUrl = row.linkedin_url;

        if (!linkedinUrl) {
          return { passed: false, verified_employee_count: '', source: '', verified_range: '', verified_linkedin_url: '', identity_method: 'no-linkedin-url' };
        }

        const key = normalizeLinkedInUrl(linkedinUrl);
        const company = key ? scrapedByUrl[key] : null;
        if (!company) {
          return { passed: false, verified_employee_count: '', source: '', verified_range: '', verified_linkedin_url: '', identity_method: 'not-scraped' };
        }

        const match = await checkIdentity(domain, company, linkedinUrl);
        if (!match.verified) {
          return {
            passed: false, verified_employee_count: '', source: '', verified_range: '', verified_linkedin_url: '',
            identity_method: match.path === 'website-escalated' ? 'website-match-name-escalated:ai-rejected' : 'ai-rejected',
          };
        }
        return {
          passed: true,
          verified_employee_count: match.verified_employee_count,
          source: match.source,
          verified_range: match.verified_range,
          verified_linkedin_url: match.verified_linkedin_url,
          identity_method:
            match.path === 'website' ? 'website-match'
            : match.path === 'website-escalated' ? 'website-match-name-escalated:ai-verified'
            : 'ai-verified',
        };
      })
      .run({ key: 'record_id' });

    const verifiedRows = await verified.materialize();

    const outputRows = buildOutputRows(verifiedRows);

    // Persist the merged rows as their own durable dataset and return THAT
    // HANDLE, not a materialized array. A plain array is exactly what
    // shipped here before -- correct in every unit test and in `deepline
    // plays check`, but the Deepline runtime caps a play's inline return
    // payload (the run-event document has a size limit), so on a real
    // 100-row run it silently truncated to the first 20 rows.
    // `ctx.dataset(...).run(...)` persists every row to a durable table with
    // no such cap; returning the handle WITHOUT calling `.materialize()` on
    // it keeps `rows` a dataset reference (`isDataset: true` in `deepline
    // plays check`'s output), so `deepline runs export --dataset result.rows`
    // retrieves all 100 rows regardless of sample size. No provider call
    // here -- this is a plain data-shaping dataset, so the one-batched-
    // Apify-call ceiling is untouched.
    const output = await ctx
      .dataset('output', outputRows)
      .run({ key: 'record_id' });

    return { rows: output };
  },
  {
    description:
      'Fetch a verified employee count per company domain via a LinkedIn-direct chain (exa_answer resolves the LinkedIn company URL for every row, one batched HarvestAPI scrape, then an identity check) so the CRM Report Card can grade stored headcount accuracy. Read-only: never writes to a CRM.',
  },
);
