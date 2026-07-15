# PRANA — Kafka & Redis Architecture (Canonical Reference)

> **Status: DECIDED. Not a suggestion. Every service implementation must follow this.**
> Source of truth: `PRANA_Portal_v52.html` §19 (Tech Stack) + §20 (NFRs).

---

## 1. Why Kafka + Redis (Not Optional)

Scale targets from §20:
- **1,00,000 orgs · 1,00,00,000 employees · ~50 crore documents**
- **5,00,000 events/sec sustained write throughput**
- **Active-active: ap-south-1 (Mumbai) + ap-south-2 (Hyderabad). RTO = 0. RPO = 500ms.**

At this volume, synchronous HTTP handlers that chain DB writes → audit writes → multiple workflow starts are a scaling cliff. The correct pattern:

```
HTTP handler → validate → 1 DB write (source of truth) → 1 Kafka publish → return 202
                                           ↓
                              Consumers pick up from Kafka:
                              AuditConsumer     → INSERT audit_event
                              WorkflowConsumer  → start Temporal workflow(s)
                              SSEFanoutConsumer → Redis Pub/Sub → browser SSE
                              NotifConsumer     → SES / WhatsApp WABA
                              AnalyticsConsumer → vault health, embeddings
```

---

## 2. Kafka (Apache Kafka on AWS MSK)

**Config (from §19):** KRaft mode · Both regions · MirrorMaker 2 (MM2) bidirectional sync.

### 2.1 Topic Registry

| Topic | Key | Events | Partition Key |
|-------|-----|--------|---------------|
| `prana.ingest.events` | Ingest domain | `DOC_INGESTED`, `BATCH_UPLOADED` | `tenant_id` |
| `prana.pipeline.events` | Pipeline state | `STAGE_CHANGED`, `DOC_ROUTED`, `EXCEPTION_RAISED`, `EXCEPTION_RESOLVED`, `EXCEPTION_DISMISSED` | `document_id` |
| `prana.audit.events` | Immutable audit | all above + auth events | `tenant_id` |
| `prana.notifications` | Push/email | `DOC_ROUTED`, `EXCEPTION_RAISED`, `ELEVATION_APPROVED` | `user_id` |
| `prana.analytics.events` | Async analytics | `DOC_ROUTED`, `VAULT_HEALTH_TICK` | `tenant_id` |

### 2.2 Event Schemas

#### DOC_INGESTED
```json
{
  "event_type": "DOC_INGESTED",
  "event_id": "<uuid>",
  "occurred_at": "<iso8601>",
  "tenant_id": "<uuid>",
  "document_id": "<uuid>",
  "batch_id": "<uuid|null>",
  "doc_type": "SALARY_SLIP",
  "doc_period": "2024-01",
  "s3_key": "staging/<tenant>/<doc>.pdf",
  "s3_bucket": "prana-staging",
  "file_size_bytes": 123456,
  "file_hash_sha256": "<hex>",
  "original_filename": "slip_jan.pdf",
  "upload_comment": "Q4 batch",
  "actor_id": "<oa_user_id>",
  "actor_type": "OA_OPERATOR",
  "ip_address": "1.2.3.4",
  "user_agent": "Mozilla/..."
}
```

#### BATCH_UPLOADED
```json
{
  "event_type": "BATCH_UPLOADED",
  "event_id": "<uuid>",
  "occurred_at": "<iso8601>",
  "tenant_id": "<uuid>",
  "batch_id": "<uuid>",
  "doc_type": "SALARY_SLIP",
  "source": "PORTAL_UPLOAD",
  "total": 50,
  "accepted": 48,
  "rejected": 2,
  "total_bytes": 12345678,
  "started_at": "<iso8601>",
  "ended_at": "<iso8601>",
  "duration_ms": 1234,
  "filenames": ["a.pdf", "b.pdf"],
  "errors": [{"filename": "x.pdf", "error": "EMPTY_FILE"}],
  "actor_id": "<oa_user_id>",
  "actor_type": "OA_OPERATOR",
  "ip_address": "1.2.3.4",
  "user_agent": "Mozilla/..."
}
```

#### STAGE_CHANGED
```json
{
  "event_type": "STAGE_CHANGED",
  "document_id": "<uuid>",
  "tenant_id": "<uuid>",
  "pipeline_status": "EXTRACTING",
  "previous_status": "SCANNING",
  "occurred_at": "<iso8601>"
}
```

#### DOC_ROUTED
```json
{
  "event_type": "DOC_ROUTED",
  "document_id": "<uuid>",
  "tenant_id": "<uuid>",
  "employee_uuid": "<uuid>",
  "resolution_method": "PAN_TOKEN_MATCH",
  "resolution_confidence": 1.0,
  "occurred_at": "<iso8601>"
}
```

#### EXCEPTION_RAISED
```json
{
  "event_type": "EXCEPTION_RAISED",
  "document_id": "<uuid>",
  "exception_id": "<uuid>",
  "exception_type": "NO_MATCH",
  "tenant_id": "<uuid>",
  "occurred_at": "<iso8601>"
}
```

### 2.3 Consumer Responsibilities

| Consumer | Subscribes To | Action |
|----------|--------------|--------|
| `WorkflowConsumer` | `prana.ingest.events` (DOC_INGESTED) | `temporal.start_workflow(DocumentPipelineWorkflow)` + `BatchTimeoutMonitorWorkflow` |
| `WorkflowConsumer` | `prana.ingest.events` (BATCH_UPLOADED) | `temporal.start_workflow(BatchProgressWorkflow)` if batch_id present |
| `AuditConsumer` | `prana.audit.events` | `INSERT INTO audit_event` (append-only by policy — see §8 for the DB-level enforcement gap), dual-written to Immudb for cryptographic tamper-evidence |
| `SSEFanoutConsumer` | `prana.pipeline.events` | `redis.publish(f"sse:doc:{document_id}", status)` |
| `NotifConsumer` | `prana.notifications` | SES email / WhatsApp WABA dispatch |
| `AnalyticsConsumer` | `prana.analytics.events` | vault health recalc, trigger `InsightRefreshWorkflow` |

### 2.4 Producer Rules
- One `KafkaProducer` instance per service pod (created at startup, shared via `app.state`).
- Partition key = `tenant_id` for ingest/audit events (keeps tenant traffic on same partition for ordering).
- Partition key = `document_id` for pipeline events (all stage changes for one doc arrive in order).
- `acks=all` — no data loss on broker failure.
- Compression: `snappy`.
- Retry: 5 retries, exponential backoff, idempotent producer (`enable.idempotence=True`).

---

## 3. Redis (ElastiCache Global Datastore)

**Config (from §19):** Redis Enterprise · CRDT active-active · Both regions · sub-10ms cross-region sync.

### 3.1 Cache Namespaces

| Namespace | Key Pattern | TTL | Invalidation | CRDT Type |
|-----------|------------|-----|-------------|-----------|
| Identity | `pan_token:{pan_token}` | 30 min | DB trigger → DEL | LWW |
| Share token | `share:{token}` | Until `expires_at` | VaultService on revoke | LWW |
| Vault completeness | `vault:{tenant_id}` | 5 min | Doc push → DEL | LWW |
| SSE Pub/Sub | `sse:doc:{document_id}` | N/A (ephemeral channel) | Auto on subscriber disconnect | N/A |
| JWT revocation | `jwt:revoked:{jti}` | Until JWT natural expiry | Written on logout/elevation-end | LWW |
| Elevation session | `elevation:{elevation_id}` | Until `ends_at` | Written on elevation end-early | LWW |

### 3.2 SSE Pattern (Redis Pub/Sub → Browser)

```
Temporal stage activity
    → publishes STAGE_CHANGED to prana.pipeline.events
        → SSEFanoutConsumer
            → redis.publish("sse:doc:{document_id}", {"pipeline_status": "EXTRACTING"})
                → GET /ingest/status/{document_id}
                    → asyncio task: redis.subscribe("sse:doc:{document_id}")
                        → yield SSE frame to browser
```

**Never poll YugabyteDB from the SSE endpoint.** The old 2s DB poll pattern does not survive 10M documents at high concurrency.

### 3.3 Redis Rules
- No plaintext PAN/NIK ever cached — only `pan_token` (HMAC output) used as cache key.
- `usage_count` on share tokens uses **counter CRDT** for correct cross-region increment.
- JWT revocation list checked by Kong middleware on every request (before hitting FastAPI).

---

## 4. HTTP Handler Contract

Every ingest handler must follow this and only this pattern:

```python
# ✅ CORRECT — handler is thin, fast, returns 202
async def upload_documents(...):
    file_bytes = await f.read()
    _validate_file(f.filename, file_bytes)          # sync, in-memory, fast
    s3.put(staging_key, file_bytes)                 # must happen synchronously (need key in DB row)
    await db.execute("INSERT INTO document ...")    # source-of-truth write
    await kafka.publish("prana.ingest.events",      # single publish per file
        DOC_INGESTED_event)
    return 202

# ❌ WRONG — HTTP handler doing sequential sync work
async def upload_documents(...):
    await db.execute("INSERT INTO document ...")
    await db.execute("INSERT INTO audit_event ...")  # ← move to AuditConsumer
    await temporal.start_workflow(...)               # ← move to WorkflowConsumer
    await temporal.start_workflow(...)               # ← move to WorkflowConsumer
    await temporal.start_workflow(...)               # ← move to WorkflowConsumer
    return 202
```

Signals to Temporal (exception_resolved, elevation_approved) are the **one exception** — these are direct workflow signals, not Kafka events, because they target a specific running workflow instance and need the signal path.

---

## 5. Active-Active Topology

```
                    ┌─────────────────────────────────────┐
                    │         Route 53 Latency Routing     │
                    └──────────┬──────────────────┬───────┘
                               │                  │
              ┌────────────────▼───┐    ┌──────────▼──────────────┐
              │   ap-south-1       │    │   ap-south-2             │
              │   Mumbai           │    │   Hyderabad              │
              │                    │    │                          │
              │  Kong Gateway      │    │  Kong Gateway            │
              │  FastAPI pods      │    │  FastAPI pods            │
              │  Temporal workers  │    │  Temporal workers        │
              │  Kafka brokers ◄───┼────┼─► Kafka brokers (MM2)   │
              │  Redis CRDT ◄──────┼────┼─► Redis CRDT            │
              │  YugabyteDB ◄──────┼────┼─► YugabyteDB            │
              │  Qdrant            │    │  Qdrant                  │
              └────────────────────┘    └──────────────────────────┘
```

- **Tenant home-region write:** Kafka events produced to tenant's home region; MM2 mirrors to the other.
- **Temporal:** YugabyteDB is the persistence backend — same active-active cluster used by both Temporal worker pools.
- **Redis CRDT:** sub-10ms cross-region sync. Kong reads JWT revocation from local CRDT replica.

---

## 6. Kafka Consumer Startup

Consumers run as long-lived background tasks started at FastAPI `lifespan`:

```python
# prana-api/main.py lifespan
async with asynccontextmanager(lifespan):
    app.state.kafka_producer = KafkaProducer(settings)
    await app.state.kafka_producer.start()

    consumers = [
        AuditConsumer(settings),
        WorkflowConsumer(settings, temporal_client),
        SSEFanoutConsumer(settings, redis_client),
        NotifConsumer(settings),
        AnalyticsConsumer(settings, temporal_client),
    ]
    for c in consumers:
        asyncio.create_task(c.run())
    yield
    await app.state.kafka_producer.stop()
```

Each consumer uses `aiokafka.AIOKafkaConsumer` with `group_id` per consumer type, enabling independent scaling and replay.

---

## 7. NFR Targets That Drove These Decisions

| NFR | Target | Mechanism |
|-----|--------|-----------|
| Write throughput | 5,00,000 events/sec | Kafka + YugabyteDB distributed writes |
| SSE latency | <500ms stage-change visible in browser | Redis Pub/Sub (no polling) |
| Audit durability | 7-year retention, tamper-evident | AuditConsumer → YugabyteDB hot → Iceberg cold, dual-written to Immudb (§8) |
| Cross-region lag | <500ms RPO | Kafka MM2 + Redis CRDT + YugabyteDB active-active |
| Handler P99 latency | <200ms for upload accept | One DB write + one Kafka publish only |
| Zero message loss | File never silently dropped | `acks=all` + Temporal durability for pipeline |

---

## 8. Immudb — Tamper-Evident Audit Ledger (DECIDED)

**Status: DECIDED, dev infra live.** 4th data store alongside YugabyteDB / Kafka / Redis.

### 8.1 Why

`audit_event` in YugabyteDB is an **ordinary mutable table**. The only trace of an
"append-only" design intent is a single SQL comment in `prana-db/schema.sql`:

```sql
-- IMPORTANT: REVOKE UPDATE, DELETE ON audit_event FROM app_role — append-only by policy.
```

This was **never executed as real DDL** — no `REVOKE` statement exists anywhere in the
codebase, and `app_role` is not even defined. Today, any process holding the app's DB
credentials can silently UPDATE or DELETE audit rows; the DPDP "never erase audit_event"
rule (`.claude/rules/compliance-dpdp.md`) is enforced by code convention only, not by the
database. Immudb closes this gap: it is a real, cryptographically verifiable, append-only
ledger (Codenotary open source, `immudb-py` client) — tampering with a value after it is
written is mathematically detectable via `verifiedGet`, independent of DB credentials.

### 8.2 Scope — what actually reaches Immudb

The rule of thumb: **whatever gets a `prana.audit.events` copy becomes an `audit_event` row,
and every `audit_event` row is dual-written to Immudb.** `AuditConsumer` subscribes to two
topics (`prana.audit.events`, `prana.vault.events`); everything it reads on those topics goes
through `_write_audit()` → Immudb, with exactly one carve-out (below).

Every domain helper in `kafka/producer.py` publishes to its own per-domain topic **and** CCs
`prana.audit.events`, except the two rows marked "no" below:

| Domain helper | Audited → Immudb? | Example event types |
|---|---|---|
| `doc_ingested()` | Yes | `DOC_INGESTED` |
| `batch_uploaded()` | Yes | `BATCH_UPLOADED` |
| `stage_changed()` | Yes | `STAGE_CHANGED` (pipeline stage transitions) |
| `doc_routed()` | Yes | `DOC_ROUTED` |
| `exception_raised()` / `exception_resolved()` | Yes | `EXCEPTION_RAISED`, `EXCEPTION_RESOLVED`, `EXCEPTION_DISMISSED` |
| `doc_accessed()` | **No, with one exception** — see below | `DOC_ACCESSED`, `SHARE_ACCESSED` |
| `share_event()` | Yes | `SHARE_CREATED`, `SHARE_REVOKED`, `SHARE_EXPIRED`, `SHARE_OTP_*` |
| `auth_event()` | Yes | `SESSION_CREATED`, `LOGIN_SUCCESS`, `LOGIN_FAILED`, `TOTP_*`, `OTP_*` |
| `employee_event()` | Yes | `EMPLOYEE_ONBOARDED/ACTIVATED/EXITED/REJOINED`, `EMPLOYEE_PASSWORD_RESET`, `EMPLOYEE_SESSIONS_REVOKED`, `EMPLOYEE_SHARES_REVOKED` |
| `tenant_event()` | Yes | `TENANT_CREATED`, `TENANT_CONFIG_UPDATED`, `API_KEY_CREATED/REVOKED`, `KEK_ROTATED` |
| `oa_user_event()` | Yes | `OA_USER_CREATED`, `OA_USER_LOCKED`, `ELEVATION_APPROVED/DENIED/EXPIRED`, `OA_WELCOME_RESENT`, TOTP/password resets |
| `compliance_event()` | Yes | `CONSENT_GRANTED/WITHDRAWN`, `ERASURE_*`, `CORRECTION_*`, `GRIEVANCE_*` |
| `security_event()` | Yes | `ANOMALY_DETECTED`, `ACCOUNT_LOCKED`, `CROSS_TENANT_UPLOAD`, `CSAM_DETECTED` |
| `statutory_event()` | Yes | `OBLIGATION_DUE/OVERDUE`, `PF_FILING_DUE`, `GRATUITY_*` |
| `integration_event()` | Yes | `HRMS_WEBHOOK_*`, `EPFO_VERIFICATION_*`, `KMS_*`, `TEXTRACT_*` |
| `platform_event()` | **No** | `WORKER_STARTED/CRASHED`, `HEALTH_CHECK_FAILED`, `DEPLOYMENT_*` — ops telemetry, no `TOPIC_AUDIT` publish at all |
| `notify_email/sms/push/whatsapp/bell()` | **No** | Channel-specific dispatch only, no `TOPIC_AUDIT` publish |
| `cache_invalidate()` | **No** | Internal cache-signal only, no `TOPIC_AUDIT` publish |

**The one carve-out:** `AuditConsumer._run_loop()` special-cases `event_type == "DOC_ACCESSED"`
— those events are routed to `_write_access_log()` (→ `document_access_log`, the CISO/employee
access-visibility table) instead of `_write_audit()`, so routine document views are **not**
mirrored to Immudb. Anything else on `prana.audit.events` (including `SHARE_ACCESSED`, which
`doc_accessed()` can also emit) falls through to `_write_audit()` and **is** Immudb'd, since the
routing check matches on the literal string `"DOC_ACCESSED"` only.

`_write_access_log()` itself is a separate table/concern end to end and is never dual-written.

### 8.3 Architecture

```
AuditConsumer._write_audit(event)
    → INSERT INTO audit_event ... RETURNING event_id   (source of truth, YugabyteDB)
    → anyio.to_thread.run_sync(immudb.verified_set,     (best-effort, off the event loop —
        key=f"audit:{event_id}", value={...})            immudb-py's gRPC client is sync)
```

- Key: `audit:{event_id}` — deterministic, 1:1 with the YugabyteDB row.
- Value: JSON of `event_type, actor_type, actor_id, tenant_id, document_id, ip_address, event_metadata, occurred_at`.
- **Resilience:** Immudb is a secondary verification store. A failed dual-write is logged
  (`log.exception`) and swallowed — it must never block or roll back the primary
  `audit_event` write, and must never stall the Kafka consumer's batch-commit loop.
- Skipped when `ON CONFLICT DO NOTHING` yields no row (duplicate Kafka redelivery) — the
  first successful delivery already dual-wrote it.
- `ImmudbService` (`prana-api/services/immudb_service.py`) follows the same wrapper
  convention as `KMSService`: plain class, primitive constructor args, real exceptions
  never a silent placeholder.

### 8.4 Dev Infra

- `docker-compose.yml`: `codenotary/immudb:1.9.5` on `localhost:3322` (gRPC), `9497`
  (metrics), `8081` (web console). Volume `immudb_data`.
- Settings (`prana-api/config.py`): `immudb_host`, `immudb_port`, `immudb_user`,
  `immudb_password`, `immudb_database` (dev default database: `prana_audit`).
- `immudb_password` is covered by the fail-closed production guard
  (`Settings.assert_production_ready()`) — refuses to boot in prod on the `immudb` dev default.
- Wired in `prana-api/main.py` `lifespan()` non-fatally (like S3/Temporal/Kafka) — dev
  without the Immudb container up still boots with `app.state.immudb_service = None`,
  and `AuditConsumer` simply skips the dual-write.

### 8.5 Resolved (2026-07-15) — REVOKE executed + periodic verification added

Both halves of the original gap are now closed:

1. **The REVOKE is real DDL, not just a comment.** `prana-db/migrations/039_audit_role_revoke.sql`
   (also folded into `schema.sql` LAYER 14, so a fresh deploy gets it automatically) creates
   `prana_app_role` — the role the app's runtime DB pool actually connects as (`config.py`
   `db_user`/`db_password`, default `prana_app_role`/`prana_app_role` in dev) — grants it
   full CRUD on every table, then `REVOKE UPDATE, DELETE ON audit_event FROM prana_app_role`.
   The app can still `INSERT` (AuditConsumer's dual-write path) but can no longer alter or
   delete existing rows, even if its own credentials are compromised or misused. The
   fail-closed production guard (`Settings.assert_production_ready()`) additionally refuses
   to boot if `db_user` is `yugabyte`/`postgres`/`root` — the app must never run as the
   DB superuser that could bypass this REVOKE.

2. **Something now actually checks.** Provable-but-unchecked tampering was the real
   danger: `verified_get()` can prove a row was altered, but only if someone calls it.
   `AuditIntegrityVerificationWorkflow` (`workflows/audit_integrity.py`, Pattern 3 —
   Temporal Schedule, `secops-queue`, default every 60 min via
   `audit_integrity_check_interval_minutes`) re-checks the most recent 500 `audit_event`
   rows against their Immudb dual-write on every run. A mismatch (row altered) or an
   `unverified` result (Immudb's own cryptographic proof failed) publishes an
   `AUDIT_INTEGRITY_MISMATCH` security event, which `NotifConsumer` turns into an email to
   every active Portal Admin. `AuditIntegrityService` (`services/audit_integrity_service.py`)
   holds the comparison logic — zero Temporal imports, so it's directly unit-testable.

**Residual gap:** this only re-verifies the most recent 500 rows per run (no persistent
checkpoint/pagination across the full 7-year hot-tier history), so it re-covers recent,
active data repeatedly but doesn't guarantee eventual coverage of the entire table. Older,
already-cold-archived partitions are effectively out of scope for this workflow. Extending
it to paginate through full history is a future enhancement, not yet scheduled.

## 9. Application Error Observability — 4th Incident Track (DECIDED, APPROVED 2026-07-15)

Full design: `prana-docs/ERROR_OBSERVABILITY_DESIGN.md`. Summary here for readers of this
doc who won't necessarily open that one.

### 9.1 Why

Before this track existed, PRANA had **zero durable trace of code-level exceptions** —
no Sentry/Datadog/structured logging/log aggregation anywhere. The global FastAPI exception
handler didn't log at all, explicit `except Exception: log.exception(...)` blocks only
reached Python's unstructured stderr "handler of last resort" (`logging.basicConfig()` was
never called), and no exception path — caught or uncaught — ever created an incident.

### 9.2 Capture layers (all three ship together, no phase-2 deferral)

| Layer | Entry point | Source value written |
|-------|-------------|----------------------|
| HTTP | `main.py`'s exception handlers (`db_unavailable_handler` etc. + `unhandled_exception_handler`) | `request.url.path` |
| Kafka consumers | `kafka/error_capture.py`'s `record_consumer_error()`, called from all 20 consumers' outer `except Exception` | the consumer's class name, e.g. `"AuthConsumer"` |
| Temporal activities | `workflows/error_capture_interceptor.py`'s `ErrorObservabilityInterceptor` (registered on `Worker(...)` in `worker.py`) | the activity's registered name, e.g. `"verify_audit_integrity"` |

Every capture site calls `ErrorObservabilityService.record()` — never raw SQL — and is
itself wrapped in a self-protective `except Exception: pass`/`log.exception(...)` so the
error-recording infrastructure can never recursively fail the request/consumer/activity it's
trying to observe.

### 9.3 Storage: `error_event` (migration `040_error_event.sql`, not in `schema.sql` — see file header)

Deduplicated by `fingerprint = sha256(exception_type + top_traceback_frame_location +
normalized_message)` — the same bug recurring with different input data collapses to one row
with a growing `occurrence_count`, not one row per occurrence. `message`/`traceback` are
regex-scrubbed for PAN/JWT-shaped/email/`+91`-mobile strings before being written, and only
`traceback.format_exc()` text is ever captured — never local variable values (a realistic
PAN/salary leak vector). 90-day retention via `error_event_retention_days` (`platform_config`).

### 9.4 Promotion to a real incident: `ErrorThresholdEvaluationWorkflow`

Pattern 3 (Temporal Schedule), `secops-queue`, default every 15 min via
`error_threshold_check_interval_minutes`. Each run scans open (`NEW`/`ACKNOWLEDGED`,
unlinked) `error_event` rows and promotes qualifying ones into the **same** `incident` table
used by the business-event track (§8's neighbor, not a second incident lifecycle) —
`services/error_threshold_service.py` holds the classification rules:

| Condition | Severity |
|-----------|----------|
| Security/crypto-critical source (`/auth/`, `/totp/` HTTP prefixes, `AuthConsumer`, `verify_audit_integrity`) | P1 on first occurrence |
| Compliance-critical endpoint (`/v1/dpdp/`, `/v1/ingest/`) recurring 3+ times within 10 min | P2 |
| Any other genuinely new fingerprint | P2 on first occurrence |
| Anything else recurring 10+ times within 15 min | P3 |

### 9.5 Portal UI

Folded into the existing PA/CISO incident-register screens as an "Errors" tab (not a
standalone page) — `prana-portal/src/pages/pa/SecurityIncidentRegister.tsx` (PA, backed by
`/admin/errors*`, full list/acknowledge/ignore/resolve/promote-to-incident) and
`prana-portal/src/pages/ciso/SecurityIncidents.tsx` (CISO, backed by `/v1/ciso/errors*`,
tenant-scoped — own tenant plus `tenant_id IS NULL` platform-level errors — read/acknowledge/
resolve only, no ignore/promote).
