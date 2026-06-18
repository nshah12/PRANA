@../CLAUDE.md

# PRANA API — Backend

## Stack
- **Language:** Python 3.12
- **Web framework:** FastAPI
- **Workflow engine:** Temporal Python SDK v1.x
- **Event streaming:** Apache Kafka (aiokafka) — `prana-api/kafka/` — producer + 5 consumers
- **Database:** YugabyteDB (asyncpg driver)
- **Cache:** Redis Enterprise CRDT (redis-py async) — identity, share tokens, vault health, SSE Pub/Sub, JWT revocation
- **Object storage:** AWS S3
- **KMS:** AWS KMS (ap-south-1, customer-managed CMKs)
- **API gateway:** Kong

## Kafka — HTTP Handler Contract (NEVER violate)
HTTP handlers do exactly this and nothing more:
```
validate → S3 put → INSERT document row → kafka.publish(DOC_INGESTED) → return 202
```
**No** `INSERT INTO audit_event` in HTTP handlers — AuditConsumer owns that.
**No** `temporal.start_workflow()` in HTTP handlers — WorkflowConsumer owns that.
**No** notification dispatch in HTTP handlers — NotifConsumer owns that.
Exception: direct Temporal **signals** (exception_resolved, elevation_approved) are OK in handlers — they target a specific running workflow instance, not a fan-out.

Full reference: `prana-docs/KAFKA_REDIS_ARCHITECTURE.md`

## Kafka Topics (5 total)
| Topic | Partition Key |
|-------|--------------|
| `prana.ingest.events` | `tenant_id` |
| `prana.pipeline.events` | `document_id` |
| `prana.audit.events` | `tenant_id` |
| `prana.notifications` | `user_id` |
| `prana.analytics.events` | `tenant_id` |

## Service Architecture
The 9 Temporal workflow owner services (from PRANA_Portal_v52.html):

| # | Service | Owns |
|---|---------|------|
| 1 | **AuthService** | Login, TOTP, sessions, lockouts |
| 2 | **IdentityService** | employee_user, pan_token dedup, vault activation |
| 3 | **TenantService** | tenant CRUD, OA users, KEK provisioning |
| 4 | **IngestService** | Document upload, pipeline trigger, API key auth |
| 5 | **PipelineService** | 6-stage AI pipeline orchestration |
| 6 | **VaultService** | Document access, watermarking, share tokens |
| 7 | **AdminService** | employee_master, elevation, audit |
| 8 | **ComplianceService** | DPDP erasure, consent, export, grievance |
| 9 | **AnalyticsService** | vault_completeness, career insights, embeddings |

Each service = one FastAPI router + one or more Temporal workflow definitions.

## Temporal Pattern (ALWAYS follow this)
```python
# ✅ Business logic in plain service class — zero Temporal imports
class AccountLockService:
    async def apply_policy_lock(self, user_type, user_id, reason_code, duration_hours):
        ...  # writes to DB, no workflow engine awareness

# ✅ Temporal workflow is a thin adapter (<20 lines)
@workflow.defn
class PolicyLockWorkflow:
    @workflow.run
    async def run(self, ...):
        await workflow.execute_activity(AccountLockService.apply_policy_lock, ...)
```

Never put business logic inside `@workflow.run` or `@workflow.defn` methods directly.

## Database Rules
- Always use `asyncpg` for DB access — never sync drivers
- Row-level security (RLS) on all tenant-scoped tables
- `tenant_id` always derived from auth context, never from request payload
- Zero hardcoded durations — all from `platform_config` / `tenant_config` at runtime
- Schema: `db/schema.sql` (YugabyteDB DDL, 19 tables)

## Auth Middleware
- JWT validation at Kong API gateway (signature + `revoked` flag check via user_session)
- JWT JTI = `user_session.session_id`
- Session revocation: `UPDATE user_session SET revoked=TRUE` — instant, no TTL games

## Encryption in Code
```python
# pan_token — deterministic, cross-tenant dedup key
pan_token = hmac.new(platform_secret, pan.encode(), 'sha256').hexdigest()

# enc_pan — format-preserving, reversible per-employee
enc_pan = ff3.encrypt(pan, employee_dek)

# enc_dek — envelope encryption, stored in DB
enc_dek = kms.encrypt(dek, KeyId=tenant_kek_arn)
```

## API Key Auth (HRMS integrations)
- Header: `X-PRANA-Key-ID: {api_key_id}`, `X-PRANA-Signature: HMAC-SHA256(body, signing_secret)`
- Lookup: `SELECT * FROM api_key WHERE key_hash = SHA256($api_key_id) AND status='ACTIVE'`
- `tenant_id` comes from `api_key.tenant_id` — never the request body

## Error Response Format
```json
{ "error": "INVALID_TOTP", "message": "...", "request_id": "uuid" }
```
Always include `request_id` (ties to `login_attempt_log.request_id`).

## Coding Standards
- Type hints everywhere — Pydantic v2 for request/response models
- All DB mutations in transactions
- All time durations from config tables, never hardcoded
- No bare `except:` — catch specific exceptions
- Structured logging with `request_id` on every log line
