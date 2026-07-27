// @ts-nocheck
/* eslint-disable */

// Employee-count accuracy: for each company, fetch a verified headcount and return
// it next to the stored one. This play FETCHES; it does not judge. The band
// comparison lives in the report card's Python scorer so the grading rule is
// covered by an offline test suite.
//
// Waterfall: peopledatalabs_enrich_company (exact employee_count, free on a miss)
// -> exa_answer with an outputSchema (citation-backed, about $0.007) -> unverifiable.
//
// Restricted plays lib: no encodeURIComponent, no array/string .indexOf, no
// String.charAt.

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

export default definePlay(
  'crm-report-card-employee-count-accuracy',
  async (ctx: any, input: any) => {
    const rows = input.rows || [];

    const dataset = ctx
      .dataset('employee_count_accuracy', rows)

      // One tool call plus its extract, returning a compact scalar.
      .withColumn('pdl_employee_count', async (row: any) => {
        const domain = String(row.domain || '').trim();
        if (!domain) return null;
        try {
          const result = await ctx.tools.execute({
            id: 'pdl_employee_count',
            description: 'Fetch verified employee count from PeopleDataLabs for this company domain.',
            tool: 'peopledatalabs_enrich_company',
            input: { domain },
          });
          const raw = toolRaw(result) || {};
          return toInt(raw.employee_count);
        } catch (err) {
          // Best effort: a provider miss is not a failed row.
          return null;
        }
      })

      .withColumn('exa_employee_count', async (row: any, prior: any) => {
        if (prior.pdl_employee_count) return null;
        const domain = String(row.domain || '').trim();
        if (!domain) return null;
        try {
          const result = await ctx.tools.execute({
            id: 'exa_employee_count',
            description: 'Fetch a citation-backed employee count answer from Exa for this company domain.',
            tool: 'exa_answer',
            input: {
              query: `How many employees work at the company at ${domain}? Answer with a single number.`,
              text: true,
              outputSchema: {
                type: 'object',
                properties: {
                  employee_count: { type: 'number' },
                  confidence: { type: 'string' },
                },
                required: ['employee_count'],
              },
            },
          });
          const raw = toolRaw(result) || {};
          const answer = raw.answer || {};
          return toInt(answer.employee_count);
        } catch (err) {
          return null;
        }
      });

    const results = await dataset.run({ key: 'record_id' });

    // Lean return: one compact row per record, no raw provider payloads.
    return {
      rows: results.map((r: any) => ({
        record_id: r.record_id,
        domain: r.domain,
        stored_employee_count: r.company_size,
        verified_employee_count: r.pdl_employee_count || r.exa_employee_count || '',
        source: r.pdl_employee_count
          ? 'peopledatalabs_enrich_company'
          : (r.exa_employee_count ? 'exa_answer' : ''),
      })),
    };
  },
  {
    description:
      'Fetch a verified employee count per company domain (PeopleDataLabs, then Exa) so the CRM Report Card can grade stored headcount accuracy. Read-only: never writes to a CRM.',
  },
);
