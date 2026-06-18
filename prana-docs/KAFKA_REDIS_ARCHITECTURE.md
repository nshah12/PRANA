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
| `AuditConsumer` | `prana.audit.events` | `INSERT INTO audit_event` — immutable, no UPDATE/DELETE ever |
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
| Audit durability | 7-year retention, immutable | AuditConsumer → YugabyteDB hot → Iceberg cold |
| Cross-region lag | <500ms RPO | Kafka MM2 + Redis CRDT + YugabyteDB active-active |
| Handler P99 latency | <200ms for upload accept | One DB write + one Kafka publish only |
| Zero message loss | File never silently dropped | `acks=all` + Temporal durability for pipeline |
