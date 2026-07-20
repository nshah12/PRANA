# PRANA API Changelog

> **Source of truth for all breaking changes, deprecations, and migrations.**
> Every breaking change MUST be documented here before it ships.
> HRMS partners and mobile teams reference this document.

---

## How to read this document

| Symbol | Meaning |
|--------|---------|
| 🔴 BREAKING | Field removed, renamed, or type changed — requires migration |
| 🟡 DEPRECATED | Endpoint/version still works but will be removed on sunset date |
| 🟢 ADDED | New optional field or endpoint — backward compatible |
| ⚪ INTERNAL | Internal change, no client impact |

---

## v1 — Current stable version

**Status:** Active
**Released:** 2025-01-01
**Deprecated:** —
**Sunset:** —

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/ingest/upload` | Upload single document |
| POST | `/v1/ingest/batch` | Upload batch (CSV + ZIP) |
| GET | `/v1/ingest/documents` | List documents for tenant |
| GET | `/v1/ingest/stats` | Dashboard stats |
| GET | `/v1/ingest/exceptions` | Exception queue |
| POST | `/v1/ingest/exceptions/{id}/resolve` | Resolve exception |
| GET | `/v1/vault/documents` | Employee document list |
| GET | `/v1/vault/health` | Vault health score |
| GET | `/v1/vault/career` | Career timeline |
| GET | `/v1/vault/employers` | Employer list |
| GET | `/v1/vault/activity` | Access activity log |
| POST | `/v1/vault/share` | Create share token |
| GET | `/v1/dpdp/erasure-request` | DPDP erasure |
| GET | `/v1/ask/` | Ask PRANA chatbot |
| POST | `/v1/public/contact` | Submit a contact-form message (no auth) |
| POST | `/v1/public/org-register/init` | Org self-registration step 1: email + OTP |
| POST | `/v1/public/org-register/verify` | Org self-registration step 2: verify OTP |
| POST | `/v1/public/org-register/complete` | Org self-registration step 3: submit application |
| GET | `/v1/public/verify/{code}` | Verify a PRANA credential code (recruiters/banks, no auth) |
| GET | `/v1/public/qr/{code}` | QR code PNG for a credential verification URL (no auth) |

### Response conventions (v1)
```json
// Collections always wrapped:
{ "documents": [...], "total": 42 }

// Errors always:
{ "error": "ERROR_CODE", "message": "...", "request_id": "uuid" }

// Dates always ISO 8601:
{ "pushed_at": "2025-06-17T14:30:00.000Z" }
```

### Change history

| Date | Type | Endpoint | Change |
|------|------|---------|--------|
| 2025-06-17 | 🟢 ADDED | `/v1/ingest/stats` | New dashboard stats endpoint |
| 2025-06-17 | ⚪ INTERNAL | All endpoints | Added `DeprecationMiddleware` — no client impact |
| 2026-07-15 | 🟢 ADDED | `/v1/public/*` | Versioned mirror of the previously-unversioned `/public/*` endpoints (contact form, org self-registration, credential verification), per `.claude/rules/api-versioning.md` — "only public/HRMS/mobile APIs are versioned." Purely additive: `/public/*` keeps working unchanged, same handlers, no deprecation planned yet. New integrators (recruiters/banks calling credential verification) should prefer `/v1/public/verify/{code}`. |
| 2026-07-15 | ⚪ INTERNAL | `/public/contact-inquiries`, `/public/org-applications*` | Relocated to `/admin/contact-inquiries`, `/admin/org-applications*` (`routers/pa_admin.py`) — these were PA-authenticated reads that never belonged under a path named "public." Old paths no longer resolve; the only caller (Portal's `ContactInquiries.tsx`) was updated in the same change. Not a partner-facing contract (unversioned admin-console-internal endpoint), so no `/v1/` mirror, deprecation window, or partner notification applies. |
| 2026-07-19 | ⚪ INTERNAL | `/admin/tenants/{id}/suspend`, `/admin/tenants/{id}/activate` | Removed unreachable duplicate route definitions in `pa_admin.py` (shadowed by `tenants.py`, which was always the route FastAPI dispatched to) — no client impact |
| 2026-07-19 | ⚪ INTERNAL | `/admin/tenants/{id}/suspend`, `/admin/tenants/{id}/activate` | Suspend/activate now publish an audit Kafka event (`TENANT_SUSPENDED`/`TENANT_ACTIVATED`) and record the transition in `account_status_event`; previously only `tenant.status` was updated, so this history was invisible to CISO/PA views — no response shape change |
| 2026-07-19 | ⚪ INTERNAL | `/v1/manifests/*`, `/v1/unclassified/*`, `/admin/manifests/*` | Fixed auth and DB wiring that referenced `request.state.jwt_claims` and `request.app.state.db`, neither of which any middleware or dependency ever set — every one of these endpoints always returned 401 or raised an unhandled exception regardless of a valid token. Rewired to the standard `dependencies.py` DI pattern (`AuthUser`/`require_oa`/`PortalAdmin`/`DbConn`) used by every other router. This restores previously non-functional behavior; it is not a contract change |

---

## How to migrate when a breaking change is announced

1. Read the migration section for the specific endpoint below
2. Update your integration in staging
3. Test against `api-staging.prana.in/v2/...`
4. Confirm with PRANA team → they flip your API key to v2
5. PRANA monitors v1 usage in analytics — will reach out if you haven't migrated before sunset

---

## Partner notification process

When a breaking change is planned:
1. Entry added to `BREAKING_CHANGES` in `prana-api/versioning.py`
2. Entry added to `DEPRECATED_ENDPOINTS` in `prana-api/versioning.py`
3. Email sent to all `api_key` holders for affected tenant (90 days before sunset)
4. `notify_sent: True` flipped in versioning.py — CI check blocks deployment until this is done
5. Deprecation headers appear on all calls to deprecated endpoint from that point
6. On sunset date: endpoint returns 410 Gone, CI check fails if any code still calls it

---

## Upcoming changes (planned, not yet deprecated)

None currently planned.

---

## Archived versions

None yet.
