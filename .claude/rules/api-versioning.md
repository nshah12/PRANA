# PRANA API Versioning Rules
# Auto-loaded when editing prana-api/**
# ENFORCEMENT: scripts/check_api_compat.py — sunset dates, notify_sent, deprecated calls, changelog
# ENFORCEMENT: middleware/deprecation.py — adds headers at runtime, blocks sunset versions with 410
# Run /enforce before any PR merge. Violations block deployment.

## Versioning strategy: URL prefix
```
/v1/ingest/upload        ← HRMS API (stable contract)
/v1/vault/documents      ← Mobile app
/v1/dpdp/erasure-request ← Compliance
/auth/org/login          ← Unversioned (internal auth, no HRMS callers)
```
Auth, admin, and health endpoints are unversioned — only public/HRMS/mobile APIs are versioned.

## Single source of truth: prana-api/versioning.py
ALL versioning decisions live here:
- `VERSION_REGISTRY` — which versions are active/deprecated/sunset
- `DEPRECATED_ENDPOINTS` — individual endpoints being phased out
- `BREAKING_CHANGES` — documented history of every breaking change

**Never deprecate an endpoint anywhere else. Always update versioning.py first.**

## DeprecationMiddleware (prana-api/middleware/deprecation.py)
Runs automatically on every request. No router changes needed.
- Reads versioning.py
- Adds `Deprecation`, `Sunset`, `Link`, `X-Migration-Guide` headers to deprecated responses
- Returns `410 Gone` for sunset versions — blocks calls entirely

## Pre-production check: scripts/check_api_compat.py
Run before every deployment: `python scripts/check_api_compat.py`
Catches:
- Sunset dates that have passed (deploy blocker)
- Missing partner notification (deploy blocker)
- Source code calling deprecated endpoints (warning)
- v1 field removals that may be breaking (warning)
- Breaking changes not in API_CHANGELOG.md (deploy blocker)

## What is and isn't a breaking change

| Change | Breaking? | Action |
|--------|----------|--------|
| Add optional field to response | NO | Safe to add in v1 |
| Add new optional request field | NO | Safe to add in v1 |
| Remove field from response | YES | Must go in v2 |
| Rename field | YES | Must go in v2 |
| Change field type | YES | Must go in v2 |
| Add required request field | YES | Must go in v2 |
| Change HTTP status code | YES | Must go in v2 |
| New endpoint | NO | Add to v1 is fine |

## How to introduce a breaking change (correct process)
1. Create `prana-api/routers/v2/` with new router file
2. Add entry to `BREAKING_CHANGES` in versioning.py
3. Add entry to `DEPRECATED_ENDPOINTS` with `sunset_on` = today + 90 days
4. Document in `prana-docs/API_CHANGELOG.md`
5. Send partner notification email → flip `notify_sent: True`
6. Mount v2 router in main.py under `/v2/...`
7. Run `python scripts/check_api_compat.py` — must pass clean
8. On sunset date: remove v1 endpoint, update VERSION_REGISTRY status

## HRMS partner API key behaviour
Each `api_key` row has `api_version` column.
Old API keys keep v1 behaviour even after v2 ships.
Never break an existing API key's contract mid-term.

## Documentation
`prana-docs/API_CHANGELOG.md` — human-readable changelog for HRMS partners and mobile team.
Every breaking change must appear here before deployment.
