"""
Rebuild PRANA_Admin_Manual.html — role-wise admin reference covering the
ENTIRE admin surface of the platform, not just the housekeeping actions.

Two layers per role tab:
  1. Curated "Housekeeping" cards (hand-written, hardcoded below) — the
     TOTP/password reset, unlock, reactivate, bulk-revoke, CSV import,
     merge, resend-welcome actions, with gotchas and irreversibility notes
     that don't come from the OpenAPI schema.
  2. Auto-generated "Full endpoint catalogue" — every other endpoint that
     role can call, pulled live from app.openapi() + role reflection over
     app.routes (same mechanism as rebuild_api_reference_html.py), grouped
     by functional area. Always matches the running code.

Run any time a router/endpoint or role gate changes:
    cd prana-api && python ../scripts/rebuild_admin_manual_html.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path("C:/Nilesh/claude-code/scripts")))
import rebuild_api_reference_html as api_ref  # noqa: E402

DEST = Path("C:/Nilesh/claude-code/prana-docs/wireframes/PRANA_Admin_Manual.html")

ROLES = [
    ("pa", "Portal Admin (PA)",
     "PRANA's platform-level operator role, spanning every tenant rather than being scoped to "
     "one organisation. PA normally has a \"zero employee PII\" boundary; any action that touches "
     "employee PII is a deliberate, narrow exception requiring a mandatory <code>reason</code> field, "
     "logged with the action."),
    ("oa_admin", "OA-Admin",
     "The senior admin role inside one tenant, with full read/write over that tenant's employees, "
     "OA users, exceptions, elevations, and config. Every action is scoped to the caller's own "
     "<code>tenant_id</code> from the JWT, never from the request. The broadest role by endpoint count "
     "since most tenant-scoped admin actions fall back to it."),
    ("oa_operator", "OA-Operator",
     "The day-to-day operations role inside one tenant, narrower than OA-Admin. Handles ingest, "
     "exception triage, and bulk onboarding, but not account-security actions like password/TOTP "
     "resets or user role changes."),
    ("ciso", "CISO",
     "Primarily a <i>read</i> role, with full visibility into every admin action across the tenant "
     "(including IP addresses, where employees see city-level only). A small set of incident-response "
     "actions are delegated directly to CISO so they don't have to wait on OA-Admin."),
    ("chro", "CHRO",
     "HR-leadership dashboards and workforce analytics for one tenant: alumni network, career "
     "insights, digest/alert configuration, labour-law obligations."),
    ("cfo", "CFO",
     "Finance-leadership dashboards for one tenant: compensation benchmarking, cost/vault analytics, "
     "digest configuration."),
]

# ── Curated housekeeping cards, per role key ─────────────────────────────────

HOUSEKEEPING = {
    "pa": """
    <div class="card">
      <div class="card-head"><div class="card-title">Reset employee TOTP (platform override)</div>
        <div class="badges"><span class="badge b-post">POST</span><span class="badge b-reason">REASON REQUIRED</span></div></div>
      <div class="card-body"><div class="endpoint">POST <code>/admin/employees/reset-totp</code></div>
      Clears the employee's <code>totp_secret_enc</code> for any tenant, forcing re-enrollment on next login.
      Use when OA-Admin isn't available or the employee spans multiple tenants.</div>
    </div>
    <div class="card">
      <div class="card-head"><div class="card-title">Reset employee password (platform override)</div>
        <div class="badges"><span class="badge b-post">POST</span><span class="badge b-reason">REASON REQUIRED</span></div></div>
      <div class="card-body"><div class="endpoint">POST <code>/admin/employees/reset-password</code></div>
      Generates a one-time temp password (shown once, never logged) and sets <code>force_reset=TRUE</code>.
      Works across any tenant, unlike the OA-Admin version which is tenant-scoped.</div>
    </div>
    <div class="card">
      <div class="card-head"><div class="card-title">Unlock a fellow Portal Admin</div>
        <div class="badges"><span class="badge b-post">POST</span></div></div>
      <div class="card-body"><div class="endpoint">POST <code>/admin/pa-users/unlock</code></div>
      The "someone else holds the keys" recovery path: a locked-out PA cannot unlock themselves, only
      another active PA can. No <code>reason</code> required since PA-to-PA has no PII exposure.</div>
    </div>
    <div class="card">
      <div class="card-head"><div class="card-title">Merge duplicate employee records</div>
        <div class="badges"><span class="badge b-post">POST</span><span class="badge b-reason">REASON REQUIRED</span><span class="badge b-danger">IRREVERSIBLE</span></div></div>
      <div class="card-body"><div class="endpoint">POST <code>/admin/employees/merge</code></div>
      For PAN-typo duplicate identities: two <code>employee_user</code> rows that are the same person.
      Re-points every FK'd table onto the canonical record in one transaction, then marks the duplicate
      <code>status='MERGED'</code> (never deletes it; see <code>prana-db/migrations/038_employee_merge.sql</code>).
      <b>There is no "unmerge."</b> Confirm identity match carefully before running.</div>
    </div>
    <div class="also">
      <div class="also-title">Also available to PA (pre-existing, not part of the housekeeping set)</div>
      <div class="mini-card"><b>OA emergency create / suspend / reset</b>: <code>POST /admin/oa-emergency/create|suspend|reset</code>.
        Break-glass creation, suspension, or password reset of an OA-Admin account for a tenant, when the
        tenant has no working OA-Admin left to self-serve. Reason required, logged as <code>PA_EMERGENCY_OVERRIDE</code>.</div>
      <div class="mini-card"><b>Tenant management</b>: <code>/admin/tenants/*</code> (list, activate, suspend). Platform-wide
        tenant lifecycle, not employee-scoped.</div>
    </div>
""",
    "oa_admin": """
    <div class="card">
      <div class="card-head"><div class="card-title">Reset employee TOTP</div><div class="badges"><span class="badge b-post">POST</span></div></div>
      <div class="card-body"><div class="endpoint">POST <code>/v1/org/employees/reset-totp</code></div>
      Clears the employee's TOTP secret, forcing re-enrollment. Use when an employee has lost their authenticator app/device.</div>
    </div>
    <div class="card">
      <div class="card-head"><div class="card-title">Reset employee password</div><div class="badges"><span class="badge b-post">POST</span></div></div>
      <div class="card-body"><div class="endpoint">POST <code>/v1/org/employees/reset-password</code></div>
      Generates a one-time temp password (shown once) and sets <code>force_reset=TRUE</code> so the employee must
      set a new password on next login. Looked up by email or mobile, own tenant only.</div>
    </div>
    <div class="card">
      <div class="card-head"><div class="card-title">Un-mark alumni / reactivate</div><div class="badges"><span class="badge b-post">POST</span></div></div>
      <div class="card-body"><div class="endpoint">POST <code>/v1/org/employees/{employee_uuid}/reactivate</code></div>
      Reverses <code>mark_alumni</code>. Employee must currently be <code>ALUMNI</code>. Clears <code>dol</code> and
      <code>push_window_expires</code>, sets status back to <code>ACTIVE</code>, records a <code>REJOINED</code> career event.</div>
    </div>
    <div class="card">
      <div class="card-head"><div class="card-title">Sign out everywhere (bulk revoke sessions)</div>
        <div class="badges"><span class="badge b-post">POST</span></div></div>
      <div class="card-body"><div class="endpoint">POST <code>/v1/org/employees/{employee_uuid}/revoke-sessions</code></div>
      Revokes every active session for the employee in one action, e.g. after a lost/stolen device report.
      Shared with CISO.</div>
    </div>
    <div class="card">
      <div class="card-head"><div class="card-title">Revoke all document shares</div><div class="badges"><span class="badge b-post">POST</span></div></div>
      <div class="card-body"><div class="endpoint">POST <code>/v1/org/employees/{employee_uuid}/revoke-shares</code></div>
      Revokes every active document share link the employee has created, invalidating outstanding share URLs
      and OTP sessions immediately. Shared with CISO.</div>
    </div>
    <div class="card">
      <div class="card-head"><div class="card-title">Resend OA welcome email</div><div class="badges"><span class="badge b-post">POST</span></div></div>
      <div class="card-body"><div class="endpoint">POST <code>/v1/org/users/{oa_user_id}/resend-welcome</code></div>
      Re-triggers the <code>OA_WELCOME</code> email template via NotifConsumer, for a bounced original email
      or an expired invite link.</div>
    </div>
""",
    "oa_operator": """
    <div class="card">
      <div class="card-head"><div class="card-title">Bulk employee CSV import</div><div class="badges"><span class="badge b-post">POST</span></div></div>
      <div class="card-body"><div class="endpoint">POST <code>/v1/org/employees/import</code></div>
      Creates employees in bulk from a CSV (max 500 rows; required columns <code>nik</code>, <code>full_name</code>,
      <code>doj</code>). Each row is processed independently: a bad row (missing field, bad date, duplicate NIK)
      is recorded as <code>{"row": i, "error": &lt;code&gt;}</code> without aborting the rest of the batch.</div>
    </div>
""",
    "ciso": """
    <div class="card">
      <div class="card-head"><div class="card-title">Sign out everywhere (bulk revoke sessions)</div>
        <div class="badges"><span class="badge b-post">POST</span></div></div>
      <div class="card-body"><div class="endpoint">POST <code>/v1/org/employees/{employee_uuid}/revoke-sessions</code></div>
      Same endpoint as OA-Admin. CISO can act immediately on a suspected account compromise without waiting
      for an OA-Admin to be available.</div>
    </div>
    <div class="card">
      <div class="card-head"><div class="card-title">Revoke all document shares</div><div class="badges"><span class="badge b-post">POST</span></div></div>
      <div class="card-body"><div class="endpoint">POST <code>/v1/org/employees/{employee_uuid}/revoke-shares</code></div>
      Same endpoint as OA-Admin. Kills any outstanding share links/OTP sessions as an incident-response measure.</div>
    </div>
""",
    "chro": "",
    "cfo": "",
}

FOOTER = """
  <div class="footer-note">
    Explicitly not built: <b>impersonate / "view as employee."</b> Considered and rejected as a housekeeping
    tool: a genuine privacy risk (an admin viewing an employee's vault as them) that isn't part of this
    feature set. Curated write-up: <code>prana-docs/ADMIN_HOUSEKEEPING_GUIDE.md</code>. Full request/response
    schemas for every endpoint below: <a href="PRANA_API_Reference.html" style="color:var(--sky)">API Reference</a>.
    What goes to Immudb: <a href="../KAFKA_REDIS_ARCHITECTURE.md">KAFKA_REDIS_ARCHITECTURE.md &sect;8.2</a>.
  </div>
"""


def endpoint_roles(auth: str) -> set[str]:
    if auth.startswith("Portal Admin"):
        return {"pa"}
    if auth.startswith("OA user"):
        return set(auth.split("role: ", 1)[1].split(", "))
    return set()


def catalogue_html(endpoints, role_key):
    matching = [e for e in endpoints if role_key in endpoint_roles(e["auth"])]
    matching.sort(key=lambda e: (e["tag"], e["path"]))
    by_tag: dict[str, list] = {}
    for e in matching:
        by_tag.setdefault(e["tag"], []).append(e)

    if not matching:
        return '<p class="empty-note">No endpoints reflected for this role beyond the housekeeping actions above.</p>'

    parts = [f'<div class="cat-meta">{len(matching)} endpoints across {len(by_tag)} functional areas.</div>']
    for tag in sorted(by_tag, key=lambda t: api_ref.TAG_LABELS.get(t, t)):
        rows = "".join(
            f'<div class="cat-row" data-path="{e["path"].lower()}" data-summary="{(e["summary"] or "").lower()}">'
            f'<span class="method-badge m-{e["method"]}">{e["method"]}</span>'
            f'<span class="cat-path">{e["path"]}</span>'
            f'<span class="cat-summary">{e["summary"] or ""}</span>'
            f'</div>'
            for e in by_tag[tag]
        )
        parts.append(
            f'<div class="cat-group"><div class="cat-group-title">{api_ref.TAG_LABELS.get(tag, tag)} '
            f'<span class="count">{len(by_tag[tag])}</span></div>{rows}</div>'
        )
    return "".join(parts)


def render():
    endpoints = api_ref.build_endpoints()

    tabs_html = "\n".join(
        f'<div class="tab{" active" if i == 0 else ""}" data-tab="{key}" onclick="switchTab(\'{key}\')">{label}</div>'
        for i, (key, label, _) in enumerate(ROLES)
    )

    panels_html = []
    for i, (key, label, desc) in enumerate(ROLES):
        hk = HOUSEKEEPING.get(key, "")
        hk_section = f'<div class="section-label">Housekeeping (curated)</div>{hk}' if hk.strip() else ""
        cat = catalogue_html(endpoints, key)
        panels_html.append(f"""
  <div class="panel{' active' if i == 0 else ''}" id="panel-{key}">
    <div class="role-desc"><b>{label}</b> is {desc}</div>
    {hk_section}
    <div class="section-label">Full endpoint catalogue (auto-generated)</div>
    <input type="text" class="cat-search" placeholder="Filter {label} endpoints..." oninput="filterCatalogue(this, '{key}')">
    <div id="cat-{key}">{cat}</div>
  </div>""")

    total_role_gated = len({(e["path"], e["method"]) for e in endpoints if endpoint_roles(e["auth"])})

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PRANA — Admin Manual</title>
<style>
  :root {{
    --bg:#0F172A; --bg2:#1E293B; --bg3:#253347; --border:#334155; --border2:#475569;
    --text:#F1F5F9; --text2:#CBD5E1; --text3:#94A3B8; --accent:#D4537E; --sky:#0EA5E9;
    --emerald:#10B981; --amber:#F59E0B; --violet:#8B5CF6; --red:#EF4444; --mono:'DM Mono','Fira Code',monospace;
    --get:#0EA5E9; --post:#10B981; --patch:#F59E0B; --put:#8B5CF6; --delete:#EF4444;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--text); font-family:system-ui,sans-serif; font-size:14px; line-height:1.65; }}
  .wrap {{ max-width:1020px; margin:0 auto; padding:2.5rem 2rem 6rem; }}
  .brand {{ font-family:var(--mono); font-size:12px; font-weight:700; color:var(--accent); letter-spacing:.12em; margin-bottom:.6rem; }}
  h1 {{ font-size:30px; font-weight:700; margin-bottom:.5rem; }}
  .subtitle {{ color:var(--text3); font-size:14px; margin-bottom:2rem; max-width:800px; }}
  .subtitle code {{ color:var(--text2); }}
  .tabs {{ display:flex; gap:.4rem; border-bottom:1px solid var(--border); margin-bottom:2rem; flex-wrap:wrap; }}
  .tab {{ padding:.7rem 1.1rem; font-size:13.5px; font-weight:600; color:var(--text3); cursor:pointer; border-bottom:2px solid transparent; }}
  .tab:hover {{ color:var(--text2); }}
  .tab.active {{ color:var(--sky); border-bottom-color:var(--sky); }}
  .role-desc {{ background:var(--bg2); border:1px solid var(--border); border-left:3px solid var(--sky);
    border-radius:8px; padding:1rem 1.2rem; margin-bottom:1.6rem; font-size:13px; color:var(--text2); }}
  .role-desc b {{ color:var(--text); }}
  .panel {{ display:none; }}
  .panel.active {{ display:block; }}
  .section-label {{ font-size:12px; font-weight:700; color:var(--text3); text-transform:uppercase; letter-spacing:.08em;
    margin:1.6rem 0 .8rem; padding-bottom:.5rem; border-bottom:1px solid var(--border); }}
  .card {{ background:var(--bg2); border:1px solid var(--border); border-radius:10px; margin-bottom:1rem; overflow:hidden; }}
  .card-head {{ padding:1rem 1.3rem; border-bottom:1px solid var(--border); display:flex; align-items:flex-start;
    justify-content:space-between; gap:1rem; flex-wrap:wrap; }}
  .card-title {{ font-size:15.5px; font-weight:700; }}
  .badges {{ display:flex; gap:.4rem; flex-wrap:wrap; }}
  .badge {{ font-family:var(--mono); font-size:10px; font-weight:700; padding:2px 8px; border-radius:4px; white-space:nowrap; }}
  .b-post {{ background:rgba(16,185,129,.15); color:var(--emerald); }}
  .b-reason {{ background:rgba(245,158,11,.15); color:var(--amber); }}
  .b-danger {{ background:rgba(239,68,68,.15); color:var(--red); }}
  .card-body {{ padding:1rem 1.3rem; font-size:13px; color:var(--text2); }}
  .endpoint {{ font-family:var(--mono); font-size:12px; color:var(--text3); margin-bottom:.6rem; }}
  .endpoint code {{ color:var(--sky); }}
  .also {{ margin-top:1.5rem; }}
  .also-title {{ font-size:12px; font-weight:700; color:var(--text3); text-transform:uppercase; letter-spacing:.08em;
    margin-bottom:.7rem; }}
  .mini-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:.8rem 1.1rem;
    margin-bottom:.6rem; font-size:12.5px; color:var(--text2); }}
  .mini-card b {{ color:var(--text); }}
  .mini-card code {{ font-family:var(--mono); color:var(--text3); font-size:11px; }}
  code {{ font-family:var(--mono); font-size:.92em; }}
  .cat-meta {{ font-size:12px; color:var(--text3); margin-bottom:1rem; }}
  .cat-search {{ width:100%; background:var(--bg2); border:1px solid var(--border); color:var(--text);
    padding:.5rem .8rem; border-radius:6px; font-size:13px; font-family:inherit; margin-bottom:1rem; }}
  .cat-group {{ margin-bottom:1.3rem; }}
  .cat-group-title {{ font-size:12.5px; font-weight:700; color:var(--text2); margin-bottom:.4rem; }}
  .cat-group-title .count {{ color:var(--text3); font-family:var(--mono); font-size:10px; font-weight:400; }}
  .cat-row {{ display:flex; align-items:center; gap:.7rem; padding:.4rem .7rem; border-radius:6px; font-size:12.5px; }}
  .cat-row:hover {{ background:var(--bg2); }}
  .method-badge {{ font-family:var(--mono); font-size:10px; font-weight:700; padding:1px 7px; border-radius:4px;
    color:#fff; min-width:46px; text-align:center; flex-shrink:0; }}
  .m-GET {{ background:var(--get); }} .m-POST {{ background:var(--post); }} .m-PATCH {{ background:var(--patch); }}
  .m-PUT {{ background:var(--put); }} .m-DELETE {{ background:var(--red); }}
  .cat-path {{ font-family:var(--mono); font-size:12px; color:var(--text2); flex-shrink:0; }}
  .cat-summary {{ color:var(--text3); font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .empty-note {{ color:var(--text3); font-size:12px; }}
  .footer-note {{ margin-top:3rem; padding-top:1.5rem; border-top:1px solid var(--border); color:var(--text3); font-size:12px; }}
  .hidden {{ display:none !important; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="brand">PRANA · ADMIN MANUAL</div>
  <h1>Admin Manual</h1>
  <p class="subtitle">
    Role-by-role reference for every admin-gated action in the platform ({total_role_gated} endpoints across
    6 roles), not just account housekeeping. The "Housekeeping" section per role is hand-curated with gotchas
    and irreversibility notes; the "Full endpoint catalogue" below it is auto-generated straight from the live
    OpenAPI schema and role reflection, so it never drifts from the code. Every action here (with the exception
    of read-only dashboard/list endpoints) is fully audited: it publishes a Kafka event, <code>AuditConsumer</code>
    writes an <code>audit_event</code> row and dual-writes it to Immudb, and CISOs can see it in the OA Activity
    Audit screen. Regenerate with <code>python scripts/rebuild_admin_manual_html.py</code> after any router change.
  </p>

  <div class="tabs">
{tabs_html}
  </div>
{"".join(panels_html)}
{FOOTER}
</div>

<script>
function switchTab(name) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + name));
}}
function filterCatalogue(input, key) {{
  const q = input.value.toLowerCase();
  const root = document.getElementById('cat-' + key);
  root.querySelectorAll('.cat-row').forEach(row => {{
    const match = !q || row.dataset.path.includes(q) || row.dataset.summary.includes(q);
    row.classList.toggle('hidden', !match);
  }});
  root.querySelectorAll('.cat-group').forEach(g => {{
    const anyVisible = [...g.querySelectorAll('.cat-row')].some(r => !r.classList.contains('hidden'));
    g.classList.toggle('hidden', !anyVisible);
  }});
}}
</script>
</body>
</html>"""
    return html


if __name__ == "__main__":
    DEST.write_text(render(), encoding="utf-8")
    print(f"Written: {DEST}")
