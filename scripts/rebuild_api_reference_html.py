"""
Rebuild PRANA_API_Reference.html from the live FastAPI OpenAPI schema.

Unlike the other prana-docs pages, this one is generated straight from
`app.openapi()` plus a reflection pass over `app.routes` to recover the
role/tenant-type each endpoint requires (FastAPI's OpenAPI output doesn't
encode custom Depends()-based RBAC, only "some bearer token required").

Run any time a router/endpoint changes:
    cd prana-api && python ../scripts/rebuild_api_reference_html.py
"""
import inspect
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path("C:/Nilesh/claude-code/prana-api")))

warnings.filterwarnings("ignore")  # duplicate operationId warnings — cosmetic only

from fastapi import params as fastapi_params           # noqa: E402
from fastapi.routing import APIRoute                    # noqa: E402
from main import app                                    # noqa: E402

DEST = Path("C:/Nilesh/claude-code/prana-docs/wireframes/PRANA_API_Reference.html")

TAG_LABELS = {
    "auth": "Authentication", "admin": "Platform Admin (PA)", "public": "Public",
    "totp": "TOTP Setup", "v1:alumni": "Alumni Network", "v1:ask": "Ask PRANA (Chatbot)",
    "v1:benchmarking": "Compensation Benchmarking", "v1:cfo": "CFO Dashboard",
    "v1:chro": "CHRO Dashboard", "v1:ciso": "CISO Dashboard", "v1:compliance": "Vault Compliance",
    "v1:dpdp": "DPDP Rights", "v1:elevations": "Access Elevation", "v1:employees": "Employee Management (OA)",
    "v1:exceptions": "Exception Queue", "v1:gamification": "Gamification",
    "v1:hrms-admin": "HRMS Definitions (PA)", "v1:hrms-config": "HRMS Config (OA)",
    "v1:hrms-webhook": "HRMS Webhook (inbound)", "v1:ingest": "Document Ingest (HRMS)",
    "v1:labour-law": "Labour Law / Statutory", "v1:manifests": "Doc Manifests",
    "v1:org": "Org / OA Users", "v1:share": "Document Sharing", "v1:vault": "Employee Vault",
    "internal": "Internal (prana-ai only)",
}

METHOD_ORDER = {"GET": 0, "POST": 1, "PATCH": 2, "PUT": 3, "DELETE": 4}


# ── Role/auth reflection ─────────────────────────────────────────────────────

def _closure_roles(func):
    try:
        cv = inspect.getclosurevars(func)
    except TypeError:
        return None
    return cv.nonlocals.get("roles")


def describe_auth(route: APIRoute) -> str:
    deps = list(route.dependencies)
    try:
        sig = inspect.signature(route.endpoint)
    except (TypeError, ValueError):
        sig = None
    if sig:
        for _, p in sig.parameters.items():
            if isinstance(p.default, fastapi_params.Depends):
                deps.append(p.default)
            anno = p.annotation
            for meta in getattr(anno, "__metadata__", ()):
                if isinstance(meta, fastapi_params.Depends):
                    deps.append(meta)

    role_sets: set[str] = set()
    has_pa = has_employee = has_bearer_only = False
    for d in deps:
        func = d.dependency
        fname = getattr(func, "__name__", "")
        if fname == "require_pa":
            has_pa = True
        elif fname == "require_employee":
            has_employee = True
        elif fname == "_decode_bearer":
            has_bearer_only = True
        roles = _closure_roles(func)
        if roles:
            role_sets.update(roles)

    if has_pa:
        return "Portal Admin (PA)"
    if has_employee:
        return "Employee"
    if role_sets:
        return "OA user — role: " + ", ".join(sorted(role_sets))
    if has_bearer_only:
        return "Authenticated (any role)"
    if route.path.startswith("/internal/"):
        return "Internal service header (X-Internal-Service)"
    if route.path.startswith("/v1/hrms/webhook") or route.path.startswith("/v1/ingest"):
        return "HRMS API key (HMAC-signed)"
    return "None (public)"


def build_auth_map() -> dict[tuple[str, str], str]:
    out = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        desc = describe_auth(route)
        for m in route.methods:
            if m in ("HEAD", "OPTIONS"):
                continue
            out[(route.path, m)] = desc
    return out


# ── OpenAPI schema flattening ────────────────────────────────────────────────

def describe_type(schema: dict) -> str:
    if not schema:
        return "any"
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    if "anyOf" in schema:
        parts = [describe_type(s) for s in schema["anyOf"]]
        return " | ".join(dict.fromkeys(parts))  # dedupe, preserve order
    t = schema.get("type", "any")
    if t == "array":
        return f"array<{describe_type(schema.get('items', {}))}>"
    if schema.get("format"):
        return f"{t}({schema['format']})"
    if schema.get("enum"):
        return f"enum[{', '.join(map(str, schema['enum']))}]"
    return t


def flatten_schema(schema: dict, components: dict, depth: int = 0) -> list[dict]:
    """Resolve one $ref hop and return a flat field list. depth guards recursion."""
    if depth > 2 or not schema:
        return []
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        target = components.get(name, {})
        return flatten_schema(target, components, depth + 1)
    props = schema.get("properties")
    if not props:
        return []
    required = set(schema.get("required", []))
    fields = []
    for pname, pschema in props.items():
        fields.append({
            "name": pname,
            "type": describe_type(pschema),
            "required": pname in required,
            "description": pschema.get("description", ""),
        })
    return fields


# ── Build the flat endpoint list ─────────────────────────────────────────────

def build_endpoints():
    spec = app.openapi()
    components = spec.get("components", {}).get("schemas", {})
    auth_map = build_auth_map()

    endpoints = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            if not isinstance(op, dict) or method.upper() not in METHOD_ORDER:
                continue
            method_u = method.upper()
            tag = (op.get("tags") or ["untagged"])[0]

            params = []
            for p in op.get("parameters", []):
                sch = p.get("schema", {})
                params.append({
                    "name": p["name"], "in": p["in"],
                    "required": p.get("required", False),
                    "type": describe_type(sch),
                    "default": sch.get("default"),
                })

            req_body = []
            rb = op.get("requestBody", {})
            body_schema = rb.get("content", {}).get("application/json", {}).get("schema", {})
            if body_schema:
                req_body = flatten_schema(body_schema, components)

            resp_body = []
            resp_note = ""
            r200 = op.get("responses", {}).get("200", {})
            r200_schema = r200.get("content", {}).get("application/json", {}).get("schema", {})
            if r200_schema:
                resp_body = flatten_schema(r200_schema, components)
                if not resp_body:
                    resp_note = "Not modeled as a Pydantic response_model — returns a serialized " \
                                 "dict per the response shape contract " \
                                 "({\"items\": [...], \"total\": N} or {\"resource_name\": {...}})."

            endpoints.append({
                "method": method_u, "path": path, "tag": tag,
                "summary": op.get("summary", ""), "description": op.get("description", ""),
                "operationId": op.get("operationId", ""),
                "params": params, "req_body": req_body,
                "resp_body": resp_body, "resp_note": resp_note,
                "auth": auth_map.get((path, method_u), "Unknown"),
                "deprecated": bool(op.get("deprecated")),
            })

    endpoints.sort(key=lambda e: (e["tag"], e["path"], METHOD_ORDER[e["method"]]))
    return endpoints


# ── HTML render ───────────────────────────────────────────────────────────────

def render(endpoints):
    tags_order = []
    for e in endpoints:
        if e["tag"] not in tags_order:
            tags_order.append(e["tag"])
    tag_counts = {t: sum(1 for e in endpoints if e["tag"] == t) for t in tags_order}

    data_json = json.dumps(endpoints, ensure_ascii=False, separators=(",", ":"))
    sidebar_links = "\n".join(
        f'<a href="#tag-{t}" class="sidebar-link" data-tag="{t}">'
        f'{TAG_LABELS.get(t, t)} <span class="count">{tag_counts[t]}</span></a>'
        for t in tags_order
    )
    tag_options = "\n".join(
        f'<option value="{t}">{TAG_LABELS.get(t, t)}</option>' for t in tags_order
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PRANA — API Reference</title>
<style>
  :root {{
    --bg:#0F172A; --bg2:#1E293B; --bg3:#253347; --border:#334155; --border2:#475569;
    --text:#F1F5F9; --text2:#CBD5E1; --text3:#94A3B8; --accent:#D4537E; --sky:#0EA5E9;
    --emerald:#10B981; --amber:#F59E0B; --violet:#8B5CF6; --red:#EF4444; --mono:'DM Mono','Fira Code',monospace;
    --get:#0EA5E9; --post:#10B981; --patch:#F59E0B; --put:#8B5CF6; --delete:#EF4444;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--text); font-family:system-ui,sans-serif; font-size:14px; line-height:1.6; }}
  a {{ color:inherit; }}
  .left-sidebar {{ position:fixed; top:0; left:0; bottom:0; width:280px; background:var(--bg2);
    border-right:1px solid var(--border); overflow-y:auto; padding:1.2rem 0 2rem; z-index:100; }}
  .sidebar-brand {{ font-family:var(--mono); font-size:12px; font-weight:700; color:var(--accent);
    letter-spacing:.1em; padding:0 1.2rem 1rem; border-bottom:1px solid var(--border); margin-bottom:.6rem; }}
  .sidebar-meta {{ padding:0 1.2rem 1rem; font-size:11px; color:var(--text3); border-bottom:1px solid var(--border); margin-bottom:.4rem; }}
  .sidebar-link {{ display:flex; justify-content:space-between; padding:.35rem 1.2rem; font-size:12.5px;
    color:var(--text2); text-decoration:none; border-left:2px solid transparent; }}
  .sidebar-link:hover, .sidebar-link.active {{ color:var(--sky); background:rgba(14,165,233,.08); border-left-color:var(--sky); }}
  .sidebar-link .count {{ color:var(--text3); font-family:var(--mono); font-size:10px; }}
  .page-wrap {{ margin-left:280px; max-width:980px; padding:2rem 2rem 6rem; }}
  @media (max-width:1100px) {{ .left-sidebar {{ display:none; }} .page-wrap {{ margin-left:0; }} }}
  .doc-title {{ font-size:30px; font-weight:700; margin-bottom:.4rem; }}
  .doc-subtitle {{ color:var(--text3); font-size:14px; margin-bottom:1.5rem; }}
  .toolbar {{ display:flex; gap:.6rem; margin-bottom:1.8rem; flex-wrap:wrap; position:sticky; top:0;
    background:var(--bg); padding:.8rem 0; z-index:10; }}
  .toolbar input, .toolbar select {{ background:var(--bg2); border:1px solid var(--border); color:var(--text);
    padding:.5rem .8rem; border-radius:6px; font-size:13px; font-family:inherit; }}
  .toolbar input {{ flex:1; min-width:200px; }}
  .tag-section {{ margin-bottom:2.5rem; }}
  .tag-title {{ font-size:18px; font-weight:700; color:var(--text); margin-bottom:.9rem;
    padding-bottom:.5rem; border-bottom:1px solid var(--border); }}
  .ep-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:8px; margin-bottom:.6rem; overflow:hidden; }}
  .ep-row {{ display:flex; align-items:center; gap:.8rem; padding:.7rem 1rem; cursor:pointer; user-select:none; }}
  .ep-row:hover {{ background:var(--bg3); }}
  .method-badge {{ font-family:var(--mono); font-size:11px; font-weight:700; padding:2px 8px; border-radius:4px;
    color:#fff; min-width:52px; text-align:center; flex-shrink:0; }}
  .m-GET {{ background:var(--get); }} .m-POST {{ background:var(--post); }} .m-PATCH {{ background:var(--patch); }}
  .m-PUT {{ background:var(--put); }} .m-DELETE {{ background:var(--red); }}
  .ep-path {{ font-family:var(--mono); font-size:13px; color:var(--text); flex-shrink:0; }}
  .ep-summary {{ color:var(--text3); font-size:12.5px; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .auth-badge {{ font-size:10px; font-family:var(--mono); color:var(--amber); border:1px solid rgba(245,158,11,.3);
    background:rgba(245,158,11,.08); padding:2px 7px; border-radius:4px; white-space:nowrap; flex-shrink:0; }}
  .auth-badge.none {{ color:var(--text3); border-color:var(--border2); background:transparent; }}
  .ep-detail {{ display:none; padding:1rem 1.2rem 1.3rem; border-top:1px solid var(--border); background:rgba(0,0,0,.15); }}
  .ep-detail.open {{ display:block; }}
  .ep-desc {{ color:var(--text2); font-size:13px; margin-bottom:1rem; white-space:pre-line; }}
  .ep-op-id {{ font-family:var(--mono); font-size:10.5px; color:var(--text3); margin-bottom:1rem; }}
  .field-table {{ width:100%; border-collapse:collapse; font-size:12.5px; margin-bottom:1rem; }}
  .field-table th {{ text-align:left; color:var(--text3); font-size:10px; text-transform:uppercase; letter-spacing:.05em;
    padding:.3rem .6rem; border-bottom:1px solid var(--border); font-family:var(--mono); }}
  .field-table td {{ padding:.35rem .6rem; border-bottom:1px solid rgba(255,255,255,.04); vertical-align:top; }}
  .field-name {{ font-family:var(--mono); color:var(--sky); }}
  .field-type {{ font-family:var(--mono); color:var(--violet); font-size:11.5px; }}
  .field-req {{ color:var(--accent); font-size:10px; font-weight:700; }}
  .sub-h {{ font-size:11px; font-weight:700; color:var(--text3); text-transform:uppercase; letter-spacing:.08em;
    margin:.9rem 0 .4rem; font-family:var(--mono); }}
  .resp-note {{ color:var(--text3); font-size:12px; font-style:italic; margin-bottom:1rem; }}
  .empty-note {{ color:var(--text3); font-size:12px; }}
  .hidden {{ display:none !important; }}
</style>
</head>
<body>
  <nav class="left-sidebar">
    <div class="sidebar-brand">PRANA · API REFERENCE</div>
    <div class="sidebar-meta">{len(endpoints)} endpoints · {len(tags_order)} groups<br>Generated from live OpenAPI schema</div>
    {sidebar_links}
  </nav>
  <div class="page-wrap">
    <h1 class="doc-title">PRANA API Reference</h1>
    <p class="doc-subtitle">
      Auto-generated from <code>app.openapi()</code> + role reflection over <code>app.routes</code> —
      always matches the running code. Regenerate with
      <code>python scripts/rebuild_api_reference_html.py</code> after any router change.
      Role/auth requirements are best-effort, reflected from each endpoint's <code>Depends()</code> chain;
      verify against the router source for anything security-critical.
    </p>
    <div class="toolbar">
      <input type="text" id="search" placeholder="Search path, summary, or operation id…">
      <select id="methodFilter">
        <option value="">All methods</option>
        <option>GET</option><option>POST</option><option>PATCH</option><option>PUT</option><option>DELETE</option>
      </select>
      <select id="authFilter">
        <option value="">All auth types</option>
        <option value="Portal Admin">Portal Admin (PA)</option>
        <option value="OA user">OA user (any role)</option>
        <option value="Employee">Employee</option>
        <option value="HRMS">HRMS API key</option>
        <option value="Internal">Internal service</option>
        <option value="None">Public / none</option>
      </select>
    </div>
    <div id="content"></div>
  </div>

<script>
const DATA = {data_json};
const TAG_LABELS = {json.dumps(TAG_LABELS, ensure_ascii=False)};

function fieldRows(fields) {{
  if (!fields.length) return '<div class="empty-note">No fields.</div>';
  return '<table class="field-table"><thead><tr><th>Field</th><th>Type</th><th>Required</th><th>Description</th></tr></thead><tbody>' +
    fields.map(f => `<tr><td class="field-name">${{f.name}}</td><td class="field-type">${{f.type}}</td>` +
      `<td>${{f.required ? '<span class="field-req">REQUIRED</span>' : ''}}</td><td>${{f.description || ''}}</td></tr>`).join('') +
    '</tbody></table>';
}}

function paramRows(params) {{
  if (!params.length) return '';
  return '<div class="sub-h">Parameters</div><table class="field-table"><thead><tr><th>Name</th><th>In</th><th>Type</th><th>Required</th></tr></thead><tbody>' +
    params.map(p => `<tr><td class="field-name">${{p.name}}</td><td>${{p.in}}</td><td class="field-type">${{p.type}}</td>` +
      `<td>${{p.required ? '<span class="field-req">REQUIRED</span>' : ''}}</td></tr>`).join('') +
    '</tbody></table>';
}}

function authClass(auth) {{
  return auth.startsWith('None') ? 'auth-badge none' : 'auth-badge';
}}

function card(e, idx) {{
  const detailId = 'detail-' + idx;
  return `<div class="ep-card" data-path="${{e.path.toLowerCase()}}" data-summary="${{(e.summary||'').toLowerCase()}}"
      data-opid="${{(e.operationId||'').toLowerCase()}}" data-method="${{e.method}}" data-auth="${{e.auth}}">
    <div class="ep-row" onclick="document.getElementById('${{detailId}}').classList.toggle('open')">
      <span class="method-badge m-${{e.method}}">${{e.method}}</span>
      <span class="ep-path">${{e.path}}</span>
      <span class="ep-summary">${{e.summary || ''}}</span>
      <span class="${{authClass(e.auth)}}">${{e.auth}}</span>
    </div>
    <div class="ep-detail" id="${{detailId}}">
      ${{e.description ? `<div class="ep-desc">${{e.description}}</div>` : ''}}
      <div class="ep-op-id">operationId: ${{e.operationId}}</div>
      ${{paramRows(e.params)}}
      ${{e.req_body.length ? '<div class="sub-h">Request Body</div>' + fieldRows(e.req_body) : ''}}
      ${{e.resp_body.length || e.resp_note ? '<div class="sub-h">Response (200)</div>' +
        (e.resp_note ? `<div class="resp-note">${{e.resp_note}}</div>` : fieldRows(e.resp_body)) : ''}}
    </div>
  </div>`;
}}

function render() {{
  const byTag = {{}};
  DATA.forEach((e, i) => {{ (byTag[e.tag] = byTag[e.tag] || []).push([e, i]); }});
  const parts = [];
  Object.keys(byTag).forEach(tag => {{
    parts.push(`<div class="tag-section" id="tag-${{tag}}"><div class="tag-title">${{TAG_LABELS[tag] || tag}}</div>` +
      byTag[tag].map(([e, i]) => card(e, i)).join('') + '</div>');
  }});
  document.getElementById('content').innerHTML = parts.join('');
}}
render();

function applyFilters() {{
  const q = document.getElementById('search').value.toLowerCase();
  const method = document.getElementById('methodFilter').value;
  const auth = document.getElementById('authFilter').value;
  document.querySelectorAll('.ep-card').forEach(card => {{
    const matchesQ = !q || card.dataset.path.includes(q) || card.dataset.summary.includes(q) || card.dataset.opid.includes(q);
    const matchesM = !method || card.dataset.method === method;
    const matchesA = !auth || card.dataset.auth.includes(auth);
    card.classList.toggle('hidden', !(matchesQ && matchesM && matchesA));
  }});
  document.querySelectorAll('.tag-section').forEach(sec => {{
    const anyVisible = [...sec.querySelectorAll('.ep-card')].some(c => !c.classList.contains('hidden'));
    sec.classList.toggle('hidden', !anyVisible);
  }});
}}
document.getElementById('search').addEventListener('input', applyFilters);
document.getElementById('methodFilter').addEventListener('change', applyFilters);
document.getElementById('authFilter').addEventListener('change', applyFilters);
</script>
</body>
</html>"""
    return html


if __name__ == "__main__":
    endpoints = build_endpoints()
    DEST.write_text(render(endpoints), encoding="utf-8")
    print(f"Written: {DEST}")
    print(f"Total endpoints: {len(endpoints)}")
