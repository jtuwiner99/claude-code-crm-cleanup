"""Ground-truth review console for the employee-count provider benchmark.

Throwaway local tool, in the same spirit as sculpted-skills' qa-console: a
Flask app over durable files, meant to run once on one machine and then be
forgotten. The durable output is benchmark/ground_truth.jsonl, not this app.

This file holds only the Flask routes, HTML/JS, and server startup. All the
logic that can be tested without a browser or network access (loading
domains.csv, computing what's still pending, building a record, appending
it, last-row-wins, LinkedIn slug normalization, candidate building, the
homepage-framing helpers) lives in ground_truth_lib.py, which imports
nothing but the standard library -- so tests/test_ground_truth_console.py
runs under plain `python3 -m pytest` on a machine that has never installed
Flask. This module needs Flask; the lib does not.

Interaction model (per the operator): per company, side by side --
  LEFT:  the domain, the unlabeled LinkedIn candidate list (built blind from
         raw_results.csv + ourplay_results.csv), the LinkedIn People-tab
         count field, the independent (non-LinkedIn) count field, and the
         three actions (confirm & save / not the right page / no ground
         truth).
  RIGHT: the company's homepage framed in an iframe via /proxy, exactly the
         way qa-console frames evidence pages (proxy fetch + strip framing
         guards + inject <base>), since most sites refuse direct framing.
Clicking a candidate (or typing a pasted URL) opens ITS LinkedIn People page
in one reused named browser window ('gt-linkedin'), because LinkedIn itself
can never render in an iframe (X-Frame-Options + login authwall). Typing a
real linkedin_people_count records identity as correct for whichever
candidate is currently selected -- that's the whole point of the People tab:
the operator confirms identity and reads the count in the same glance.

BLIND BY DESIGN -- read this before touching this file:
This app must NEVER read, load, display, or link to any COLUMN of
raw_results.csv / ourplay_results.csv other than `domain` and `linkedin_url`
(ground_truth_lib.py enforces this at the parsing layer). It must never show
which provider produced which candidate -- not in the HTML, not in a data
attribute, not in the JSON this page fetches -- and never show any
provider's employee count. Candidates are unlabeled and shuffled with a
domain-seeded RNG so their order carries no information about source. If you
are tempted to add a label, a tooltip, or a debug attribute that reveals
which provider a candidate came from, don't -- that is exactly the
anchoring risk METHODOLOGY.md's "Anchoring control" section closes off.

Usage:
  python3 ground_truth_console.py [--domains PATH] [--out PATH]
      [--raw-results PATH] [--ourplay-results PATH] [--port 7799]
      [--only domain1.com,domain2.com,...]

--only restricts the console to a specific comma-separated set of domains and
ignores the normal already-recorded skip logic for them, so a row that was
confirmed against the wrong LinkedIn page (e.g. close.com, copper.com,
cal.com) can be re-reviewed and corrected. Without --only, behavior is
unchanged: any domain already in ground_truth.jsonl is skipped as usual.
Corrections append normally either way (ground_truth.jsonl stays append-only,
last-row-wins). Within one --only session, a domain drops off the front of
the queue once it has been resubmitted this run (gtl.pending's `exclude`),
so the console advances to the next requested domain.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from flask import Flask, Response, jsonify, request

import ground_truth_lib as gtl

HERE = Path(__file__).resolve().parent
DEFAULT_DOMAINS = HERE / "domains.csv"
DEFAULT_OUT = HERE / "ground_truth.jsonl"
DEFAULT_RAW_RESULTS = HERE / "raw_results.csv"
DEFAULT_OURPLAY_RESULTS = HERE / "ourplay_results.csv"


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>ground-truth console</title>
<style>
:root{--paper:#F7F6F2;--card:#FFFFFF;--ink:#1F2937;--muted:#6B7280;--line:#E5E2DA;
--accent:#0F6B5C;--accent-soft:#E4EFEC;--warn:#B4552D;--warn-soft:#F9EDE6;
--li:#0A66C2;--li-soft:#EAF2FB;--mono:ui-monospace,SFMono-Regular,Menlo,monospace}
*{box-sizing:border-box}
body{font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink);
  margin:0;background:var(--paper);display:flex;height:100vh}
#left{width:42%;min-width:400px;display:flex;flex-direction:column;border-right:1px solid var(--line);
  overflow-y:auto}
#right{flex:1;display:flex;flex-direction:column}
#topbar{padding:10px 18px;border-bottom:1px solid var(--line);display:flex;align-items:baseline;
  gap:12px;background:var(--card)}
#topbar b{font-size:15px}
#topbar .muted{color:var(--muted);font-size:12px;margin-left:auto}
#bar{height:4px;background:var(--line)}#barfill{height:4px;background:var(--accent);width:0%;transition:width .2s}
#card{padding:18px}
#err{display:none;color:var(--warn);background:var(--warn-soft);border-radius:8px;padding:8px 12px;
  font-size:12.5px;margin-bottom:12px}
#domain{font-size:21px;font-weight:650;margin:0 0 2px}
#tierline{color:var(--muted);font-size:12.5px;margin-bottom:12px}
#tierline .note{font-style:italic}
.splitline{font-size:11.5px;color:var(--muted);margin:0 0 16px;padding:8px 12px;
  background:var(--accent-soft);border-radius:8px}
h4{margin:0 0 8px;font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.section{margin-bottom:18px}
#candidates{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}
.cand{font:600 13px var(--mono);padding:8px 14px;border-radius:8px;border:1px solid var(--line);
  background:var(--card);cursor:pointer;color:var(--ink)}
.cand:hover{border-color:var(--li)}
.cand.sel{background:var(--li);border-color:var(--li);color:#fff}
.noCands{font-size:12.5px;color:var(--muted);font-style:italic;margin-bottom:10px}
.customrow{background:var(--li-soft);border:1px solid #B9CBD3;border-radius:8px;padding:10px 12px}
.customrow.sel{outline:2px solid var(--li)}
.customrow label{display:block;font-size:11.5px;font-weight:600;color:var(--muted);margin-bottom:4px}
.customrow input{width:100%;font:13px -apple-system,sans-serif;padding:7px 9px;border:1px solid var(--line);
  border-radius:6px;background:var(--card);margin-bottom:6px}
.customrow a{color:var(--li);font-size:12px;font-weight:600;text-decoration:none}
label.fieldlabel{display:block;font-size:11.5px;font-weight:600;color:var(--muted);margin:0 0 4px}
input.field,textarea.field{width:100%;font:14px -apple-system,sans-serif;padding:8px 10px;
  border:1px solid var(--line);border-radius:6px;margin-bottom:12px;background:var(--card)}
textarea.field{resize:vertical;min-height:44px}
.li-count-box{background:var(--li-soft);border:1px solid #B9CBD3;border-radius:8px;padding:10px 12px}
.li-count-box label.fieldlabel{color:var(--li)}
.ind-box{background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.ind-box .tag{display:inline-block;font:700 10px -apple-system,sans-serif;letter-spacing:.04em;
  text-transform:uppercase;color:var(--accent);background:var(--accent-soft);border-radius:99px;
  padding:2px 8px;margin-bottom:8px}
.evlinks{margin-top:6px}
.evlinks a{display:inline-block;color:var(--accent);font-size:12px;text-decoration:none;
  margin:2px 12px 2px 0;font-weight:600}
#actions{display:flex;flex-direction:column;gap:8px;margin-top:6px}
button{font:700 13px -apple-system,sans-serif;padding:10px 14px;border-radius:8px;
  border:1px solid var(--line);background:var(--card);cursor:pointer;color:var(--ink);text-align:left}
button:hover{border-color:var(--accent)}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button.wrongbtn{border-color:var(--warn);color:var(--warn);background:transparent}
button.ghost{color:var(--muted);background:transparent}
kbd{font:700 10.5px var(--mono);background:rgba(0,0,0,.07);border-radius:4px;padding:1px 5px;margin-right:8px}
button.primary kbd{background:rgba(255,255,255,.25)}
#donemsg{display:none;font-size:18px;padding:40px 22px;color:var(--accent);text-align:center}
#evhead{padding:8px 16px;font-size:12px;color:var(--muted);background:var(--card);border-bottom:1px solid var(--line)}
#evhead a{color:var(--accent);text-decoration:none;font-weight:600}
#evwrap{flex:1;position:relative}
#homepage-frame{position:absolute;inset:0;border:0;width:100%;height:100%;background:#fff}
#evloading{position:absolute;inset:0;display:none;flex-direction:column;align-items:center;justify-content:center;
  gap:12px;background:rgba(247,246,242,.85);z-index:5}
#evloading.on{display:flex}
#evloading .dot{width:38px;height:38px;border:4px solid var(--line);border-top-color:var(--accent);
  border-radius:50%;animation:spin .8s linear infinite}
#evloading .txt{font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}
@keyframes spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion: reduce){*{transition:none!important}#evloading .dot{animation:none}}
</style></head><body>
<div id="left">
  <div id="topbar"><b>ground-truth console</b><span class="muted" id="progress"></span></div>
  <div id="bar"><div id="barfill"></div></div>
  <div id="donemsg">All 100 companies recorded. ground_truth.jsonl is up to date -- you can close this tab.</div>
  <div id="card">
    <div id="err"></div>
    <div id="domain"></div>
    <div id="tierline"></div>
    <div class="splitline">The LinkedIn People tab opens in its own window because LinkedIn can't render
      here. It's the reference: typing the real count from it records that candidate as the correct
      identity AND the truth count in one motion. The homepage on the right and the about/filing links
      below are for the separate, optional, non-LinkedIn independent_count -- recorded on purpose, never
      blended with the LinkedIn number.</div>

    <div class="section">
      <h4>LinkedIn identity candidates (unlabeled, shuffled)</h4>
      <div id="candidates"></div>
      <div class="customrow" id="customrow">
        <label>None of these -- paste the correct LinkedIn URL</label>
        <input id="custom_url" placeholder="https://www.linkedin.com/company/..." autocomplete="off">
        <a href="#" id="search-link" onclick="event.preventDefault();openLinkedInSearch()">Search LinkedIn for this domain &#8599;</a>
      </div>
    </div>

    <div class="section li-count-box">
      <label class="fieldlabel" for="li_count">linkedin_people_count -- from the People tab open in the LinkedIn window</label>
      <input class="field" id="li_count" type="number" min="0" inputmode="numeric" autocomplete="off"
        placeholder="employees shown on that page">
    </div>

    <div class="section ind-box">
      <span class="tag">independent, optional</span>
      <label class="fieldlabel" for="ind_count">independent_count -- a NON-LinkedIn headcount (homepage / about / careers / filing)</label>
      <input class="field" id="ind_count" type="number" min="0" inputmode="numeric" autocomplete="off">
      <label class="fieldlabel" for="ind_cite">independent_citation_url</label>
      <input class="field" id="ind_cite" type="text" placeholder="https://..." autocomplete="off">
      <div class="evlinks" id="evlinks"></div>
    </div>

    <div class="section">
      <label class="fieldlabel" for="note">note (optional)</label>
      <textarea class="field" id="note"></textarea>
    </div>

    <div id="actions">
      <button class="primary" onclick="submitRow('correct')"><kbd>Enter</kbd>Confirm &amp; save (page is correct)</button>
      <button class="wrongbtn" onclick="submitRow('wrong')"><kbd>Alt+W</kbd>Not the right page</button>
      <button class="ghost" onclick="submitRow('no-ground-truth')"><kbd>Alt+N</kbd>No ground truth</button>
    </div>
  </div>
</div>
<div id="right">
  <div id="evhead"><span id="evlinks-head"></span></div>
  <div id="evwrap">
    <iframe id="homepage-frame" src="about:blank" title="homepage"></iframe>
    <div id="evloading"><div class="dot"></div><div class="txt">Loading homepage&hellip;</div></div>
  </div>
</div>
<script>
let state=null, liTab=null, selected={type:'none'}, evTimer;

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function letter(i){return String.fromCharCode(65+i);}

function openLinkedIn(url){
  // Reused named window: each row (and each candidate click) replaces the
  // last instead of piling up tabs.
  try{
    if(liTab && !liTab.closed){liTab.location.href=url;}
    else{liTab=window.open(url,'gt-linkedin');}
  }catch(e){/* pop-up blocked -- the manual links still work */}
}
function openLinkedInSearch(){ if(state&&state.row) openLinkedIn(state.row.linkedin_search_url); }

function derivePeopleUrl(url){
  url=(url||'').trim();
  if(!url) return url;
  const m=url.match(/linkedin\\.com\\/company\\/([^\\/?#]+)/i);
  if(m) return 'https://www.linkedin.com/company/'+m[1]+'/people/';
  return url;
}

function selectCandidate(i){
  selected={type:'candidate',index:i};
  document.getElementById('custom_url').value='';
  renderSelection();
  openLinkedIn(state.row.candidates[i].people_url);
}
function selectCustom(){
  selected={type:'custom'};
  renderSelection();
}
function openCustom(){
  const u=document.getElementById('custom_url').value;
  if(u.trim()) openLinkedIn(derivePeopleUrl(u));
}

function renderSelection(){
  document.querySelectorAll('.cand').forEach(b=>b.classList.toggle('sel', selected.type==='candidate' && Number(b.dataset.i)===selected.index));
  document.getElementById('customrow').classList.toggle('sel', selected.type==='custom');
}

function evLoading(on){document.getElementById('evloading').classList.toggle('on',on);}
function loadHomepage(url){
  const fr=document.getElementById('homepage-frame');
  clearTimeout(evTimer);evLoading(false);fr.onload=null;
  fr.src='about:blank';
  setTimeout(()=>{
    evLoading(true);
    fr.onload=()=>{evLoading(false);};
    evTimer=setTimeout(()=>evLoading(false),20000);
    fr.src='/proxy?url='+encodeURIComponent(url);
  },0);
}

function render(){
  const r=state.row, done=(r===null);
  document.getElementById('card').style.display=done?'none':'block';
  document.getElementById('evwrap').style.display=done?'none':'block';
  document.getElementById('donemsg').style.display=done?'block':'none';
  document.getElementById('progress').textContent=state.done+' of '+state.total+' recorded';
  document.getElementById('barfill').style.width=(state.total?100*state.done/state.total:0)+'%';
  document.getElementById('err').style.display='none';
  if(done)return;

  document.getElementById('domain').textContent=r.domain;
  document.getElementById('tierline').innerHTML='tier: '+esc(r.tier)+(r.note?' &middot; <span class="note">'+esc(r.note)+'</span>':'');

  const cands=r.candidates||[];
  const cwrap=document.getElementById('candidates');
  if(cands.length){
    cwrap.innerHTML=cands.map((c,i)=>'<button class="cand" data-i="'+i+'" onclick="selectCandidate('+i+')">'+letter(i)+'</button>').join('');
  }else{
    cwrap.innerHTML='<div class="noCands">No candidate LinkedIn URLs were found for this domain -- search and paste one below.</div>';
  }
  document.getElementById('custom_url').value='';
  document.getElementById('custom_url').oninput=selectCustom;

  document.getElementById('li_count').value='';
  document.getElementById('ind_count').value='';
  document.getElementById('ind_cite').value='';
  document.getElementById('note').value='';

  document.getElementById('evlinks').innerHTML=
    '<a href="'+r.google_about_url+'" target="_blank" rel="noopener">Google: about/careers &#8599;</a>'
    +'<a href="'+r.google_filing_url+'" target="_blank" rel="noopener">Google: filings &#8599;</a>';
  document.getElementById('evlinks-head').innerHTML=
    '<a href="'+r.homepage_url+'" target="_blank" rel="noopener">Open original homepage &#8599;</a>';

  // Default selection: first candidate, or custom if there are none.
  selected = cands.length ? {type:'candidate', index:0} : {type:'custom'};
  renderSelection();
  if(cands.length){ openLinkedIn(cands[0].people_url); }
  else { openLinkedInSearch(); }

  loadHomepage(r.homepage_url);
  document.getElementById('li_count').focus();
}

async function refresh(){
  state=await(await fetch('/api/state')).json();
  render();
}

function showErr(msg){
  const e=document.getElementById('err');e.textContent=msg;e.style.display='block';
}

async function submitRow(verdict){
  if(!state.row)return;
  let chosen='';
  if(verdict==='correct'){
    if(selected.type==='candidate'){
      chosen=state.row.candidates[selected.index].company_url;
    }else{
      chosen=document.getElementById('custom_url').value.trim();
    }
    if(!chosen){showErr('Choose a candidate above, or paste a LinkedIn URL, before confirming.');return;}
    if(!document.getElementById('li_count').value){showErr('Enter the count from the LinkedIn People tab before confirming.');return;}
  }
  const body={
    domain: state.row.domain,
    tier: state.row.tier,
    identity_verdict: verdict,
    chosen_linkedin_url: chosen,
    linkedin_people_count: document.getElementById('li_count').value,
    independent_count: document.getElementById('ind_count').value,
    independent_citation_url: document.getElementById('ind_cite').value,
    note: document.getElementById('note').value,
  };
  const res=await fetch('/api/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await res.json();
  if(!res.ok){showErr(data.error||'save failed');return;}
  state=data;render();
}

document.addEventListener('keydown',e=>{
  if(e.target && e.target.tagName==='TEXTAREA')return;
  if(e.altKey && (e.key==='n'||e.key==='N')){e.preventDefault();submitRow('no-ground-truth');return;}
  if(e.altKey && (e.key==='w'||e.key==='W')){e.preventDefault();submitRow('wrong');return;}
  if(e.key==='Enter' && e.target && e.target.id==='li_count'){e.preventDefault();submitRow('correct');}
});
refresh();
</script></body></html>"""


def create_app(domains_path, out_path, raw_results_path=None, ourplay_results_path=None,
               only=None) -> Flask:
    app = Flask(__name__)
    domains_path, out_path = Path(domains_path), Path(out_path)
    raw_results_path = Path(raw_results_path) if raw_results_path else DEFAULT_RAW_RESULTS
    ourplay_results_path = Path(ourplay_results_path) if ourplay_results_path else DEFAULT_OURPLAY_RESULTS

    # only: a set of domains for re-review mode, or None for normal behavior.
    # only_done is session-local (this process only, never written to disk):
    # it tracks which --only domains have been resubmitted this run so the
    # queue advances instead of re-showing the one just corrected.
    only_set = set(only) if only else None
    only_done: set = set()

    def state_payload():
        domains = gtl.load_domains(domains_path)
        rows = gtl.load_ground_truth(out_path)
        todo = gtl.pending(domains, rows, only=only_set, exclude=only_done)
        row = None
        if todo:
            d = todo[0]
            ctx = gtl.row_context_for(d["domain"], raw_results_path, ourplay_results_path)
            row = {**d, **ctx}
        total = len(only_set) if only_set is not None else len(domains)
        done = total - len(todo)
        return {
            "row": row,
            "done": done,
            "total": total,
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
                identity_verdict=body.get("identity_verdict", ""),
                chosen_linkedin_url=body.get("chosen_linkedin_url", ""),
                linkedin_people_count=body.get("linkedin_people_count"),
                independent_count=body.get("independent_count"),
                independent_citation_url=body.get("independent_citation_url", ""),
                note=body.get("note", ""),
            )
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        gtl.append_record(out_path, record)
        if only_set is not None and domain in only_set:
            only_done.add(domain)
        return jsonify(state_payload())

    @app.get("/proxy")
    def proxy():
        url = request.args.get("url", "")
        if not gtl.safe_public_url(url):
            return ("<p style='font:12px sans-serif;padding:14px;color:#B4552D'>"
                    "Can't frame this URL (invalid, or a private/internal address). "
                    "Use the &ldquo;Open original &#8599;&rdquo; link above.</p>"), 200
        try:
            ctype, raw, final_url = gtl.fetch_url_bytes(url)
        except Exception as e:
            return ("<p style='font:12px sans-serif;padding:14px;color:#B4552D'>"
                    "Couldn't load this page in-pane (" + str(e).replace("<", "&lt;") + "). "
                    "Use the &ldquo;Open original &#8599;&rdquo; link above.</p>"), 200
        if "text/html" not in ctype.lower():
            # PDFs, images, etc. -- serve bytes directly; our response carries
            # no framing headers, so the pane renders them.
            return Response(raw, content_type=ctype or "application/octet-stream")
        html = gtl.strip_frame_guards(raw.decode("utf-8", "replace"), final_url)
        return html

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domains", default=str(DEFAULT_DOMAINS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--raw-results", default=str(DEFAULT_RAW_RESULTS))
    parser.add_argument("--ourplay-results", default=str(DEFAULT_OURPLAY_RESULTS))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7799)
    parser.add_argument(
        "--only", default=None,
        help="Comma-separated domains to re-review, ignoring the already-recorded "
             "skip logic for exactly those domains (e.g. close.com,copper.com,cal.com). "
             "Omit for normal resume behavior.")
    args = parser.parse_args()
    only = None
    if args.only:
        only = {d.strip() for d in args.only.split(",") if d.strip()}
    app = create_app(args.domains, args.out, args.raw_results, args.ourplay_results, only=only)
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
