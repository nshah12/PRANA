# PRANA Kafka & Redis Rules
# Auto-loaded when editing prana-api/kafka/**, prana-api/routers/ingest.py, or SSE code

## DECIDED INFRASTRUCTURE — not optional, not suggestions

## Kafka — AWS MSK, KRaft mode, both regions
Dev: `confluentinc/cp-kafka:7.6.1` on `localhost:9092`

### 5 topics (12 partitions each)
| Topic | Partition key | Owner |
|-------|-------------|-------|
| `prana.ingest.events` | tenant_id | AuditConsumer, WorkflowConsumer |
| `prana.pipeline.events` | document_id | SSEFanoutConsumer |
| `prana.audit.events` | tenant_id | AuditConsumer |
| `prana.notifications` | user_id | NotifConsumer |
| `prana.analytics.events` | tenant_id | AnalyticsConsumer |

### 5 consumers in `prana-api/kafka/consumers/`
- `AuditConsumer` — writes audit_event rows
- `WorkflowConsumer` — starts Temporal workflows
- `SSEFanoutConsumer` — pushes to Redis Pub/Sub for SSE
- `NotifConsumer` — dispatches SES/push notifications
- `AnalyticsConsumer` — writes analytics data

### HTTP handler contract (NEVER violate)
```
validate → S3 put → 1 DB write → 1 kafka.publish() → return 202
```
Nothing else in the HTTP path. Ever.

## Redis — ElastiCache Global Datastore, CRDT active-active
Dev: `redis:7.2-alpine` on `localhost:6379`

### 4 namespaces
| Namespace | Key pattern | TTL |
|-----------|------------|-----|
| Identity | `pan:{pan_token}` | 24h |
| Share tokens | `share:{token}` | per config |
| Vault completeness | `vault:{pan_token}` | 1h |
| JWT revocation | `revoked:{jti}` | session TTL |

### SSE pattern
```
Pipeline stage change → Kafka prana.pipeline.events
→ SSEFanoutConsumer → Redis Pub/Sub sse:doc:{document_id}
→ browser EventSource
```
NEVER poll YugabyteDB from SSE endpoint.

## No plaintext PAN/NIK in cache — only `pan_token` (HMAC output) as key
