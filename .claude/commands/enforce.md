# /enforce

Run the full pre-deploy gate. Every rule, mechanically checked. Nothing ships until this passes.

## What it checks (in order)
**[1/2] Rule Enforcement Scanner** (`scripts/enforce_rules.py`)
- [SEC-01] No raw salary/PAN field names in API responses
- [SEC-02] No plaintext PAN as Redis cache key
- [SEC-03] tenant_id never from request body or URL
- [SEC-04] No hardcoded secrets or KMS ARNs
- [DB-01]  No f-string SQL
- [DB-02]  No SELECT * (warn)
- [DB-03]  No bare except:
- [API-01] No bare list [] return from routers
- [API-02] No raw dict(row) return without serialization
- [KAFKA-01] No audit_event INSERT in HTTP handlers
- [KAFKA-02] No temporal.start_workflow in HTTP handlers
- [DEPLOY-01] No cross-service imports (prana-ai/prana-ask ← prana-api)
- [TEMPORAL-01] No @workflow.run method exceeding 20 lines
- [FRONTEND-01] No nested Pressable/TouchableOpacity (warn)
- [FRONTEND-02] useQuery without error state handling (warn)

**[2/2] API Compatibility Check** (`scripts/check_api_compat.py`)
- Sunset dates passed
- Missing partner notification
- Source code calling deprecated endpoints
- Breaking changes not in API_CHANGELOG.md

## How to run
```powershell
cd C:\Nilesh\claude-code\prana-api
powershell -File scripts/pre_deploy_check.ps1
```

## When to run
- Before ANY PR merge touching prana-api, prana-portal, prana-mobile, prana-ai, prana-ask
- Before ANY deployment to staging or production
- After completing any feature — verify no rules were accidentally violated

## Exit codes
0 = all checks passed, safe to deploy
1 = violations found, deployment blocked
