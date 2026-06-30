"""
Rebuild PRANA_Message_Taxonomy.html from the authoritative locale JSON.
Run any time errors.py / messages.py / en.json are updated.
"""
import json, re
from pathlib import Path

SRC  = Path("C:/Nilesh/claude-code/prana-portal/src/i18n/en.json")
DEST = Path("C:/Nilesh/claude-code/prana-docs/wireframes/PRANA_Message_Taxonomy.html")

data = json.loads(SRC.read_text(encoding="utf-8"))

# Codes that Temporal treats as non-retryable (pipeline errors only)
NR = {
    "S03_SCAN_VIRUS_DETECTED","S03_SCAN_NSFW_EXPLICIT","S03_SCAN_CSAM_DETECTED",
    "S05_RESOLVE_CROSS_TENANT","S04_EXTRACT_PASSWORD_PROTECTED","S04_EXTRACT_CORRUPTED",
    "S06_ROUTE_LEGAL_HOLD_BLOCK","S06_ROUTE_ALREADY_TERMINAL",
    "S04_EXTRACT_OCR_BLANK_OUTPUT","S04_EXTRACT_DARK_IMAGE",
}

# Build JS-safe locale blob (strip _meta)
locale_for_js = {k: v for k, v in data.items() if k != "_meta"}
locale_js = json.dumps(locale_for_js, ensure_ascii=False, separators=(",", ":"))

# Counts
counts = {cat: len(entries) for cat, entries in locale_for_js.items()}
total = sum(counts.values())

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PRANA — Message Taxonomy</title>
<style>
  :root {{
    --bg:#f8f7f4; --surface:#fff; --border:rgba(0,0,0,0.08); --border-strong:rgba(0,0,0,0.14);
    --text:#0b0b0b; --text-2:#52514e; --text-3:#898781; --radius:8px;
    --api-bg:#e6f1fb; --api-border:#b5d4f4; --api-text:#0c447c; --api-dot:#185fa5;
    --ai-bg:#eaf3de;  --ai-border:#c0dd97;  --ai-text:#3b6d11;  --ai-dot:#639922;
    --ask-bg:#faeeda; --ask-border:#fac775; --ask-text:#854f0b; --ask-dot:#ba7517;
    --cat-error:#fcebeb;   --cat-error-t:#a32d2d;  --cat-error-b:#f7c1c1;
    --cat-success:#eaf3de; --cat-success-t:#3b6d11; --cat-success-b:#c0dd97;
    --cat-info:#e6f1fb;    --cat-info-t:#0c447c;    --cat-info-b:#b5d4f4;
    --cat-valid:#faeeda;   --cat-valid-t:#854f0b;   --cat-valid-b:#fac775;
    --cat-status:#f1efe8;  --cat-status-t:#444441;  --cat-status-b:#d3d1c7;
    --cat-pipe:#eaf3de;    --cat-pipe-t:#3b6d11;    --cat-pipe-b:#c0dd97;
    --nr-bg:#fcebeb; --nr-t:#a32d2d; --nr-b:#f7c1c1;
  }}
  @media(prefers-color-scheme:dark){{
    :root{{
      --bg:#1a1a19; --surface:#232321; --border:rgba(255,255,255,0.08); --border-strong:rgba(255,255,255,0.14);
      --text:#fff; --text-2:#c3c2b7; --text-3:#898781;
      --api-bg:#0c2a4a; --api-border:#185fa5; --api-text:#85b7eb; --api-dot:#378add;
      --ai-bg:#172d0a; --ai-border:#3b6d11; --ai-text:#c0dd97; --ai-dot:#97c459;
      --ask-bg:#2c1e06; --ask-border:#854f0b; --ask-text:#fac775; --ask-dot:#ef9f27;
      --cat-error:#2a0f0f; --cat-error-t:#f09595; --cat-error-b:#791f1f;
      --cat-success:#172d0a; --cat-success-t:#c0dd97; --cat-success-b:#3b6d11;
      --cat-info:#0c2a4a; --cat-info-t:#85b7eb; --cat-info-b:#185fa5;
      --cat-valid:#2c1e06; --cat-valid-t:#fac775; --cat-valid-b:#854f0b;
      --cat-status:#2c2c2a; --cat-status-t:#b4b2a9; --cat-status-b:#5f5e5a;
      --cat-pipe:#172d0a; --cat-pipe-t:#c0dd97; --cat-pipe-b:#3b6d11;
      --nr-bg:#2a0f0f; --nr-t:#f09595; --nr-b:#791f1f;
    }}
  }}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);font-size:14px;line-height:1.5;}}
  .page{{max-width:1300px;margin:0 auto;padding:32px 24px 80px;}}
  h1{{font-size:22px;font-weight:500;margin-bottom:4px;}}
  .sub{{font-size:13px;color:var(--text-2);margin-bottom:6px;}}
  .meta{{font-size:11px;color:var(--text-3);margin-bottom:24px;}}
  .stats{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:24px;}}
  .sc{{background:var(--surface);border:0.5px solid var(--border);border-radius:var(--radius);padding:10px 14px;min-width:110px;}}
  .sc-label{{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--text-3);margin-bottom:3px;}}
  .sc-val{{font-size:20px;font-weight:500;}}
  .sc-sub{{font-size:11px;color:var(--text-3);}}
  .controls{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:14px;}}
  .sw{{position:relative;flex:1;min-width:200px;max-width:340px;}}
  .sw svg{{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--text-3);width:14px;height:14px;}}
  input[type=search]{{width:100%;padding:7px 10px 7px 30px;border:0.5px solid var(--border-strong);border-radius:var(--radius);background:var(--surface);color:var(--text);font-size:13px;outline:none;}}
  input[type=search]:focus{{border-color:#378add;box-shadow:0 0 0 3px rgba(55,138,221,.15);}}
  .fg{{display:flex;gap:5px;flex-wrap:wrap;}}
  .fb{{padding:4px 11px;border:0.5px solid var(--border-strong);border-radius:16px;background:var(--surface);color:var(--text-2);font-size:12px;cursor:pointer;transition:all .12s;white-space:nowrap;}}
  .fb:hover{{background:var(--bg);}}
  .fb.on{{background:#185fa5;border-color:#185fa5;color:#fff;}}
  .fb.on.cat-error{{background:#a32d2d;border-color:#a32d2d;}}
  .fb.on.cat-success{{background:#3b6d11;border-color:#3b6d11;}}
  .fb.on.cat-info{{background:#185fa5;border-color:#185fa5;}}
  .fb.on.cat-valid{{background:#854f0b;border-color:#854f0b;}}
  .fb.on.cat-status{{background:#444441;border-color:#444441;}}
  .fb.on.svc-ai{{background:#639922;border-color:#639922;}}
  .fb.on.svc-ask{{background:#ba7517;border-color:#ba7517;}}
  .fb.on.nr{{background:#a32d2d;border-color:#a32d2d;}}
  .fb.on.cat-ui{{background:#5b2d9e;border-color:#5b2d9e;color:#fff;}}
  .fb.on.svc-fe{{background:#5b2d9e;border-color:#5b2d9e;}}
  .nb{{display:inline-flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.08);border-radius:10px;font-size:11px;color:inherit;padding:0 6px;margin-left:5px;}}
  .tw{{background:var(--surface);border:0.5px solid var(--border);border-radius:12px;overflow:hidden;}}
  table{{width:100%;border-collapse:collapse;table-layout:fixed;}}
  col.cc{{width:30%;}} col.cv{{width:42%;}} col.cs{{width:80px;}} col.cd{{width:13%;}} col.cr{{width:80px;}}
  th{{background:var(--bg);text-align:left;padding:8px 13px;font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:.05em;color:var(--text-3);border-bottom:0.5px solid var(--border);position:sticky;top:0;z-index:2;}}
  td{{padding:8px 13px;border-bottom:0.5px solid var(--border);vertical-align:middle;}}
  tr:last-child td{{border-bottom:none;}}
  tr:hover td{{background:var(--bg);}}
  .gsep td{{background:var(--bg);color:var(--text-3);font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:.06em;padding:5px 13px;border-bottom:0.5px solid var(--border);}}
  .cc-cell{{display:flex;align-items:center;gap:6px;}}
  .code{{font-family:'SF Mono','Fira Code',Consolas,monospace;font-size:12px;color:var(--text);word-break:break-all;}}
  .cpbtn{{opacity:0;border:none;background:none;cursor:pointer;color:var(--text-3);padding:2px;border-radius:3px;}}
  tr:hover .cpbtn{{opacity:1;}}
  .cpbtn:hover{{background:var(--bg);}}
  .cat{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:500;border:0.5px solid transparent;white-space:nowrap;}}
  .cat-error  {{background:var(--cat-error);  color:var(--cat-error-t);  border-color:var(--cat-error-b);}}
  .cat-success{{background:var(--cat-success);color:var(--cat-success-t);border-color:var(--cat-success-b);}}
  .cat-info   {{background:var(--cat-info);   color:var(--cat-info-t);   border-color:var(--cat-info-b);}}
  .cat-valid  {{background:var(--cat-valid);  color:var(--cat-valid-t);  border-color:var(--cat-valid-b);}}
  .cat-status {{background:var(--cat-status); color:var(--cat-status-t); border-color:var(--cat-status-b);}}
  .cat-pipe   {{background:var(--cat-pipe);   color:var(--cat-pipe-t);   border-color:var(--cat-pipe-b);}}
  .cat-ui     {{background:#f0ebfb;color:#5b2d9e;border-color:#cdb5f5;}}
  .svc{{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:500;border:0.5px solid transparent;white-space:nowrap;}}
  .svc-api{{background:var(--api-bg);color:var(--api-text);border-color:var(--api-border);}}
  .svc-ai {{background:var(--ai-bg); color:var(--ai-text); border-color:var(--ai-border);}}
  .svc-ask{{background:var(--ask-bg);color:var(--ask-text);border-color:var(--ask-border);}}
  .svc-fe {{background:#f0ebfb;color:#5b2d9e;border-color:#cdb5f5;}}
  .dot{{width:5px;height:5px;border-radius:50%;flex-shrink:0;}}
  .d-api{{background:var(--api-dot);}} .d-ai{{background:var(--ai-dot);}} .d-ask{{background:var(--ask-dot);}} .d-fe{{background:#7c3aed;}}
  .nr-badge{{display:inline-block;padding:2px 7px;border-radius:10px;font-size:11px;background:var(--nr-bg);color:var(--nr-t);border:0.5px solid var(--nr-b);}}
  .lv{{font-size:12px;color:var(--text-2);font-style:italic;}}
  .empty{{text-align:center;padding:48px;color:var(--text-3);font-size:13px;}}
  .toast{{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:#232321;color:#fff;font-size:12px;padding:5px 14px;border-radius:16px;opacity:0;transition:opacity .18s;pointer-events:none;z-index:99;}}
  .toast.show{{opacity:1;}}
</style>
</head>
<body>
<div class="page">
  <h1>PRANA &mdash; Message Taxonomy</h1>
  <p class="sub">Every code the backend emits and the frontend renders. Zero hardcoded strings. Adding a language = adding one JSON file.</p>
  <p class="meta">Generated from <code>prana-portal/src/i18n/en.json</code> &nbsp;&middot;&nbsp; {total} codes total &nbsp;&middot;&nbsp; Enforced by MSG-01 / MSG-02 in enforce_rules.py</p>

  <div class="stats">
    <div class="sc"><div class="sc-label">Total</div><div class="sc-val" id="s-total">{total}</div><div class="sc-sub">4 services &middot; 8 categories</div></div>
    <div class="sc"><div class="sc-label">Error</div><div class="sc-val" id="s-error" style="color:var(--cat-error-t)">{counts.get('error',0)}</div><div class="sc-sub">PranaError</div></div>
    <div class="sc"><div class="sc-label">Success</div><div class="sc-val" id="s-success" style="color:var(--cat-success-t)">{counts.get('success',0)}</div><div class="sc-sub">SuccessCode</div></div>
    <div class="sc"><div class="sc-label">Info</div><div class="sc-val" id="s-info" style="color:var(--cat-info-t)">{counts.get('info',0)}</div><div class="sc-sub">InfoCode</div></div>
    <div class="sc"><div class="sc-label">Validation</div><div class="sc-val" id="s-valid" style="color:var(--cat-valid-t)">{counts.get('validation',0)}</div><div class="sc-sub">ValidationCode</div></div>
    <div class="sc"><div class="sc-label">Status</div><div class="sc-val" id="s-status" style="color:var(--cat-status-t)">{counts.get('status',0)}</div><div class="sc-sub">StatusCode</div></div>
    <div class="sc"><div class="sc-label">Pipeline</div><div class="sc-val" id="s-pipe" style="color:var(--cat-pipe-t)">{counts.get('pipeline_error',0)}</div><div class="sc-sub">PipelineError</div></div>
    <div class="sc"><div class="sc-label">Ask</div><div class="sc-val" id="s-ask" style="color:var(--ask-dot)">{counts.get('ask_error',0)}</div><div class="sc-sub">AskError</div></div>
    <div class="sc"><div class="sc-label">UI Copy</div><div class="sc-val" id="s-ui" style="color:#5b2d9e">{counts.get('ui',0)}</div><div class="sc-sub">tUi() — frontend only</div></div>
    <div class="sc"><div class="sc-label">Non-retry</div><div class="sc-val" id="s-nr" style="color:var(--cat-error-t)">10</div><div class="sc-sub">Temporal fails fast</div></div>
  </div>

  <div class="controls">
    <div class="sw">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input type="search" id="search" placeholder="Search code or display text&hellip;" autocomplete="off">
    </div>
    <div class="fg" id="fg-cat">
      <button class="fb on" data-cat="all">All <span class="nb" id="fb-all">{total}</span></button>
      <button class="fb cat-error"   data-cat="error">Error <span class="nb" id="fb-error">{counts.get('error',0)}</span></button>
      <button class="fb cat-success" data-cat="success">Success <span class="nb" id="fb-success">{counts.get('success',0)}</span></button>
      <button class="fb cat-info"    data-cat="info">Info <span class="nb" id="fb-info">{counts.get('info',0)}</span></button>
      <button class="fb cat-valid"   data-cat="validation">Validation <span class="nb" id="fb-valid">{counts.get('validation',0)}</span></button>
      <button class="fb cat-status"  data-cat="status">Status <span class="nb" id="fb-status">{counts.get('status',0)}</span></button>
      <button class="fb cat-pipe"    data-cat="pipeline_error">Pipeline <span class="nb" id="fb-pipe">{counts.get('pipeline_error',0)}</span></button>
      <button class="fb"             data-cat="ask_error">Ask <span class="nb" id="fb-ask">{counts.get('ask_error',0)}</span></button>
      <button class="fb cat-ui"      data-cat="ui">UI Copy <span class="nb" id="fb-ui">{counts.get('ui',0)}</span></button>
    </div>
    <div class="fg" id="fg-svc">
      <button class="fb on" data-svc="all">All services</button>
      <button class="fb svc-api" data-svc="prana-api">prana-api</button>
      <button class="fb svc-ai"  data-svc="prana-ai">prana-ai</button>
      <button class="fb svc-ask" data-svc="prana-ask">prana-ask</button>
      <button class="fb svc-fe"  data-svc="frontend">frontend</button>
    </div>
    <button class="fb nr" id="btn-nr">Non-retryable only</button>
  </div>

  <div class="tw">
    <table id="tbl">
      <colgroup><col class="cc"><col class="cv"><col class="cs"><col class="cd"><col class="cr"></colgroup>
      <thead><tr>
        <th>Code</th><th>English (en-IN)</th><th>Service</th><th>Category</th><th>Non-retry</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table>
    <div class="empty" id="empty" style="display:none">No matching codes</div>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
const NR = new Set({json.dumps(list(NR))});
const LOCALE = {locale_js};
const SVC_MAP = {{"error":"prana-api","success":"prana-api","info":"prana-api","validation":"prana-api","status":"prana-api","pipeline_error":"prana-ai","ask_error":"prana-ask","ui":"frontend"}};
const CAT_LABEL = {{"error":"Error","success":"Success","info":"Info","validation":"Validation","status":"Status","pipeline_error":"Pipeline","ask_error":"Ask","ui":"UI Copy"}};
const CAT_CLASS = {{"error":"cat-error","success":"cat-success","info":"cat-info","validation":"cat-valid","status":"cat-status","pipeline_error":"cat-pipe","ask_error":"cat-pipe","ui":"cat-ui"}};

const ALL_ROWS = [];
for (const [cat, entries] of Object.entries(LOCALE)) {{
  for (const [code, locale] of Object.entries(entries)) {{
    ALL_ROWS.push({{ cat, code, locale, svc: SVC_MAP[cat] || "prana-api" }});
  }}
}}

let activeCat = "all", activeSvc = "all", nrOnly = false, query = "";

function render() {{
  const q = query.toLowerCase();
  const tbody = document.getElementById("tbody");
  tbody.innerHTML = "";
  let lastGroup = null, vis = 0;
  for (const row of ALL_ROWS) {{
    if (activeCat !== "all" && row.cat !== activeCat) continue;
    if (activeSvc !== "all" && row.svc !== activeSvc) continue;
    if (nrOnly && !NR.has(row.code)) continue;
    if (q && !row.code.toLowerCase().includes(q) && !row.locale.toLowerCase().includes(q) && !row.cat.includes(q)) continue;
    const group = row.svc + "||" + row.cat;
    if (group !== lastGroup) {{
      const sep = document.createElement("tr");
      sep.className = "gsep";
      sep.innerHTML = `<td colspan="5">${{row.svc}} &mdash; ${{CAT_LABEL[row.cat] || row.cat}}</td>`;
      tbody.appendChild(sep);
      lastGroup = group;
    }}
    const svcKey = {{"prana-api":"api","prana-ai":"ai","prana-ask":"ask","frontend":"fe"}}[row.svc] || "api";
    const catCls = CAT_CLASS[row.cat] || "cat-error";
    const nr = NR.has(row.code) ? '<span class="nr-badge">&#x2717; no</span>' : "";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><div class="cc-cell">
        <span class="code">${{row.code}}</span>
        <button class="cpbtn" title="Copy" onclick="cp(this,'${{row.code}}')">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        </button>
      </div></td>
      <td><span class="lv">${{row.locale}}</span></td>
      <td><span class="svc svc-${{svcKey}}"><span class="dot d-${{svcKey}}"></span>${{row.svc}}</span></td>
      <td><span class="cat ${{catCls}}">${{CAT_LABEL[row.cat] || row.cat}}</span></td>
      <td>${{nr}}</td>
    `;
    tbody.appendChild(tr);
    vis++;
  }}
  document.getElementById("empty").style.display = vis === 0 ? "block" : "none";
}}

document.getElementById("search").addEventListener("input", e => {{ query = e.target.value; render(); }});
document.getElementById("fg-cat").addEventListener("click", e => {{
  const btn = e.target.closest("[data-cat]"); if (!btn) return;
  activeCat = btn.dataset.cat;
  document.querySelectorAll("[data-cat]").forEach(b => b.classList.remove("on"));
  btn.classList.add("on"); render();
}});
document.getElementById("fg-svc").addEventListener("click", e => {{
  const btn = e.target.closest("[data-svc]"); if (!btn) return;
  activeSvc = btn.dataset.svc;
  document.querySelectorAll("[data-svc]").forEach(b => b.classList.remove("on"));
  btn.classList.add("on"); render();
}});
document.getElementById("btn-nr").addEventListener("click", e => {{
  nrOnly = !nrOnly; e.target.classList.toggle("on", nrOnly); render();
}});
function cp(btn, code) {{
  navigator.clipboard.writeText(code).then(() => {{
    const t = document.getElementById("toast");
    t.textContent = "Copied " + code;
    t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 1400);
  }});
}}
render();
</script>
</body>
</html>"""

DEST.write_text(html, encoding="utf-8")
print(f"Written: {DEST}")
print(f"Total codes: {total}")
for cat, n in counts.items():
    print(f"  {cat}: {n}")
