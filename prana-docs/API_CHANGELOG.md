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
