import re

with open('PRANA_CXO_Deck_v11.html', 'r', encoding='ascii') as f:
    text = f.read()

annexure_slides = r"""
<!-- ANNEX A — Employee Vault -->
<div class="slide" style="background:#f8fafc;">
  <div class="hdr" style="background:linear-gradient(90deg,#0f172a,#1e3a8a);border-bottom:none;">
    <div class="hdr-tag" style="color:#94a3b8;font-size:10px;letter-spacing:0.12em">ANNEXURE A</div>
    <div style="font-size:13px;font-weight:800;color:#fff;margin-left:10px">Employee Vault &mdash; Web &amp; Mobile</div>
    <div class="hdr-num" style="color:#475569">A / 3</div>
  </div>
  <div class="body" style="flex-direction:column;gap:0;padding:18px 32px 14px;">
    <div style="font-size:10px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:#94a3b8;margin-bottom:12px">What the employee sees &mdash; one permanent URL, every employer, every document</div>
    <div style="display:flex;gap:16px;flex:1;min-height:0">

      <!-- SCREEN 1: Vault URL card + doc list -->
      <div style="flex:1.15;background:#fff;border-radius:14px;border:1.5px solid #e2e8f0;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 2px 12px rgba(0,0,0,0.06)">
        <div style="background:#f1f5f9;padding:7px 12px;display:flex;align-items:center;gap:6px;border-bottom:1px solid #e2e8f0">
          <div style="width:8px;height:8px;border-radius:50%;background:#ef4444"></div>
          <div style="width:8px;height:8px;border-radius:50%;background:#f59e0b"></div>
          <div style="width:8px;height:8px;border-radius:50%;background:#10b981"></div>
          <div style="flex:1;background:#fff;border-radius:4px;padding:3px 8px;font-size:10px;color:#64748b;margin-left:8px;border:1px solid #e2e8f0">prana.in/vault/meera.iyer</div>
        </div>
        <div style="margin:10px;border-radius:10px;padding:10px 12px;background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 60%,#0c4a6e 100%)">
          <div style="font-size:8px;font-weight:800;letter-spacing:0.15em;color:#38bdf8;margin-bottom:4px">YOUR PERMANENT VAULT URL</div>
          <div style="font-size:12px;font-weight:700;color:#fff;font-family:monospace">prana.in/vault/meera.iyer</div>
          <div style="font-size:9px;color:#94a3b8;margin-top:3px;font-family:monospace">Active since Apr 2019 &middot; 3 linked employers &middot; 14 documents</div>
        </div>
        <div style="display:flex;gap:6px;margin:0 10px 8px;">
          <div style="flex:1;background:#fff;border:1.5px solid #e2e8f0;border-radius:8px;padding:6px 8px;text-align:center">
            <div style="font-size:16px;font-weight:900;color:#0ea5e9">14</div>
            <div style="font-size:8.5px;color:#64748b;margin-top:1px">Total Docs</div>
          </div>
          <div style="flex:1;background:#fff;border:1.5px solid #e2e8f0;border-radius:8px;padding:6px 8px;text-align:center">
            <div style="font-size:16px;font-weight:900;color:#10b981">2</div>
            <div style="font-size:8.5px;color:#64748b;margin-top:1px">Active Shares</div>
          </div>
          <div style="flex:1;background:#fff;border:1.5px solid #e2e8f0;border-radius:8px;padding:6px 8px;text-align:center">
            <div style="font-size:16px;font-weight:900;color:#f59e0b">3</div>
            <div style="font-size:8.5px;color:#64748b;margin-top:1px">Employers</div>
          </div>
          <div style="flex:1;background:#fff;border:1.5px solid #e2e8f0;border-radius:8px;padding:6px 8px;text-align:center">
            <div style="font-size:16px;font-weight:900;color:#8b5cf6">1</div>
            <div style="font-size:8.5px;color:#64748b;margin-top:1px">Self Upload</div>
          </div>
        </div>
        <div style="display:flex;gap:5px;margin:0 10px 8px;flex-wrap:wrap">
          <span style="background:#0ea5e9;color:#fff;border:1px solid #0ea5e9;border-radius:20px;padding:2px 8px;font-size:8.5px;font-weight:700">All</span>
          <span style="background:#fff;color:#475569;border:1px solid #e2e8f0;border-radius:20px;padding:2px 8px;font-size:8.5px;font-weight:600">TechSol</span>
          <span style="background:#fff;color:#475569;border:1px solid #e2e8f0;border-radius:20px;padding:2px 8px;font-size:8.5px;font-weight:600">FinServ</span>
          <span style="background:#fff;color:#475569;border:1px solid #e2e8f0;border-radius:20px;padding:2px 8px;font-size:8.5px;font-weight:600">CurrentCo</span>
          <span style="background:#fff;color:#475569;border:1px solid #e2e8f0;border-radius:20px;padding:2px 8px;font-size:8.5px;font-weight:600">Salary Slips</span>
          <span style="background:#fff;color:#475569;border:1px solid #e2e8f0;border-radius:20px;padding:2px 8px;font-size:8.5px;font-weight:600">Tax Docs</span>
        </div>
        <div style="margin:0 10px;border:1.5px solid #e2e8f0;border-radius:8px;overflow:hidden">
          <div style="background:rgba(14,165,233,0.07);border-bottom:1px solid rgba(14,165,233,0.18);padding:5px 10px;display:flex;align-items:center;gap:6px">
            <div style="width:7px;height:7px;border-radius:50%;background:#0ea5e9"></div>
            <span style="font-size:10px;font-weight:700;color:#0f172a">CurrentCo Pvt Ltd</span>
            <span style="font-size:8px;color:#94a3b8">Jan 2023 &ndash; Present</span>
            <span style="font-size:8px;font-weight:700;background:rgba(16,185,129,0.1);color:#059669;border:1px solid rgba(16,185,129,0.3);border-radius:4px;padding:1px 5px;margin-left:2px">Active</span>
            <span style="margin-left:auto;font-size:8.5px;color:#94a3b8">5 documents</span>
          </div>
          <div style="padding:5px 10px;display:flex;align-items:center;gap:7px;border-bottom:1px solid #f1f5f9">
            <div style="width:26px;height:26px;border-radius:6px;background:rgba(14,165,233,0.08);display:flex;align-items:center;justify-content:center;font-size:12px">&#128209;</div>
            <div style="flex:1"><div style="font-size:10px;font-weight:600;color:#0f172a">SALARY SLIP <span style="color:#94a3b8;font-weight:400">&middot; Apr 2025</span></div><div style="font-size:8px;color:#94a3b8;font-family:monospace">salary_slip_apr2025.pdf &middot; pushed 01 May 2025</div></div>
            <span style="font-size:8px;font-weight:700;background:rgba(16,185,129,0.08);color:#059669;border:1px solid rgba(16,185,129,0.25);border-radius:4px;padding:1px 5px">&#10003; Verified</span>
          </div>
          <div style="padding:5px 10px;display:flex;align-items:center;gap:7px;border-bottom:1px solid #f1f5f9">
            <div style="width:26px;height:26px;border-radius:6px;background:rgba(14,165,233,0.08);display:flex;align-items:center;justify-content:center;font-size:12px">&#129534;</div>
            <div style="flex:1"><div style="font-size:10px;font-weight:600;color:#0f172a">FORM 16 <span style="color:#94a3b8;font-weight:400">&middot; FY 2024&ndash;25</span></div><div style="font-size:8px;color:#94a3b8;font-family:monospace">form16_fy2425.pdf &middot; pushed 12 Jun 2025</div></div>
            <span style="font-size:8px;font-weight:700;background:rgba(16,185,129,0.08);color:#059669;border:1px solid rgba(16,185,129,0.25);border-radius:4px;padding:1px 5px">&#10003; Verified</span>
          </div>
          <div style="padding:5px 10px;display:flex;align-items:center;gap:7px">
            <div style="width:26px;height:26px;border-radius:6px;background:rgba(14,165,233,0.08);display:flex;align-items:center;justify-content:center;font-size:12px">&#128195;</div>
            <div style="flex:1"><div style="font-size:10px;font-weight:600;color:#0f172a">OFFER LETTER <span style="color:#94a3b4;font-weight:400">&middot; 2023</span></div><div style="font-size:8px;color:#94a3b8;font-family:monospace">offer_letter_jan2023.pdf &middot; pushed 15 Jan 2023</div></div>
            <span style="font-size:8px;font-weight:700;background:rgba(16,185,129,0.08);color:#059669;border:1px solid rgba(16,185,129,0.25);border-radius:4px;padding:1px 5px">&#10003; Verified</span>
          </div>
        </div>
      </div>

      <!-- SCREEN 2: Career Timeline -->
      <div style="width:220px;background:#fff;border-radius:14px;border:1.5px solid #e2e8f0;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 2px 12px rgba(0,0,0,0.06)">
        <div style="padding:10px 12px 6px;border-bottom:1px solid #f1f5f9">
          <div style="font-size:12px;font-weight:800;color:#0f172a">Career Timeline</div>
          <div style="font-size:9px;color:#64748b;margin-top:1px">6 years 2 months total experience</div>
        </div>
        <div style="padding:10px 12px;flex:1;overflow:hidden">
          <div style="position:relative;padding-left:16px;border-left:2px solid #e2e8f0">
            <div style="margin-bottom:14px">
              <div style="position:absolute;left:-5px;width:8px;height:8px;border-radius:50%;background:#10b981;border:2px solid #fff;box-shadow:0 0 0 2px #10b981"></div>
              <div style="font-size:10px;font-weight:700;color:#0f172a">CurrentCo Pvt Ltd</div>
              <div style="font-size:8.5px;color:#64748b">Senior Analyst &middot; Grade 3B</div>
              <div style="font-size:8px;color:#94a3b8;font-family:monospace">Jan 2023 &ndash; Present &middot; 2y 6m</div>
              <div style="margin-top:4px;display:flex;gap:3px">
                <span style="font-size:7.5px;background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;border-radius:4px;padding:1px 5px">5 docs</span>
                <span style="font-size:7.5px;background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;border-radius:4px;padding:1px 5px">Active</span>
              </div>
            </div>
            <div style="margin-bottom:14px">
              <div style="font-size:10px;font-weight:700;color:#0f172a">FinServ Solutions</div>
              <div style="font-size:8.5px;color:#64748b">Analyst &middot; Grade 2A</div>
              <div style="font-size:8px;color:#94a3b8;font-family:monospace">Mar 2021 &ndash; Dec 2022 &middot; 1y 9m</div>
              <div style="margin-top:4px;display:flex;gap:3px">
                <span style="font-size:7.5px;background:#fffbeb;color:#92400e;border:1px solid #fde68a;border-radius:4px;padding:1px 5px">6 docs</span>
                <span style="font-size:7.5px;background:#f8fafc;color:#475569;border:1px solid #e2e8f0;border-radius:4px;padding:1px 5px">Alumni</span>
              </div>
            </div>
            <div>
              <div style="font-size:10px;font-weight:700;color:#0f172a">TechSol India</div>
              <div style="font-size:8.5px;color:#64748b">Junior Analyst &middot; Grade 1C</div>
              <div style="font-size:8px;color:#94a3b8;font-family:monospace">Apr 2019 &ndash; Feb 2021 &middot; 1y 10m</div>
              <div style="margin-top:4px;display:flex;gap:3px">
                <span style="font-size:7.5px;background:#faf5ff;color:#6d28d9;border:1px solid #ddd6fe;border-radius:4px;padding:1px 5px">3 docs</span>
                <span style="font-size:7.5px;background:#f8fafc;color:#475569;border:1px solid #e2e8f0;border-radius:4px;padding:1px 5px">Alumni</span>
              </div>
            </div>
          </div>
          <div style="margin-top:14px;background:linear-gradient(135deg,#eff6ff,#f0fdf4);border:1px solid #bfdbfe;border-radius:8px;padding:8px 10px">
            <div style="font-size:8px;font-weight:800;letter-spacing:0.08em;color:#1d4ed8;margin-bottom:3px">AI INSIGHT</div>
            <div style="font-size:9.5px;color:#0f172a;line-height:1.4">Career shows consistent progression: Junior &#8594; Analyst &#8594; Senior in 6 years. Grade trajectory aligns with top quartile in your domain.</div>
          </div>
        </div>
      </div>

      <!-- SCREEN 3: Mobile app -->
      <div style="width:158px;background:#fff;border-radius:14px;border:1.5px solid #e2e8f0;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 2px 12px rgba(0,0,0,0.06)">
        <div style="background:#0f172a;padding:10px 12px 8px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <div style="font-size:9px;color:#94a3b8">9:41 AM</div>
          </div>
          <div style="font-size:8px;font-weight:800;letter-spacing:0.1em;color:#38bdf8;margin-bottom:2px">MY VAULT</div>
          <div style="font-size:10px;font-weight:700;color:#fff;font-family:monospace">prana.in/vault/you</div>
          <div style="font-size:7.5px;color:#64748b;margin-top:1px">One URL. Permanent. Yours.</div>
        </div>
        <div style="flex:1;background:#0f1f35;padding:6px">
          <div style="background:rgba(14,165,233,0.12);border:1px solid rgba(14,165,233,0.25);border-radius:6px;padding:6px 8px;margin-bottom:4px;display:flex;align-items:center;gap:5px">
            <span style="font-size:12px">&#128209;</span>
            <div><div style="font-size:8px;font-weight:700;color:#38bdf8">Salary Slip &middot; Apr 2025</div><div style="font-size:7px;color:#64748b">CurrentCo</div></div>
          </div>
          <div style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.22);border-radius:6px;padding:6px 8px;margin-bottom:4px;display:flex;align-items:center;gap:5px">
            <span style="font-size:12px">&#129534;</span>
            <div><div style="font-size:8px;font-weight:700;color:#34d399">Form 16 &middot; FY 2024&ndash;25</div><div style="font-size:7px;color:#64748b">CurrentCo</div></div>
          </div>
          <div style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.22);border-radius:6px;padding:6px 8px;margin-bottom:4px;display:flex;align-items:center;gap:5px">
            <span style="font-size:12px">&#128195;</span>
            <div><div style="font-size:8px;font-weight:700;color:#fbbf24">Offer Letter &middot; 2022</div><div style="font-size:7px;color:#64748b">FinServ Solutions</div></div>
          </div>
          <div style="background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.22);border-radius:6px;padding:6px 8px;display:flex;align-items:center;gap:5px">
            <span style="font-size:12px">&#128188;</span>
            <div><div style="font-size:8px;font-weight:700;color:#a78bfa">Relieving Letter &middot; 2022</div><div style="font-size:7px;color:#64748b">FinServ Solutions</div></div>
          </div>
          <div style="margin-top:8px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.08);display:flex;justify-content:space-around">
            <div style="text-align:center"><div style="font-size:13px">&#127968;</div><div style="font-size:6.5px;color:#38bdf8;font-weight:700">Vault</div></div>
            <div style="text-align:center"><div style="font-size:13px">&#128200;</div><div style="font-size:6.5px;color:#64748b">Career</div></div>
            <div style="text-align:center"><div style="font-size:13px">&#128279;</div><div style="font-size:6.5px;color:#64748b">Share</div></div>
            <div style="text-align:center"><div style="font-size:13px">&#128065;</div><div style="font-size:6.5px;color:#64748b">Activity</div></div>
          </div>
        </div>
      </div>

    </div>
    <div style="margin-top:10px;display:flex;gap:16px">
      <div style="flex:1;text-align:center;font-size:9px;color:#64748b;font-weight:600">&#128274; Vault URL &middot; Stat Cards &middot; Org-grouped Docs &middot; Filter Pills</div>
      <div style="width:220px;text-align:center;font-size:9px;color:#64748b;font-weight:600">&#128200; AI Career Timeline &middot; Insight Card</div>
      <div style="width:158px;text-align:center;font-size:9px;color:#64748b;font-weight:600">&#128241; Mobile App (Expo SDK 56)</div>
    </div>
  </div>
</div>

<!-- ANNEX B — Employer Portal -->
<div class="slide" style="background:#f8fafc;">
  <div class="hdr" style="background:linear-gradient(90deg,#0f172a,#1e3a8a);border-bottom:none;">
    <div class="hdr-tag" style="color:#94a3b8;font-size:10px;letter-spacing:0.12em">ANNEXURE B</div>
    <div style="font-size:13px;font-weight:800;color:#fff;margin-left:10px">Employer Portal &mdash; OA Dashboard &middot; CHRO &middot; CISO</div>
    <div class="hdr-num" style="color:#475569">B / 3</div>
  </div>
  <div class="body" style="flex-direction:column;gap:0;padding:18px 32px 14px;">
    <div style="font-size:10px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:#94a3b8;margin-bottom:12px">What the employer sees &mdash; document operations, workforce analytics, security posture</div>
    <div style="display:flex;gap:14px;flex:1;min-height:0">

      <!-- OA Dashboard -->
      <div style="flex:1;background:#fff;border-radius:14px;border:1.5px solid #e2e8f0;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 2px 12px rgba(0,0,0,0.06)">
        <div style="background:#f8fafc;border-bottom:1px solid #e2e8f0;padding:7px 12px;display:flex;align-items:center;gap:6px">
          <div style="font-size:11px;font-weight:800;color:#0f172a">Dashboard</div>
          <div style="font-size:9px;color:#64748b;margin-left:2px">Acme Corp &middot; OA-Admin</div>
          <div style="margin-left:auto;background:#10b981;color:#fff;font-size:8px;font-weight:700;border-radius:4px;padding:2px 6px">LIVE</div>
        </div>
        <div style="padding:10px">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:8px">
            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:8px;padding:7px 9px">
              <div style="font-size:18px;font-weight:900;color:#6366f1">1,247</div>
              <div style="font-size:8.5px;font-weight:600;color:#334155;margin-top:1px">Total Documents</div>
              <div style="font-size:7.5px;color:#94a3b8">this month: +143</div>
            </div>
            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:8px;padding:7px 9px">
              <div style="font-size:18px;font-weight:900;color:#f59e0b">3</div>
              <div style="font-size:8.5px;font-weight:600;color:#334155;margin-top:1px">Exception Queue</div>
              <div style="font-size:7.5px;color:#ef4444">2 past SLA (4h)</div>
            </div>
            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:8px;padding:7px 9px">
              <div style="font-size:18px;font-weight:900;color:#10b981">98.4%</div>
              <div style="font-size:8.5px;font-weight:600;color:#334155;margin-top:1px">Pipeline Success</div>
              <div style="font-size:7.5px;color:#94a3b8">last 7 days</div>
            </div>
            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:8px;padding:7px 9px">
              <div style="font-size:18px;font-weight:900;color:#0ea5e9">486</div>
              <div style="font-size:8.5px;font-weight:600;color:#334155;margin-top:1px">Active Employees</div>
              <div style="font-size:7.5px;color:#94a3b8">12 alumni</div>
            </div>
          </div>
          <div style="font-size:9px;font-weight:700;color:#0f172a;margin-bottom:5px">&#9888; Exception Queue</div>
          <div style="border:1.5px solid #fef3c7;border-radius:7px;overflow:hidden;margin-bottom:8px">
            <div style="padding:5px 8px;display:flex;align-items:center;gap:6px;background:#fffbeb;border-bottom:1px solid #fef3c7">
              <div style="width:6px;height:6px;border-radius:50%;background:#f59e0b;flex-shrink:0"></div>
              <div style="flex:1;font-size:9px;color:#0f172a">SALARY_SLIP &middot; Rajesh Kumar <span style="color:#94a3b8">&middot; Unresolved 6h</span></div>
              <span style="font-size:7.5px;background:#fef3c7;color:#92400e;border:1px solid #fde68a;border-radius:4px;padding:1px 5px">PAST SLA</span>
            </div>
            <div style="padding:5px 8px;display:flex;align-items:center;gap:6px;background:#fff">
              <div style="width:6px;height:6px;border-radius:50%;background:#ef4444;flex-shrink:0"></div>
              <div style="flex:1;font-size:9px;color:#0f172a">FORM_16 &middot; Priya Singh <span style="color:#94a3b8">&middot; Unresolved 9h</span></div>
              <span style="font-size:7.5px;background:#fef2f2;color:#991b1b;border:1px solid #fecaca;border-radius:4px;padding:1px 5px">PAST SLA</span>
            </div>
          </div>
          <div style="background:linear-gradient(90deg,#4f46e5,#6366f1);border-radius:7px;padding:8px 10px;display:flex;align-items:center;gap:8px">
            <span style="font-size:16px">&#128228;</span>
            <div>
              <div style="font-size:9.5px;font-weight:700;color:#fff">Upload Documents</div>
              <div style="font-size:8px;color:rgba(255,255,255,0.7)">Single PDF or batch CSV+ZIP</div>
            </div>
            <div style="margin-left:auto;background:rgba(255,255,255,0.2);border-radius:5px;padding:3px 8px;font-size:8px;color:#fff;font-weight:600">Upload &#8594;</div>
          </div>
        </div>
      </div>

      <!-- CHRO Dashboard -->
      <div style="flex:1;background:#fff;border-radius:14px;border:1.5px solid #e2e8f0;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 2px 12px rgba(0,0,0,0.06)">
        <div style="background:#f8fafc;border-bottom:1px solid #e2e8f0;padding:7px 12px;display:flex;align-items:center;">
          <div style="font-size:11px;font-weight:800;color:#0f172a">CHRO Dashboard</div>
          <div style="font-size:9px;color:#64748b;margin-left:6px">Workforce &amp; Compliance</div>
        </div>
        <div style="padding:10px;flex:1">
          <div style="font-size:9px;font-weight:700;color:#0f172a;margin-bottom:6px">Vault Completeness by Department</div>
          <div style="display:flex;flex-direction:column;gap:4px;margin-bottom:9px">
            <div style="display:flex;align-items:center;gap:6px">
              <div style="font-size:8.5px;color:#334155;width:72px;flex-shrink:0">Engineering</div>
              <div style="flex:1;height:7px;background:#e2e8f0;border-radius:100px;overflow:hidden"><div style="width:94%;height:100%;background:linear-gradient(90deg,#10b981,#34d399);border-radius:100px"></div></div>
              <div style="font-size:8.5px;font-weight:700;color:#059669;width:28px;text-align:right">94%</div>
            </div>
            <div style="display:flex;align-items:center;gap:6px">
              <div style="font-size:8.5px;color:#334155;width:72px;flex-shrink:0">Finance</div>
              <div style="flex:1;height:7px;background:#e2e8f0;border-radius:100px;overflow:hidden"><div style="width:88%;height:100%;background:linear-gradient(90deg,#10b981,#34d399);border-radius:100px"></div></div>
              <div style="font-size:8.5px;font-weight:700;color:#059669;width:28px;text-align:right">88%</div>
            </div>
            <div style="display:flex;align-items:center;gap:6px">
              <div style="font-size:8.5px;color:#334155;width:72px;flex-shrink:0">Operations</div>
              <div style="flex:1;height:7px;background:#e2e8f0;border-radius:100px;overflow:hidden"><div style="width:76%;height:100%;background:linear-gradient(90deg,#f59e0b,#fbbf24);border-radius:100px"></div></div>
              <div style="font-size:8.5px;font-weight:700;color:#d97706;width:28px;text-align:right">76%</div>
            </div>
            <div style="display:flex;align-items:center;gap:6px">
              <div style="font-size:8.5px;color:#334155;width:72px;flex-shrink:0">Sales</div>
              <div style="flex:1;height:7px;background:#e2e8f0;border-radius:100px;overflow:hidden"><div style="width:61%;height:100%;background:linear-gradient(90deg,#ef4444,#f87171);border-radius:100px"></div></div>
              <div style="font-size:8.5px;font-weight:700;color:#dc2626;width:28px;text-align:right">61%</div>
            </div>
          </div>
          <div style="font-size:9px;font-weight:700;color:#0f172a;margin-bottom:5px">Statutory Compliance</div>
          <div style="display:flex;flex-direction:column;gap:3px;margin-bottom:8px">
            <div style="display:flex;align-items:center;justify-content:space-between;padding:4px 7px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px">
              <span style="font-size:8.5px;color:#0f172a">PF Monthly Filing</span>
              <span style="font-size:8px;font-weight:700;color:#059669">&#10003; Filed on time</span>
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;padding:4px 7px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px">
              <span style="font-size:8.5px;color:#0f172a">Form 16 (TDS)</span>
              <span style="font-size:8px;font-weight:700;color:#059669">&#10003; 486 / 486 issued</span>
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;padding:4px 7px;background:#fffbeb;border:1px solid #fde68a;border-radius:6px">
              <span style="font-size:8.5px;color:#0f172a">ESIC Filing</span>
              <span style="font-size:8px;font-weight:700;color:#d97706">&#9888; Due in 3 days</span>
            </div>
          </div>
          <div style="background:linear-gradient(135deg,#eff6ff,#f5f3ff);border:1px solid #c7d2fe;border-radius:7px;padding:7px 9px">
            <div style="font-size:8px;font-weight:800;letter-spacing:0.08em;color:#4f46e5;margin-bottom:3px">WEEKLY DIGEST &middot; W24 2026</div>
            <div style="font-size:9px;color:#0f172a;line-height:1.5">143 documents pushed &middot; 0 exceptions pending &middot; Compliance score <strong>96/100</strong></div>
          </div>
        </div>
      </div>

      <!-- CISO Security Dashboard -->
      <div style="flex:1;background:#fff;border-radius:14px;border:1.5px solid #e2e8f0;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 2px 12px rgba(0,0,0,0.06)">
        <div style="background:#0f172a;border-bottom:1px solid #1e293b;padding:7px 12px;display:flex;align-items:center;gap:6px">
          <div style="font-size:11px;font-weight:800;color:#fff">CISO Security</div>
          <div style="font-size:9px;color:#64748b;margin-left:2px">Tenant CISO View</div>
          <div style="margin-left:auto;background:rgba(16,185,129,0.2);color:#34d399;font-size:8px;font-weight:700;border-radius:4px;padding:2px 6px">ALL SYSTEMS GREEN</div>
        </div>
        <div style="padding:10px;flex:1;background:#0f172a">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:8px">
            <div style="background:#1e293b;border:1px solid #334155;border-radius:7px;padding:6px 8px">
              <div style="font-size:15px;font-weight:900;color:#10b981">0</div>
              <div style="font-size:8px;color:#94a3b8;margin-top:1px">Active Threats</div>
            </div>
            <div style="background:#1e293b;border:1px solid #334155;border-radius:7px;padding:6px 8px">
              <div style="font-size:15px;font-weight:900;color:#f59e0b">2</div>
              <div style="font-size:8px;color:#94a3b8;margin-top:1px">Flagged Access</div>
            </div>
            <div style="background:#1e293b;border:1px solid #334155;border-radius:7px;padding:6px 8px">
              <div style="font-size:15px;font-weight:900;color:#38bdf8">1,892</div>
              <div style="font-size:8px;color:#94a3b8;margin-top:1px">Logins (7d)</div>
            </div>
            <div style="background:#1e293b;border:1px solid #334155;border-radius:7px;padding:6px 8px">
              <div style="font-size:15px;font-weight:900;color:#a78bfa">0</div>
              <div style="font-size:8px;color:#94a3b8;margin-top:1px">Open Locks</div>
            </div>
          </div>
          <div style="font-size:8.5px;font-weight:700;color:#94a3b8;letter-spacing:0.08em;margin-bottom:4px">RECENT LOGIN ACTIVITY</div>
          <div style="display:flex;flex-direction:column;gap:3px;margin-bottom:7px">
            <div style="background:#1e293b;border-radius:5px;padding:4px 7px;display:flex;align-items:center;gap:5px">
              <div style="width:5px;height:5px;border-radius:50%;background:#10b981;flex-shrink:0"></div>
              <div style="font-size:8px;color:#e2e8f0;flex:1">priya.singh@acme.com</div>
              <div style="font-size:7.5px;color:#64748b">Mumbai &middot; 2m ago</div>
            </div>
            <div style="background:#1e293b;border-radius:5px;padding:4px 7px;display:flex;align-items:center;gap:5px">
              <div style="width:5px;height:5px;border-radius:50%;background:#10b981;flex-shrink:0"></div>
              <div style="font-size:8px;color:#e2e8f0;flex:1">rajesh.k@acme.com</div>
              <div style="font-size:7.5px;color:#64748b">Pune &middot; 18m ago</div>
            </div>
            <div style="background:#2d1b1b;border:1px solid rgba(239,68,68,0.3);border-radius:5px;padding:4px 7px;display:flex;align-items:center;gap:5px">
              <div style="width:5px;height:5px;border-radius:50%;background:#ef4444;flex-shrink:0"></div>
              <div style="font-size:8px;color:#fca5a5;flex:1">anon@unknown.ip</div>
              <div style="font-size:7.5px;color:#ef4444;font-weight:600">&#9888; Flagged</div>
            </div>
          </div>
          <div style="background:#1e293b;border:1px solid #334155;border-radius:6px;padding:7px 9px">
            <div style="font-size:8px;font-weight:700;color:#38bdf8;margin-bottom:4px">&#128272; ENCRYPTION KEY HEALTH</div>
            <div style="display:flex;flex-direction:column;gap:2.5px">
              <div style="display:flex;justify-content:space-between;font-size:8px"><span style="color:#94a3b8">Tenant KEK (KMS)</span><span style="color:#10b981;font-weight:600">&#10003; Active</span></div>
              <div style="display:flex;justify-content:space-between;font-size:8px"><span style="color:#94a3b8">Platform Secret</span><span style="color:#10b981;font-weight:600">&#10003; Active</span></div>
              <div style="display:flex;justify-content:space-between;font-size:8px"><span style="color:#94a3b8">DEK rotation</span><span style="color:#10b981;font-weight:600">0 expired</span></div>
            </div>
          </div>
        </div>
      </div>

    </div>
    <div style="margin-top:10px;display:flex;gap:14px">
      <div style="flex:1;text-align:center;font-size:9px;color:#64748b;font-weight:600">&#128228; OA Dashboard &middot; Upload &middot; Exception Queue</div>
      <div style="flex:1;text-align:center;font-size:9px;color:#64748b;font-weight:600">&#128202; CHRO &middot; Vault Completeness &middot; Statutory &middot; Digest</div>
      <div style="flex:1;text-align:center;font-size:9px;color:#64748b;font-weight:600">&#128737; CISO &middot; Login Feed &middot; Flagged Access &middot; Key Health</div>
    </div>
  </div>
</div>

<!-- ANNEX C — CFO + Digest -->
<div class="slide" style="background:#f8fafc;">
  <div class="hdr" style="background:linear-gradient(90deg,#0f172a,#1e3a8a);border-bottom:none;">
    <div class="hdr-tag" style="color:#94a3b8;font-size:10px;letter-spacing:0.12em">ANNEXURE C</div>
    <div style="font-size:13px;font-weight:800;color:#fff;margin-left:10px">CFO Analytics &middot; Automated Digest Previews</div>
    <div class="hdr-num" style="color:#475569">C / 3</div>
  </div>
  <div class="body" style="flex-direction:column;gap:0;padding:18px 32px 14px;">
    <div style="font-size:10px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:#94a3b8;margin-bottom:12px">Scheduled intelligence delivered to every CXO &mdash; zero manual effort</div>
    <div style="display:flex;gap:14px;flex:1;min-height:0">

      <!-- CFO Dashboard -->
      <div style="flex:1.1;background:#fff;border-radius:14px;border:1.5px solid #e2e8f0;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 2px 12px rgba(0,0,0,0.06)">
        <div style="background:#f8fafc;border-bottom:1px solid #e2e8f0;padding:7px 12px;display:flex;align-items:center;gap:6px">
          <div style="font-size:11px;font-weight:800;color:#0f172a">CFO Analytics</div>
          <div style="font-size:9px;color:#64748b">Compensation Intelligence</div>
        </div>
        <div style="padding:10px;flex:1">
          <div style="font-size:9px;font-weight:700;color:#0f172a;margin-bottom:6px">Payroll Intelligence &mdash; Grade Band Distribution</div>
          <div style="display:flex;flex-direction:column;gap:4px;margin-bottom:9px">
            <div style="display:flex;align-items:center;gap:6px">
              <div style="font-size:8.5px;color:#334155;width:50px;flex-shrink:0">Grade 4+</div>
              <div style="flex:1;height:8px;background:#e2e8f0;border-radius:100px;overflow:hidden"><div style="width:22%;height:100%;background:linear-gradient(90deg,#8b5cf6,#a78bfa);border-radius:100px"></div></div>
              <div style="font-size:8px;color:#64748b;width:60px;text-align:right">22 employees</div>
            </div>
            <div style="display:flex;align-items:center;gap:6px">
              <div style="font-size:8.5px;color:#334155;width:50px;flex-shrink:0">Grade 3</div>
              <div style="flex:1;height:8px;background:#e2e8f0;border-radius:100px;overflow:hidden"><div style="width:38%;height:100%;background:linear-gradient(90deg,#6366f1,#818cf8);border-radius:100px"></div></div>
              <div style="font-size:8px;color:#64748b;width:60px;text-align:right">184 employees</div>
            </div>
            <div style="display:flex;align-items:center;gap:6px">
              <div style="font-size:8.5px;color:#334155;width:50px;flex-shrink:0">Grade 2</div>
              <div style="flex:1;height:8px;background:#e2e8f0;border-radius:100px;overflow:hidden"><div style="width:52%;height:100%;background:linear-gradient(90deg,#0ea5e9,#38bdf8);border-radius:100px"></div></div>
              <div style="font-size:8px;color:#64748b;width:60px;text-align:right">252 employees</div>
            </div>
            <div style="display:flex;align-items:center;gap:6px">
              <div style="font-size:8.5px;color:#334155;width:50px;flex-shrink:0">Grade 1</div>
              <div style="flex:1;height:8px;background:#e2e8f0;border-radius:100px;overflow:hidden"><div style="width:16%;height:100%;background:linear-gradient(90deg,#10b981,#34d399);border-radius:100px"></div></div>
              <div style="font-size:8px;color:#64748b;width:60px;text-align:right">28 employees</div>
            </div>
          </div>
          <div style="font-size:9px;font-weight:700;color:#0f172a;margin-bottom:5px">&#9888; Anomaly Acknowledgement Queue</div>
          <div style="display:flex;flex-direction:column;gap:3px;margin-bottom:8px">
            <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:5px 8px;display:flex;align-items:center;gap:6px">
              <div style="width:6px;height:6px;border-radius:50%;background:#ef4444;flex-shrink:0"></div>
              <div style="flex:1;font-size:8.5px;color:#0f172a">Grade mismatch &middot; 3 employees &middot; Role vs. band</div>
              <span style="font-size:7.5px;background:#fef2f2;color:#991b1b;border:1px solid #fecaca;border-radius:4px;padding:1px 5px;flex-shrink:0">Acknowledge</span>
            </div>
            <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:6px;padding:5px 8px;display:flex;align-items:center;gap:6px">
              <div style="width:6px;height:6px;border-radius:50%;background:#f59e0b;flex-shrink:0"></div>
              <div style="flex:1;font-size:8.5px;color:#0f172a">Attrition spike &middot; Sales dept &middot; 4 exits this month</div>
              <span style="font-size:7.5px;background:#fffbeb;color:#92400e;border:1px solid #fde68a;border-radius:4px;padding:1px 5px;flex-shrink:0">Review</span>
            </div>
          </div>
          <div style="background:linear-gradient(135deg,#f5f3ff,#eff6ff);border:1px solid #ddd6fe;border-radius:7px;padding:7px 9px">
            <div style="font-size:8px;font-weight:800;letter-spacing:0.08em;color:#7c3aed;margin-bottom:3px">AI PAYROLL INSIGHT</div>
            <div style="font-size:9px;color:#0f172a;line-height:1.5">Salary benchmarking shows 14% of Grade-2 band is above market median. No raw figures stored &mdash; insight only.</div>
          </div>
        </div>
      </div>

      <!-- Digest cards -->
      <div style="flex:1;display:flex;flex-direction:column;gap:10px">
        <div style="background:#fff;border-radius:14px;border:1.5px solid #e2e8f0;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.06);flex:1">
          <div style="background:linear-gradient(90deg,#1d4ed8,#2563eb);padding:8px 12px;display:flex;align-items:center;gap:6px">
            <span style="font-size:13px">&#128202;</span>
            <div style="font-size:10px;font-weight:800;color:#fff">CHRO Weekly Digest &mdash; W24 2026</div>
          </div>
          <div style="padding:9px 12px">
            <div style="display:flex;gap:6px;margin-bottom:7px">
              <div style="flex:1;text-align:center;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:7px;padding:5px 4px">
                <div style="font-size:16px;font-weight:900;color:#059669">143</div>
                <div style="font-size:7.5px;color:#64748b">Docs Pushed</div>
              </div>
              <div style="flex:1;text-align:center;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:7px;padding:5px 4px">
                <div style="font-size:16px;font-weight:900;color:#059669">0</div>
                <div style="font-size:7.5px;color:#64748b">Exceptions</div>
              </div>
              <div style="flex:1;text-align:center;background:#eff6ff;border:1px solid #bfdbfe;border-radius:7px;padding:5px 4px">
                <div style="font-size:16px;font-weight:900;color:#1d4ed8">96</div>
                <div style="font-size:7.5px;color:#64748b">Score /100</div>
              </div>
            </div>
            <div style="font-size:8px;font-weight:700;color:#334155;margin-bottom:3px">Vault completeness alerts</div>
            <div style="display:flex;flex-direction:column;gap:2px">
              <div style="display:flex;align-items:center;gap:5px;font-size:8px;color:#0f172a"><span style="color:#f59e0b">&#9888;</span> Sales dept below 65% &mdash; 18 employees missing salary slips</div>
              <div style="display:flex;align-items:center;gap:5px;font-size:8px;color:#0f172a"><span style="color:#10b981">&#10003;</span> Engineering at 94% &mdash; on track</div>
            </div>
          </div>
        </div>
        <div style="background:#0f172a;border-radius:14px;border:1.5px solid #1e293b;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.06);flex:1">
          <div style="background:linear-gradient(90deg,#dc2626,#ef4444);padding:8px 12px;display:flex;align-items:center;gap:6px">
            <span style="font-size:13px">&#128737;</span>
            <div style="font-size:10px;font-weight:800;color:#fff">CISO Security Digest &mdash; W24 2026</div>
          </div>
          <div style="padding:9px 12px">
            <div style="display:flex;gap:6px;margin-bottom:7px">
              <div style="flex:1;text-align:center;background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.25);border-radius:7px;padding:5px 4px">
                <div style="font-size:16px;font-weight:900;color:#10b981">1,892</div>
                <div style="font-size:7.5px;color:#64748b">Total Logins</div>
              </div>
              <div style="flex:1;text-align:center;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.25);border-radius:7px;padding:5px 4px">
                <div style="font-size:16px;font-weight:900;color:#ef4444">2</div>
                <div style="font-size:7.5px;color:#64748b">Flagged</div>
              </div>
              <div style="flex:1;text-align:center;background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.25);border-radius:7px;padding:5px 4px">
                <div style="font-size:16px;font-weight:900;color:#10b981">0</div>
                <div style="font-size:7.5px;color:#64748b">Key Alerts</div>
              </div>
            </div>
            <div style="display:flex;flex-direction:column;gap:2px">
              <div style="display:flex;align-items:center;gap:5px;font-size:8px;color:#e2e8f0"><span style="color:#ef4444">&#9888;</span> 2 flagged access events need CISO review</div>
              <div style="display:flex;align-items:center;gap:5px;font-size:8px;color:#e2e8f0"><span style="color:#10b981">&#10003;</span> All DEKs healthy &middot; 0 rotations due</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Delivery schedule -->
      <div style="width:208px;display:flex;flex-direction:column;gap:10px">
        <div style="background:#fff;border-radius:14px;border:1.5px solid #e2e8f0;padding:14px 14px;box-shadow:0 2px 12px rgba(0,0,0,0.06)">
          <div style="font-size:10px;font-weight:800;color:#0f172a;margin-bottom:10px">Digest Delivery Schedule</div>
          <div style="display:flex;flex-direction:column;gap:7px">
            <div style="display:flex;gap:8px;align-items:flex-start">
              <div style="width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,#1d4ed8,#2563eb);display:flex;align-items:center;justify-content:center;font-size:12px;flex-shrink:0">&#128202;</div>
              <div><div style="font-size:9.5px;font-weight:700;color:#0f172a">CHRO Digest</div><div style="font-size:8px;color:#64748b">Weekly Mon 8AM &middot; Monthly 1st</div><div style="font-size:8px;color:#10b981;font-weight:600">&#10003; Email + Portal</div></div>
            </div>
            <div style="display:flex;gap:8px;align-items:flex-start">
              <div style="width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,#d97706,#f59e0b);display:flex;align-items:center;justify-content:center;font-size:12px;flex-shrink:0">&#128201;</div>
              <div><div style="font-size:9.5px;font-weight:700;color:#0f172a">CFO Digest</div><div style="font-size:8px;color:#64748b">Monthly 1st &middot; On anomaly</div><div style="font-size:8px;color:#10b981;font-weight:600">&#10003; Email + Portal</div></div>
            </div>
            <div style="display:flex;gap:8px;align-items:flex-start">
              <div style="width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,#dc2626,#ef4444);display:flex;align-items:center;justify-content:center;font-size:12px;flex-shrink:0">&#128737;</div>
              <div><div style="font-size:9.5px;font-weight:700;color:#0f172a">CISO Digest</div><div style="font-size:8px;color:#64748b">Weekly Mon 7AM &middot; On alert</div><div style="font-size:8px;color:#10b981;font-weight:600">&#10003; Email + Portal</div></div>
            </div>
          </div>
        </div>
        <div style="background:linear-gradient(135deg,#0f172a,#1e3a8a);border-radius:14px;padding:14px;flex:1">
          <div style="font-size:10px;font-weight:800;color:#fff;margin-bottom:8px">Zero Manual Steps</div>
          <div style="display:flex;flex-direction:column;gap:5px">
            <div style="display:flex;align-items:center;gap:6px;font-size:8.5px;color:#94a3b8"><span style="color:#10b981;font-weight:700">&#10003;</span> Temporal DigestWorkflow scheduled</div>
            <div style="display:flex;align-items:center;gap:6px;font-size:8.5px;color:#94a3b8"><span style="color:#10b981;font-weight:700">&#10003;</span> Kafka NotifConsumer dispatches</div>
            <div style="display:flex;align-items:center;gap:6px;font-size:8.5px;color:#94a3b8"><span style="color:#10b981;font-weight:700">&#10003;</span> AWS SES delivery + portal bell</div>
            <div style="display:flex;align-items:center;gap:6px;font-size:8.5px;color:#94a3b8"><span style="color:#10b981;font-weight:700">&#10003;</span> No raw &#8377; or PAN in any digest</div>
          </div>
        </div>
      </div>

    </div>
    <div style="margin-top:10px;display:flex;gap:14px">
      <div style="flex:1.1;text-align:center;font-size:9px;color:#64748b;font-weight:600">&#128201; CFO &middot; Grade Band Analytics &middot; Anomaly Queue &middot; AI Insights</div>
      <div style="flex:1;text-align:center;font-size:9px;color:#64748b;font-weight:600">&#128202; CHRO Digest &middot; &#128737; CISO Digest &mdash; live previews</div>
      <div style="width:208px;text-align:center;font-size:9px;color:#64748b;font-weight:600">Automated &middot; Temporal + Kafka + SES</div>
    </div>
  </div>
</div>
"""

text = text.replace('</body>', annexure_slides + '\n</body>')

# Encode all non-ASCII
out = []
for c in text:
    cp = ord(c)
    if cp > 127:
        out.append(f'&#{cp};')
    else:
        out.append(c)
final = ''.join(out)

with open('PRANA_CXO_Deck_v12.html', 'w', encoding='ascii') as f:
    f.write(final)

import re
slides = len(re.findall(r'class="slide"', final))
print(f"v12 written. {slides} slides. Size: {len(final)} chars")
print("Annex A:", 'ANNEXURE A' in final)
print("Annex B:", 'ANNEXURE B' in final)
print("Annex C:", 'ANNEXURE C' in final)
