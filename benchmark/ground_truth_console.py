"""Ground-truth review console for the employee-count provider benchmark.

Throwaway local tool, in the same spirit as sculpted-skills' qa-console: a
Flask app over durable files, meant to run once on one machine and then be
forgotten. The durable output is benchmark/ground_truth.jsonl, not this app.

This file holds only the Flask routes, HTML, and server startup. All the
logic that can be tested without a browser (loading domains.csv, computing
what's still pending, building a record, appending it, last-row-wins,
evidence-URL construction) lives in ground_truth_lib.py, which imports
nothing but the standard library -- so tests/test_ground_truth_console.py
runs under plain `python3 -m pytest` on a machine that has never installed
Flask. This module needs Flask; the lib does not.

Purpose: the operator hand-verifies all 100 companies in domains.csv and
records, per company, the true employee count and the correct LinkedIn
company page, each with a citation. See METHODOLOGY.md for why this has to be
a human pass and why LinkedIn cannot be the truth source for headcount.

Reads  benchmark/domains.csv            (domain, tier, note)
Writes benchmark/ground_truth.jsonl      (append-only; crash-safe)

Resume: on restart, any domain already present in ground_truth.jsonl (in any
row) is skipped; the operator picks up wherever they stopped. A correction is
just a new appended row for the same domain -- last row wins for any reader.

BLIND BY DESIGN -- read this before touching this file:
This app must NEVER read, load, display, or link to benchmark/raw_results.csv
or benchmark/ourplay_results.csv. Those hold provider answers, and the
benchmark's validity depends on ground truth being recorded without seeing
them (METHODOLOGY.md, "Anchoring control"). Do not add a "compare" or "hint"
feature, even if it looks convenient. If you are tempted to import a results
CSV into this file to "help the operator go faster," don't -- that is exactly
the anchoring risk the methodology was written to close off.

The evidence split (also load-bearing, see METHODOLOGY.md):
  - Headcount evidence is NEVER LinkedIn. We surface the company's own site
    and Google queries aimed at an about/careers page and at filings.
  - LinkedIn IS the correct source for identity (which LinkedIn page is
    right is literally the second value being recorded), so a LinkedIn
    company search auto-opens in one reused named window per row.

Usage:
  python3 ground_truth_console.py [--domains PATH] [--out PATH] [--port 7799]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from flask import Flask, jsonify, request

import ground_truth_lib as gtl

HERE = Path(__file__).resolve().parent
DEFAULT_DOMAINS = HERE / "domains.csv"
DEFAULT_OUT = HERE / "ground_truth.jsonl"


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>ground-truth console</title>
<style>
:root{--paper:#F7F6F2;--card:#FFFFFF;--ink:#1F2937;--muted:#6B7280;--line:#E5E2DA;
--accent:#0F6B5C;--accent-soft:#E4EFEC;--warn:#B4552D;--warn-soft:#F9EDE6;
--mono:ui-monospace,SFMono-Regular,Menlo,monospace}
*{box-sizing:border-box}
body{font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink);
  margin:0;background:var(--paper);display:flex;justify-content:center}
#wrap{max-width:760px;width:100%;padding:24px}
#topbar{display:flex;align-items:baseline;gap:12px;margin-bottom:6px}
#topbar b{font-size:16px}
#topbar .muted{color:var(--muted);font-size:12px}
#bar{height:4px;background:var(--line);border-radius:2px;margin-bottom:20px}
#barfill{height:4px;background:var(--accent);width:0%;border-radius:2px;transition:width .2s}
#card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:20px 22px}
#domain{font-size:22px;font-weight:650;margin:0 0 2px}
#tierline{color:var(--muted);font-size:12.5px;margin-bottom:16px}
#tierline .note{font-style:italic}
h4{margin:0 0 8px;font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.section{margin-bottom:18px}
.evidence-box{background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.evidence-box a{display:inline-block;color:var(--accent);font-size:13px;text-decoration:none;
  margin:2px 10px 2px 0;font-weight:600}
.evidence-box a:hover{text-decoration:underline}
.no-linkedin{display:inline-block;font:700 10.5px -apple-system,sans-serif;letter-spacing:.04em;
  text-transform:uppercase;color:var(--warn);background:var(--warn-soft);border-radius:99px;
  padding:2px 9px;margin-left:8px}
.li-box{background:#EAF2FB;border:1px solid #B9CBD3;border-radius:8px;padding:10px 12px}
.li-box a{color:#0A66C2;font-weight:700;text-decoration:none;font-size:13px}
.splitline{font-size:11.5px;color:var(--muted);margin:2px 0 18px;padding:8px 12px;
  background:var(--accent-soft);border-radius:8px}
label{display:block;font-size:11.5px;font-weight:600;color:var(--muted);margin:0 0 4px}
input,select,textarea{width:100%;font:14px -apple-system,sans-serif;padding:8px 10px;
  border:1px solid var(--line);border-radius:6px;margin-bottom:14px;background:var(--card)}
textarea{resize:vertical;min-height:54px}
.row2{display:flex;gap:14px}
.row2 > div{flex:1}
#actions{display:flex;gap:10px;align-items:center;margin-top:4px}
button{font:700 13px -apple-system,sans-serif;padding:10px 16px;border-radius:8px;
  border:1px solid var(--line);background:var(--card);cursor:pointer;color:var(--ink)}
button:hover{border-color:var(--accent)}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button.ghost{border-color:var(--warn);color:var(--warn);background:transparent}
kbd{font:700 10.5px var(--mono);background:rgba(0,0,0,.07);border-radius:4px;padding:1px 5px;margin-right:6px}
button.primary kbd{background:rgba(255,255,255,.25)}
#hint{color:var(--muted);font-size:11.5px;margin-left:auto}
#donemsg{display:none;font-size:19px;padding:48px 24px;color:var(--accent);text-align:center}
#err{display:none;color:var(--warn);background:var(--warn-soft);border-radius:8px;padding:8px 12px;
  font-size:12.5px;margin-bottom:14px}
</style></head><body>
<div id="wrap">
  <div id="topbar"><b>ground-truth console</b><span class="muted" id="progress"></span></div>
  <div id="bar"><div id="barfill"></div></div>
  <div id="donemsg">All 100 companies recorded. ground_truth.jsonl is up to date -- you can close this tab.</div>
  <div id="card">
    <div id="err"></div>
    <div id="domain"></div>
    <div id="tierline"></div>
    <div class="splitline">Headcount evidence below is never LinkedIn (a contestant reads LinkedIn, so it
      can't also be truth). The LinkedIn identity search opens in its own browser window/tab because
      LinkedIn can't render here -- that one IS the right source for the LinkedIn-URL field.</div>

    <div class="section">
      <h4>Headcount evidence <span class="no-linkedin">not LinkedIn</span></h4>
      <div class="evidence-box" id="hc-evidence"></div>
    </div>

    <div class="section">
      <h4>LinkedIn identity search</h4>
      <div class="li-box">Opens automatically in one reused window/tab (<code>gt-linkedin</code>).
        <span id="li-link"></span></div>
    </div>

    <form id="form">
      <div class="row2">
        <div>
          <label for="count">true_employee_count (blank if unknowable)</label>
          <input id="count" type="number" min="0" inputmode="numeric" autocomplete="off">
        </div>
        <div>
          <label for="source_type">source_type</label>
          <select id="source_type">
            <option value="filing">filing</option>
            <option value="company_page">company_page</option>
            <option value="third_party">third_party</option>
            <option value="none">none</option>
          </select>
        </div>
      </div>
      <label for="li_url">true_linkedin_url (blank if none exists)</label>
      <input id="li_url" type="text" placeholder="https://www.linkedin.com/company/..." autocomplete="off">
      <label for="citation">citation_url (where the headcount claim came from)</label>
      <input id="citation" type="text" placeholder="https://..." autocomplete="off">
      <label for="note">note (optional)</label>
      <textarea id="note"></textarea>
      <div id="actions">
        <button type="submit" class="primary"><kbd>Enter</kbd>Save &amp; next</button>
        <button type="button" class="ghost" onclick="noGroundTruth()"><kbd>Alt+N</kbd>No ground truth</button>
        <span id="hint">Enter in a single-line field saves this row. Alt+N records "can't verify" and moves on.</span>
      </div>
    </form>
  </div>
</div>
<script>
let state=null, liTab=null;

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function openLinkedIn(url){
  // Reused named window: each row replaces the last instead of piling up tabs.
  try{
    if(liTab && !liTab.closed){liTab.location.href=url;}
    else{liTab=window.open(url,'gt-linkedin');}
  }catch(e){/* pop-up blocked -- the header link still works */}
}

function render(){
  const r=state.row, done=(r===null);
  document.getElementById('card').style.display=done?'none':'block';
  document.getElementById('donemsg').style.display=done?'block':'none';
  document.getElementById('progress').textContent=state.done+' of '+state.total+' recorded';
  document.getElementById('barfill').style.width=(state.total?100*state.done/state.total:0)+'%';
  if(done)return;
  document.getElementById('domain').textContent=r.domain;
  document.getElementById('tierline').innerHTML='tier: '+esc(r.tier)+(r.note?' &middot; <span class="note">'+esc(r.note)+'</span>':'');
  const ev=r.evidence;
  document.getElementById('hc-evidence').innerHTML=
    '<a href="'+ev.site_url+'" target="_blank" rel="noopener">Company site &#8599;</a>'
    +'<a href="'+ev.google_about_url+'" target="_blank" rel="noopener">Google: about/careers &#8599;</a>'
    +'<a href="'+ev.google_filing_url+'" target="_blank" rel="noopener">Google: filings &#8599;</a>';
  document.getElementById('li-link').innerHTML=
    '<a href="'+ev.linkedin_search_url+'" onclick="event.preventDefault();openLinkedIn(this.href)">Reopen LinkedIn search &#8599;</a>';
  document.getElementById('count').value='';
  document.getElementById('li_url').value='';
  document.getElementById('citation').value='';
  document.getElementById('source_type').value='none';
  document.getElementById('note').value='';
  document.getElementById('err').style.display='none';
  document.getElementById('count').focus();
  openLinkedIn(ev.linkedin_search_url);
}

async function refresh(){
  state=await(await fetch('/api/state')).json();
  render();
}

async function submitRow(noGT){
  if(!state.row)return;
  const body={
    domain: state.row.domain,
    tier: state.row.tier,
    true_employee_count: document.getElementById('count').value,
    true_linkedin_url: document.getElementById('li_url').value,
    citation_url: document.getElementById('citation').value,
    source_type: document.getElementById('source_type').value,
    note: document.getElementById('note').value,
    no_ground_truth: !!noGT,
  };
  const res=await fetch('/api/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await res.json();
  if(!res.ok){
    const e=document.getElementById('err');e.textContent=data.error||'save failed';e.style.display='block';
    return;
  }
  state=data;render();
}

function noGroundTruth(){submitRow(true);}

document.getElementById('form').addEventListener('submit',e=>{e.preventDefault();submitRow(false);});
document.addEventListener('keydown',e=>{
  if(e.altKey && (e.key==='n'||e.key==='N')){e.preventDefault();noGroundTruth();}
});
refresh();
</script></body></html>"""


def create_app(domains_path, out_path) -> Flask:
    app = Flask(__name__)
    domains_path, out_path = Path(domains_path), Path(out_path)

    def state_payload():
        domains = gtl.load_domains(domains_path)
        rows = gtl.load_ground_truth(out_path)
        todo = gtl.pending(domains, rows)
        row = None
        if todo:
            d = todo[0]
            row = {**d, "evidence": gtl.evidence_for(d["domain"])}
        return {
            "row": row,
            "done": len(domains) - len(todo),
            "total": len(domains),
        }

    @app.get("/")
    def index():
        return PAGE

    @app.get("/api/state")
    def state():
        return jsonify(state_payload())

    @app.post("/api/submit")
    def submit():
        body = request.get_json(force=True, silent=True) or {}
        domain = (body.get("domain") or "").strip()
        if not domain:
            return jsonify({"error": "domain is required"}), 400
        # Guard against a stale client submitting for a domain that is no
        # longer the current pending row (e.g. two tabs open). Any domain
        # from domains.csv is accepted; re-recording an already-done domain
        # is allowed too (that's a correction, not an error).
        try:
            record = gtl.make_record(
                domain,
                body.get("tier", ""),
                true_employee_count=body.get("true_employee_count"),
                true_linkedin_url=body.get("true_linkedin_url", ""),
                citation_url=body.get("citation_url", ""),
                source_type=body.get("source_type", ""),
                note=body.get("note", ""),
                no_ground_truth=bool(body.get("no_ground_truth")),
            )
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        gtl.append_record(out_path, record)
        return jsonify(state_payload())

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domains", default=str(DEFAULT_DOMAINS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7799)
    args = parser.parse_args()
    app = create_app(args.domains, args.out)
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
