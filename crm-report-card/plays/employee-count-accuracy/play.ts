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
// match, GATED by a name-corroboration guard, then ai_inference on
// disagreement or on a website match the name does not corroborate) ->
// verified employee count.
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
// NAME CORROBORATION GUARD (2026-07-28). A website match alone answers "does
// this LinkedIn page claim this website," not "is this the right company" --
// a parent and its regional pages, or an old legal entity that migrated its
// domain forward, can all legitimately claim the same website (measured:
// intercom.com -> intercom-latinamerica, chorus.ai -> affectlayer-inc,
// clay.com -> grow-with-clay, all website-matched, all wrong, none of them
// failing round 1's own check so round 2 never fired). checkIdentity now
// requires the LinkedIn slug/name to actually carry the domain's brand
// before the website match is trusted; a match whose name does not
// corroborate is escalated to ai_inference rather than auto-accepted or
// silently shipped wrong. See nameCorroboratesDomain in the pure-helpers
// block. Deliberately NOT applied by running ai_inference on every row:
// the verifier has its own measured false-refusal (outreach.io, confirmed
// correct by URL ground truth and two independent providers, still
// rejected), so the escalation stays narrow to keep clean rows away from it.
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

// Merge one round-1 verification outcome with its round-2 rescue outcome, if
// one exists. A round-1 PASS is returned untouched -- round 2 never runs
// against a row that already succeeded. A round-1 FAILURE takes the round-2
// result when one was computed for it (the alternate's count, range, source,
// URL, and identity_method); a row round 2 also rejected, or never saw at
// all, stays exactly as round 1 left it -- unverifiable, not a mismatch.
//
// This is the ONE place that decides which round wins, called from the
// play's final return AND from the test that exercises this block via node,
// so there is no separate reimplementation of the merge to drift out of
// sync with the real logic.
function mergeVerification(round1: any, round2: any): any {
  if (round1 && round1.passed) return round1;
  return round2 || round1;
}

// Assemble the final per-company output rows from round 1's verified rows
// plus round 2's rescue map, via mergeVerification() above. Extracted as its
// own named function -- rather than inlined in the dataset call below -- so
// a test can assert the exact row shape handed to `ctx.dataset('output',
// ...)` without needing a live ctx. This function only decides WHAT the
// merged rows look like; it is deliberately silent on HOW they get
// returned (materialized array vs. durable dataset handle) -- that is a
// separate concern, guarded by a separate source-level test, because a
// past regression got the merge right here and still shipped truncated
// output by wrapping this in `.map(...)` and returning a plain array
// instead of a dataset handle.
function buildOutputRows(verifiedRows1: any[], round2ByRecordId: Record<string, any>): any[] {
  return verifiedRows1.map((r: any) => {
    const verification = mergeVerification(r.verification, round2ByRecordId[r.record_id]);
    return {
      record_id: r.record_id,
      domain: r.domain,
      stored_employee_count: r.company_size,
      verified_employee_count: verification.verified_employee_count,
      source: verification.source,
      verified_range: verification.verified_range,
      verified_linkedin_url: verification.verified_linkedin_url,
      identity_method: verification.identity_method,
    };
  });
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
    // match first, gated by the name-corroboration guard, ai_inference on
    // disagreement OR on a website match the name does not corroborate.
    // `path` tells the caller which of the three ways this was decided, so
    // it can label identity_method precisely instead of collapsing a
    // name-escalated result into the plain website-match or plain ai labels.
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

    // Phase 3: identity check per row against the round-1 batch result. A
    // row that fails is unverifiable FOR NOW, not a mismatch -- round 2 gets
    // a chance at it below.
    const verified1 = await ctx
      .dataset('verify', resolvedRows1)
      .withColumn('verification', async (row: any) => {
        const domain = String(row.domain || '').trim();
        const icypeasUrl = row.icypeas_url;

        if (!icypeasUrl) {
          return { passed: false, verified_employee_count: '', source: '', verified_range: '', verified_linkedin_url: '', identity_method: 'no-linkedin-url' };
        }

        const key = normalizeLinkedInUrl(icypeasUrl);
        const company = key ? scrapedByUrl[key] : null;
        if (!company) {
          return { passed: false, verified_employee_count: '', source: '', verified_range: '', verified_linkedin_url: '', identity_method: 'not-scraped' };
        }

        const match = await checkIdentity(domain, company, icypeasUrl);
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
            match.path === 'website' ? 'website-match:icypeas'
            : match.path === 'website-escalated' ? 'website-match-name-escalated:ai-verified:icypeas'
            : 'ai-verified:icypeas',
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
      // Column deliberately named `altVerification`, NOT `verification` --
      // resolvedRows2 already carries a `verification` field forward from
      // round 1 (the failed outcome that earned this row a round-2 shot),
      // and a second `.withColumn` writing the SAME field name back onto
      // rows that already carry it collides with that pass-through value
      // instead of cleanly replacing it. That collision is the actual data-
      // loss bug: `deepline plays check` confirms it statically (the play's
      // `fields` list carries `verification` twice, once per dataset), and
      // it is why a rescued row's ROUND-1 rejection kept shipping in the
      // final rows even though the durable `verify_alt` dataset (a separate
      // table, immune to this in-memory collision) had the correct rescue
      // recorded all along. A distinct column name here removes the
      // collision outright rather than depending on an unwritten merge-order
      // guarantee.
      const verified2 = await ctx
        .dataset('verify_alt', resolvedRows2)
        .withColumn('altVerification', async (row: any) => {
          const domain = String(row.domain || '').trim();
          const exaUrl = row.exa_url;
          const icypeasUrl = row.icypeas_url;

          if (!exaUrl) {
            // Exa found nothing either. "no-linkedin-url" only if Icypeas
            // never resolved anything to begin with; otherwise Icypeas DID
            // give us a (rejected) candidate, so this stays "ai-rejected".
            return {
              passed: false, verified_employee_count: '', source: '', verified_range: '', verified_linkedin_url: '',
              identity_method: icypeasUrl ? 'ai-rejected' : 'no-linkedin-url',
            };
          }

          const exaKey = normalizeLinkedInUrl(exaUrl);
          const icypeasKey = icypeasUrl ? normalizeLinkedInUrl(icypeasUrl) : '';
          if (exaKey && icypeasKey && exaKey === icypeasKey) {
            // Same page Icypeas already gave us and that already failed --
            // do not re-check it, just mark it failed and move on.
            return { passed: false, verified_employee_count: '', source: '', verified_range: '', verified_linkedin_url: '', identity_method: 'ai-rejected' };
          }

          const company = exaKey ? scrapedByUrl[exaKey] : null;
          if (!company) {
            return { passed: false, verified_employee_count: '', source: '', verified_range: '', verified_linkedin_url: '', identity_method: 'ai-rejected' };
          }

          const match = await checkIdentity(domain, company, exaUrl);
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
              match.path === 'website' ? 'website-match:exa'
              : match.path === 'website-escalated' ? 'website-match-name-escalated:ai-verified:exa'
              : 'ai-verified:exa',
          };
        })
        .run({ key: 'record_id' });

      const verifiedRows2 = await verified2.materialize();
      for (const r of verifiedRows2) {
        round2ByRecordId[r.record_id] = r.altVerification;
      }
    }

    // ---------------------------------------------------------------
    // Recombine: round-1 passes keep their round-1 result; round-1 failures
    // take their round-2 result when round 2 ran, else stay exactly as round
    // 1 left them (unverifiable, not a mismatch).
    // ---------------------------------------------------------------

    const outputRows = buildOutputRows(verifiedRows1, round2ByRecordId);

    // Phase 5: persist the merged rows as their own durable dataset and
    // return THAT HANDLE, not a materialized array. A plain
    // `verifiedRows1.map(...)` array is exactly what shipped here before --
    // correct in every unit test and in `deepline plays check`, but the
    // Deepline runtime caps a play's inline return payload (the run-event
    // document has a size limit), so on a real 100-row run it silently
    // truncated to the first 20 rows. `ctx.dataset(...).run(...)` persists
    // every row to a durable table with no such cap; returning the handle
    // WITHOUT calling `.materialize()` on it keeps `rows` a dataset
    // reference (`isDataset: true` in `deepline plays check`'s output), so
    // `deepline runs export --dataset result.rows` retrieves all 100 rows
    // regardless of sample size. No provider call here -- this is a plain
    // data-shaping dataset, so the two-batched-Apify-call ceiling is
    // untouched.
    const output = await ctx
      .dataset('output', outputRows)
      .run({ key: 'record_id' });

    return { rows: output };
  },
  {
    description:
      'Fetch a verified employee count per company domain via a LinkedIn-direct chain (Icypeas resolves round 1 for every row; only rows that fail round 1 get a round-2 Exa alternate candidate; each round is one batched HarvestAPI scrape plus an identity check) so the CRM Report Card can grade stored headcount accuracy. Read-only: never writes to a CRM.',
  },
);
