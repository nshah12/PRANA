# PRANA API Rules
# Auto-loaded when editing prana-api/**
# ENFORCEMENT: scripts/enforce_rules.py — API-01 (no bare list return), API-02 (no raw dict(row)), KAFKA-01, KAFKA-02
# Run /enforce before any PR merge. Violations block deployment.

## Stack
- FastAPI + asyncpg + YugabyteDB + Temporal + Kafka + Redis
- Python 3.12, Pydantic v2

## Every endpoint must
1. Validate auth FIRST — before any DB call
2. Derive `tenant_id` from JWT claims — NEVER from request body or URL
3. Use Pydantic model for request body — never raw dict
4. Return serialized dicts — never raw asyncpg Records

## asyncpg serialization (ALWAYS explicit)
```python
{
    "field_id":  str(r["field_id"]),           # UUID → str
    "date_col":  r["date_col"].isoformat() if r["date_col"] else None,   # date
    "dt_col":    r["dt_col"].isoformat() if r["dt_col"] else None,       # datetime
    "json_col":  json.loads(r["json_col"]) if isinstance(r["json_col"], str) else (r["json_col"] or []),  # JSONB
}
```
Never `return dict(row)` directly — always explicit comprehension.

## Response shape contract
- Collections: `{"items": [...], "total": N}` — NEVER bare array `[...]`
- Single resource: `{"resource_name": {...}}`
- Errors: `{"error": "CODE", "message": "...", "request_id": "uuid"}`

## HTTP handler contract (Kafka — NEVER violate)
```
validate → S3 put → 1 DB write → 1 kafka.publish() → return 202
```
- NO `audit_event` INSERT in handlers — AuditConsumer owns that
- NO `temporal.start_workflow()` in handlers — WorkflowConsumer owns that
- NO notification dispatch in handlers — NotifConsumer owns that

## Error handling
- Catch specific exceptions — never bare `except:`
- Use error code strings as `detail` ("INVALID_TOTP") — frontend can i18n
- Log before raising HTTPException

## Async rules
- Never `time.sleep()` — use `await asyncio.sleep()`
- Never call sync I/O inside async handlers without `run_in_executor`
- DB connection is per-request — never share across requests

## Config
- All durations from `platform_config` / `tenant_config` — never hardcoded
- Secrets from env vars — never in source code
