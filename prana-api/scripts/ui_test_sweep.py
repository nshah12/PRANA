"""
PRANA Portal — Full credential sweep
Tests all users across all role-relevant endpoints.
Handles TOTP setup automatically if not yet configured.
"""
import httpx
import pyotp
import re
import json
import sys
from datetime import datetime

BASE = "http://localhost:8000"

USERS = [
    {"email": "chro@techcorp.in",            "password": "DevEmp@123", "role": "chro",        "org": "TechCorp"},
    {"email": "cfo@techcorp.in",             "password": "DevEmp@123", "role": "cfo",         "org": "TechCorp"},
    {"email": "ciso@techcorp.in",            "password": "DevEmp@123", "role": "ciso",        "org": "TechCorp"},
    {"email": "admin@techcorp.in",           "password": "DevEmp@123", "role": "oa_admin",    "org": "TechCorp"},
    {"email": "operator@techcorp.in",        "password": "DevEmp@123", "role": "oa_operator", "org": "TechCorp"},
    {"email": "admin@nexussoftware.in",      "password": "DevEmp@123", "role": "oa_admin",    "org": "NexusSoftware"},
    {"email": "admin@meridiancapital.in",    "password": "DevEmp@123", "role": "oa_admin",    "org": "MeridianCapital"},
    {"email": "admin@zephyranalytics.in",    "password": "DevEmp@123", "role": "oa_admin",    "org": "ZephyrAnalytics"},
    {"email": "admin@pinnacleindia.in",      "password": "DevEmp@123", "role": "oa_admin",    "org": "PinnacleIndia"},
    {"email": "admin@horizonconsulting.in",  "password": "DevEmp@123", "role": "oa_admin",    "org": "HorizonConsulting"},
    {"email": "admin@aurorapharma.in",       "password": "DevEmp@123", "role": "oa_admin",    "org": "AuroraPharma"},
    {"email": "admin@cascaderetail.in",      "password": "DevEmp@123", "role": "oa_admin",    "org": "CascadeRetail"},
]

# Endpoints to test per role: (method, path, label)
ROLE_ENDPOINTS = {
    "chro": [
        ("GET",  "/v1/chro/digest/weekly",          "Weekly digest"),
        ("GET",  "/v1/chro/digest/monthly",         "Monthly digest"),
        ("GET",  "/v1/chro/digest/settings",        "Digest settings"),
        ("GET",  "/v1/chro/vault/health",           "Vault health"),
        ("GET",  "/v1/chro/vault/completeness",     "Vault completeness"),
        ("GET",  "/v1/chro/compliance/posture",     "Compliance posture"),
        ("GET",  "/v1/chro/compliance/calendar",    "Compliance calendar"),
        ("GET",  "/v1/chro/statutory",              "Statutory"),
        ("GET",  "/v1/chro/alerts",                 "Alerts"),
        ("GET",  "/v1/chro/employees/summary",      "Employees summary"),
        ("GET",  "/v1/chro/insights/trend",         "Insights trend"),
        ("GET",  "/v1/chro/insights/exceptions",    "Insights exceptions"),
        ("GET",  "/v1/chro/insights/career",        "Career insights"),
    ],
    "cfo": [
        ("GET",  "/v1/cfo/digest",                  "CFO digest"),
        ("GET",  "/v1/cfo/digest/settings",         "Digest settings"),
        ("GET",  "/v1/cfo/payroll",                 "Payroll intelligence"),
        ("GET",  "/v1/cfo/attrition",               "Attrition cost"),
        ("GET",  "/v1/cfo/benchmarking",            "Benchmarking"),
        ("GET",  "/v1/cfo/anomalies",               "Anomalies"),
        ("GET",  "/v1/cfo/consent/dashboard",       "Consent dashboard"),
        ("GET",  "/v1/cfo/headcount",               "Headcount"),
        ("GET",  "/v1/cfo/exits-joiners",           "Exits & joiners"),
        ("GET",  "/v1/cfo/trends/payroll",          "Payroll trend"),
        ("GET",  "/v1/cfo/trends/headcount",        "Headcount trend"),
        ("GET",  "/v1/cfo/salary-bands",            "Salary bands"),
    ],
    "ciso": [
        ("GET",  "/v1/ciso/digest",                 "InfoSec digest"),
        ("GET",  "/v1/ciso/digest/settings",        "Digest settings"),
        ("GET",  "/v1/ciso/overview",               "Security overview"),
        ("GET",  "/v1/ciso/auth/feed",              "Auth anomaly feed"),
        ("GET",  "/v1/ciso/accounts/locks",         "Account locks"),
        ("GET",  "/v1/ciso/access/flags",           "Access flags"),
        ("GET",  "/v1/ciso/anomalies",              "Anomaly queue"),
        ("GET",  "/v1/ciso/keys/health",            "Key health"),
        ("GET",  "/v1/ciso/shares/analytics",       "Share analytics"),
        ("GET",  "/v1/ciso/sessions",               "Active sessions"),
        ("GET",  "/v1/ciso/audit/trail",            "Audit trail"),
        ("GET",  "/v1/ciso/alerts",                 "Alerts"),
    ],
    "oa_admin": [
        ("GET",  "/v1/org/employees",               "Employee list"),
        ("GET",  "/v1/org/users",                   "OA user list"),
        ("GET",  "/v1/org/elevations",              "Elevation requests"),
        ("GET",  "/v1/org/elevations/active",       "Active elevation"),
        ("GET",  "/v1/org/exceptions",              "Exception queue"),
        ("GET",  "/v1/org/settings",                "Org settings"),
        ("GET",  "/v1/org/profile",                 "Org profile"),
        ("GET",  "/v1/ingest/exceptions",           "Ingest exceptions"),
        ("GET",  "/v1/ingest/health",               "Ingest health"),
        ("GET",  "/v1/vault/compliance/overview",   "Compliance overview"),
        ("GET",  "/v1/vault/compliance/audit-log",  "Audit log"),
    ],
    "oa_operator": [
        ("GET",  "/v1/org/employees",               "Employee list"),
        ("GET",  "/v1/org/elevations",              "Elevation requests"),
        ("GET",  "/v1/org/elevations/active",       "Active elevation"),
        ("GET",  "/v1/org/exceptions",              "Exception queue"),
        ("GET",  "/v1/ingest/exceptions",           "Ingest exceptions"),
        ("GET",  "/v1/ingest/health",               "Ingest health"),
        # These should 403 for operator:
        ("GET",  "/v1/org/users",                   "OA user list [403 expected]"),
        ("GET",  "/v1/org/settings",                "Org settings [403 expected]"),
    ],
}

# Cross-role 403 checks (things a role should NOT be able to access)
CROSS_ROLE_403 = {
    "chro":        ["/v1/cfo/digest", "/v1/ciso/overview", "/v1/org/employees"],
    "cfo":         ["/v1/chro/digest/weekly", "/v1/ciso/overview", "/v1/org/employees"],
    "ciso":        ["/v1/chro/digest/weekly", "/v1/cfo/digest", "/v1/org/employees"],
    "oa_operator": ["/v1/org/users", "/v1/org/settings"],
}

results = {}

def login_and_get_token(user):
    """Full auth flow: password → TOTP setup/verify → JWT"""
    client = httpx.Client(base_url=BASE, timeout=15)

    # Step 1: Password
    r = client.post("/auth/org/login", json={"email": user["email"], "password": user["password"]})
    if r.status_code != 200:
        return None, f"LOGIN_FAILED:{r.status_code}:{r.text[:200]}"

    body = r.json()

    # Handle force_reset
    if body.get("requires_password_reset"):
        step = body["step_token"]
        r2 = client.post("/auth/org/password-reset", json={"step_token": step, "new_password": "DevEmp@123!New"})
        if r2.status_code != 200:
            return None, f"PWD_RESET_FAILED:{r2.status_code}"
        body = r2.json()

    step_token = body.get("step_token")
    if not step_token:
        return None, f"NO_STEP_TOKEN:{json.dumps(body)[:200]}"

    # Step 2a: TOTP setup if not configured
    if body.get("requires_totp_setup"):
        r3 = client.post("/auth/org/totp-setup/init", json={"step_token": step_token})
        if r3.status_code != 200:
            return None, f"TOTP_SETUP_INIT_FAILED:{r3.status_code}:{r3.text[:200]}"
        setup = r3.json()
        uri = setup["provisioning_uri"]
        # Extract secret from URI: otpauth://totp/...?secret=XXX&...
        m = re.search(r'secret=([A-Z2-7]+)', uri, re.IGNORECASE)
        if not m:
            return None, f"TOTP_SECRET_PARSE_FAILED:{uri[:100]}"
        secret = m.group(1).upper()
        code = pyotp.TOTP(secret).now()
        setup_token = setup["setup_token"]
        r4 = client.post("/auth/org/totp-setup/confirm", json={"setup_token": setup_token, "code": code})
        if r4.status_code != 200:
            return None, f"TOTP_SETUP_CONFIRM_FAILED:{r4.status_code}:{r4.text[:200]}"
        return r4.json().get("access_token"), "TOTP_SETUP_OK"

    # Step 2b: TOTP verify (already configured — shouldn't happen in dev seed but handle it)
    # If we get here with requires_totp=true but requires_totp_setup=false, secret is stored encrypted
    # We can't recover secret from DB without DEK, so flag it
    return None, "TOTP_ALREADY_CONFIGURED_NO_SECRET_AVAILABLE"


def call(client, method, path, label):
    try:
        fn = getattr(client, method.lower())
        # Add minimal query params for paginated endpoints
        params = {}
        if "audit-log" in path or "calendar" in path:
            params = {"from": "2024-01-01", "to": "2025-12-31"}
        if "statutory" in path:
            params = {"fy": "2024-25"}
        if "trend" in path or "insights" in path:
            params = {"lookback": "3", "period": "monthly"}
        r = fn(path, params=params, timeout=10)
        body = ""
        try:
            j = r.json()
            # Sample the shape
            if isinstance(j, dict):
                keys = list(j.keys())[:5]
                body = f"keys={keys}"
                if "items" in j:
                    body += f" items={len(j.get('items',[]))}"
                if "error" in j:
                    body += f" error={j['error']}"
            else:
                body = str(j)[:80]
        except:
            body = r.text[:80]
        return r.status_code, body
    except Exception as e:
        return 0, f"EXCEPTION:{str(e)[:100]}"


# ── Main sweep ─────────────────────────────────────────────────────────────────
print(f"\n{'='*80}")
print(f"PRANA PORTAL — FULL CREDENTIAL SWEEP")
print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*80}\n")

summary = []

for user in USERS:
    email = user["email"]
    role  = user["role"]
    org   = user["org"]

    print(f"\n{'─'*70}")
    print(f"USER: {email}  |  ROLE: {role.upper()}  |  ORG: {org}")
    print(f"{'─'*70}")

    token, auth_note = login_and_get_token(user)

    if not token:
        print(f"  AUTH FAILED: {auth_note}")
        summary.append({"email": email, "role": role, "org": org, "auth": "FAILED", "auth_note": auth_note, "endpoints": []})
        continue

    print(f"  AUTH: OK ({auth_note})")
    client = httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {token}"}, timeout=15)

    eps = ROLE_ENDPOINTS.get(role, [])
    ep_results = []
    ok = fail = forbidden = error = 0

    for method, path, label in eps:
        status_code, body = call(client, method, path, label)
        icon = "✓" if status_code in (200, 201, 202) else ("✗" if status_code == 403 else "!")
        print(f"  {icon} {status_code} {method:6} {path:45} {label}")
        if body and status_code not in (200, 201, 202):
            print(f"         ↳ {body}")
        ep_results.append({"method": method, "path": path, "label": label, "status": status_code, "body": body})
        if status_code in (200, 201, 202):
            ok += 1
        elif status_code == 403:
            forbidden += 1
        elif status_code == 0:
            error += 1
        else:
            fail += 1

    # Cross-role 403 checks
    cross = CROSS_ROLE_403.get(role, [])
    if cross:
        print(f"\n  [Access control checks — should all be 403]")
        for path in cross:
            sc, body = call(client, "GET", path, "")
            icon = "✓" if sc == 403 else "✗"
            result = "403 DENIED (correct)" if sc == 403 else f"{sc} (WRONG — should be 403)"
            print(f"  {icon} {path:50} → {result}")
            ep_results.append({"method": "GET", "path": path, "label": "ACCESS_CONTROL", "status": sc, "expected": 403})

    total = len(eps)
    print(f"\n  SUMMARY: {ok}/{total} OK  |  {fail} errors  |  {forbidden} 403s  |  {error} network errors")
    summary.append({"email": email, "role": role, "org": org, "auth": "OK", "auth_note": auth_note,
                    "ok": ok, "fail": fail, "forbidden": forbidden, "error": error, "total": total,
                    "endpoints": ep_results})
    client.close()

# ── Final report ───────────────────────────────────────────────────────────────
print(f"\n\n{'='*80}")
print("FINAL SUMMARY TABLE")
print(f"{'='*80}")
print(f"{'EMAIL':<40} {'ROLE':<12} {'ORG':<20} {'AUTH':<8} {'OK':<5} {'FAIL':<5} {'ERR':<5}")
print(f"{'─'*40} {'─'*12} {'─'*20} {'─'*8} {'─'*5} {'─'*5} {'─'*5}")
for s in summary:
    if s["auth"] == "OK":
        print(f"{s['email']:<40} {s['role']:<12} {s['org']:<20} {'OK':<8} {s.get('ok',0):<5} {s.get('fail',0):<5} {s.get('error',0):<5}")
    else:
        print(f"{s['email']:<40} {s['role']:<12} {s['org']:<20} FAILED   {s['auth_note'][:30]}")

print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Save JSON
with open("scripts/ui_test_results.json", "w") as f:
    json.dump(summary, f, indent=2, default=str)
print("Results saved to scripts/ui_test_results.json")
