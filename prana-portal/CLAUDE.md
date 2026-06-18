@../CLAUDE.md

# PRANA Portal — Employer / Admin Web App

## What is the Portal
The Portal is the web interface used by organisations (employers) to push documents, manage employees, and administer access. It is NOT the employee-facing app (that is prana-mobile). Two separate login surfaces, two separate audiences.

## Login Surfaces
| URL | Who logs in | Table |
|-----|------------|-------|
| `prana.in/org/login` | OA-Operator, OA-Admin, CHRO, CFO, Tenant CISO | `oa_user` |
| `prana.in/admin/login` | Portal Admin (PRANA platform staff only) | `portal_admin` |

## Roles & Screen Access
| Role | What they can do |
|------|----------------|
| **OA-Operator** | Upload documents, view exception queue, request elevation |
| **OA-Admin** | Everything OA-Operator does + create/deactivate users, approve elevations, unlock accounts, view CISO dashboard |
| **CHRO** | Vault completeness reports, weekly/monthly digest |
| **CFO** | Financial analytics, anomaly acknowledgement |
| **Tenant CISO** | Security dashboard, login feed, document access log, flag review, force-logout |
| **Portal Admin (PA)** | Platform-wide: tenant onboarding, config, PA alert resolution — @prana.in email only |

## Stack
- **Framework:** React.js (Vite + React Router v6) — SPA, all routing client-side
- **UI:** shadcn/ui + Tailwind CSS
- **State:** React Query (server state) + Zustand (UI state)
- **Auth:** JWT from `prana-api` — store in httpOnly cookie, never localStorage
- **API calls:** via Kong API gateway (`api.prana.in`) — same API layer used by prana-mobile

## Auth Flow (Portal)
1. POST `/auth/org/login` with `{ email, password }` → returns `{ requires_totp: true }`
2. POST `/auth/org/totp` with `{ session_token, code }` → sets httpOnly refresh cookie + returns access JWT
3. All subsequent requests: `Authorization: Bearer {jwt}` header
4. JWT refresh: silent POST `/auth/refresh` before expiry (1hr JWT, 7-day refresh)
5. `force_reset = TRUE` → redirect to `/reset-password` before any other action

## Key Portal Flows

### Document Upload (OA-Operator)
- Single upload: drag-and-drop PDF → POST `/ingest/upload` → `pipeline_status` polling via SSE
- Batch upload: CSV manifest + ZIP → POST `/ingest/batch` → BatchProgressWorkflow fan-out
- Show per-file pipeline_status: QUEUED → ENCRYPTING → SCANNING → EXTRACTING → RESOLVING → ROUTED
- Exception queue: files stuck in RESOLVING need manual identity resolution → OA-Admin resolves → `exception_resolved` signal to Temporal

### Elevation (OA-Operator → OA-Admin approval)
- OA-Operator requests elevation: POST `/admin/elevations` `{ duration_hours: 2|4|8, reason }`
- OA-Admin sees pending request in sidebar badge → approves/denies
- During approved window: all actions carry `elevation_id` — clearly marked in UI with amber banner "Elevated session — ends in 1h 43m"
- Operator can end early: `POST /admin/elevations/{id}/end-early`

### CISO Security Dashboard
- Login feed: `login_attempt_log` — filter by outcome, flagged, foreign IP
- Account locks: `account_status_event WHERE event_type='POLICY_LOCK' AND reversed_by_event_id IS NULL`
  - Show: "Locked — BULK_ACCESS_ANOMALY. Auto-unlocks in 18h 23m" with "Unlock now" button
- Document access flags: `document_access_log WHERE is_flagged=TRUE`
- Force-logout: revoke session → `POST /auth/sessions/{session_id}/revoke`

### CHRO / CFO Dashboards
- Vault completeness: `employee_master.vault_completeness` — aggregate per department/grade
- CHRO digest: weekly/monthly scheduled by `DigestWorkflow` (driven by `digest_weekly_cron` / `digest_monthly_cron` config)
- CFO anomalies: POST `/cfo/anomalies/{id}/acknowledge` → `AnomalyAcknowledgementWorkflow`

## Config Tables (platform_config / tenant_config)
Every duration is runtime-configurable — **never hardcode these in the portal**:
```sql
-- Resolution: tenant_config overrides platform_config
SELECT COALESCE(
  (SELECT config_value FROM tenant_config WHERE tenant_id=$1 AND config_key=$2),
  (SELECT config_value FROM platform_config WHERE config_key=$2)
)
```
Key config values that affect Portal UI:
| Key | Default | Affects |
|-----|---------|---------|
| `totp_lockout_cooldown_minutes` | 30 | CISO lock countdown |
| `exception_sla_p50_hours` | 4 | Exception queue SLA indicator |
| `exception_sla_p95_hours` | 24 | Exception queue PA escalation |
| `share_otp_ttl_minutes` | 10 | C-Share OTP countdown |
| `domain_verification_max_hours` | 48 | Tenant onboarding domain check |

## Tenant Onboarding (Portal Admin only)
1. PA creates tenant application → `DomainVerificationWorkflow` polls DNS TXT every 15min for up to 48hr
2. PA reviews → `TenantProvisioningWorkflow` creates tenant row, KMS KEK, first OA-Admin account
3. First OA-Admin sets password + TOTP on first login (force_reset=TRUE)

## Coding Rules
- `tenant_id` always from JWT claims — never from URL params or request body
- Elevation banner: always visible during elevated sessions — not opt-in
- `linked_employee_user_id` conflict-of-interest guard: OA-Admin editing their own `employee_master` → must route through second-approver flow
- Portal Admin (`portal_admin`) accounts: lock threshold is **3** failed TOTP (not 5) — show stricter warning
- CISO can see full IP; employee sees city only — two separate response shapes for `document_access_log`
- `work email` (oa_user.email) must match `tenant.domain` — enforce client-side before API call
- Self-uploaded documents always show "Unverified — self-uploaded" badge — never treat as employer-verified
