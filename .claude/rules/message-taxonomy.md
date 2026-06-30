# PRANA Message Taxonomy Rules
# Auto-loaded always — message taxonomy is mandatory for all services
# ENFORCEMENT: scripts/enforce_rules.py — MSG-01 (hardcoded error English), MSG-02 (hardcoded success English)
# Run /enforce before any PR merge. Violations block deployment.

## The contract — NOTHING hardcoded. Ever.

The backend NEVER emits human-readable English sentences in API responses.
The frontend NEVER has string literals for user-facing messages in component code.

Every message that a user sees must flow through this chain:

```
Backend emits typed code string
  → Frontend receives it
  → t() / tError() / tSuccess() / tStatus() maps code → locale string
  → User sees the display text
```

Adding a new language = one new JSON file. Zero backend changes.

## Taxonomy files (single source of truth)

| File | Contents | Who uses it |
|------|----------|-------------|
| `prana-api/errors.py` | `PranaError(StrEnum)` — ~85 error codes | All prana-api routers, prana-ask main.py |
| `prana-api/messages.py` | `SuccessCode`, `InfoCode`, `ValidationCode`, `StatusCode` | All prana-api routers, Kafka consumers |
| `prana-ai/pipeline/errors.py` | `PipelineError(StrEnum)` — ~80 pipeline stage error codes | prana-ai pipeline stages |
| `prana-ask/errors.py` | `AskError(StrEnum)` — 7 codes | prana-ask main.py |
| `prana-portal/src/i18n/en.json` | Master English locale — all ~280 codes | Portal (React) via t() |
| `prana-mobile/i18n/en.json` | Same locale for mobile | Mobile (Expo) via t() |
| `prana-docs/wireframes/PRANA_Message_Taxonomy.html` | Searchable reference | Engineers, QA |

## How to add a new message (correct process)

### New error in prana-api

```python
# 1. Add to errors.py
class PranaError(StrEnum):
    MY_NEW_CODE = "MY_NEW_CODE"   # value MUST equal name

# 2. Use in router/service
raise prana_error(PranaError.MY_NEW_CODE, status_code=400)

# 3. Add to locale JSON (both files)
# prana-portal/src/i18n/en.json  →  "error": { "MY_NEW_CODE": "User-facing English" }
# prana-mobile/i18n/en.json      →  same

# 4. Frontend uses automatically via tError("MY_NEW_CODE")
```

### New success/info/validation in prana-api

```python
# 1. Add to messages.py
class SuccessCode(StrEnum):
    MY_ACTION_DONE = "MY_ACTION_DONE"

# 2. Use in router
return success_response(SuccessCode.MY_ACTION_DONE, extra_field=value)
# → {"message": "MY_ACTION_DONE", "extra_field": "..."}

# 3. Add to both locale JSON files
# "success": { "MY_ACTION_DONE": "Action completed successfully." }
```

### New error in prana-ai / prana-ask

Same pattern, but add to the service-local `errors.py` (deployment boundary — no cross-imports).

## What enforce_rules.py checks

| Rule | What it catches | Severity |
|------|-----------------|----------|
| MSG-01 | `detail="English sentence..."` in HTTPException — any English sentence ≥10 chars in a detail= string | ERROR — blocks merge |
| MSG-02 | `"message": "English string"` in return dicts — any multi-word English message value | ERROR — blocks merge |

Both rules exempt: test files, errors.py, messages.py, f-strings, variable references.

## What to do in the frontend

```typescript
// Portal
import { tError, tSuccess, tStatus, tValidation, tInfo } from '@/i18n'

// Map API error code → display string
const msg = tError(error.detail)  // error.detail is "INVALID_TOTP" etc.

// Map success code → display string
const msg = tSuccess(response.message)  // response.message is "DOC_UPLOADED" etc.

// Mobile
import { tError, tSuccess } from '@/i18n'
// identical API
```

Never write: `<p>Document uploaded successfully</p>`
Always write: `<p>{tSuccess(response.message)}</p>`

## Naming conventions

- `PranaError`: DOMAIN_ISSUE — `TENANT_NOT_FOUND`, `INVALID_TOTP`, `ELEVATION_NOT_ACTIVE`
- `SuccessCode`: NOUN_VERB_PAST — `DOC_UPLOADED`, `TENANT_ACTIVATED`, `ELEVATION_ENDED`
- `InfoCode`: NOUN_STATE — `PIPELINE_QUEUED`, `SESSION_EXPIRING_SOON`
- `ValidationCode`: FIELD_RULE — `FIELD_REQUIRED`, `EMAIL_INVALID_FORMAT`
- `StatusCode`: STATE — `QUEUED`, `ROUTED`, `FAILED`
- `PipelineError`: `S{stage:02d}_{SHORT_DESCRIPTION}` — `S04_EXTRACT_LLM_TIMEOUT`
- Value ALWAYS equals name — never `INVALID_TOTP = "Incorrect authenticator code"`

## Code pattern (value == name)

```python
class PranaError(StrEnum):
    INVALID_TOTP = "INVALID_TOTP"   # value == name
    # NOT: INVALID_TOTP = "Incorrect authenticator code"  ← WRONG
```

This makes the code usable as a stable string for JSON serialization, audit logs, and i18n keys.
