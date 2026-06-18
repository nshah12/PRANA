# /check-breaking-change

Run the pre-production API compatibility check. Always run this before any deployment or PR that touches a versioned endpoint.

## What it checks
1. Sunset dates that have passed — endpoints that must be removed
2. Deprecated endpoints missing successor / migration_guide / notify_sent
3. Source code (Python + TypeScript) calling deprecated or sunset paths
4. v1 router files with field removals (potential breaking changes)
5. Breaking changes in versioning.py not yet documented in API_CHANGELOG.md

## How to run
```powershell
cd C:\Nilesh\claude-code\prana-api
python scripts/check_api_compat.py
```

Exit 0 = clean. Exit 1 = issues found, deployment blocked.

## If issues are found

**ERROR: sunset date passed** → Remove endpoint from router, update versioning.py status
**ERROR: notify_sent=False** → Send partner email first, then flip to True
**ERROR: not in changelog** → Add entry to prana-docs/API_CHANGELOG.md
**WARN: deprecated call in source** → Update call to successor endpoint
**WARN: field removed from v1** → Verify it's non-breaking, or move change to v2 router

## When to run (automatically)
- Before every PR merge that touches `prana-api/routers/`
- Before every deployment to staging or production
- After adding any entry to `DEPRECATED_ENDPOINTS` in versioning.py

## Arguments
Optional path to check specific file: `$ARGUMENTS`
