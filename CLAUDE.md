# PRANA Platform — Root Context

## What is PRANA
PRANA is a career document vault for Indian workers. Employers push documents (salary slips, Form 16, offer letters) via a Portal or HRMS API. Employees access their documents via a mobile app. Documents are processed through a 6-stage AI pipeline that extracts insights — raw salary figures are never stored or surfaced in UI.

## Monorepo Structure
```
prana-mobile/   — React Native / Expo SDK 56 mobile app
prana-api/      — Python backend: FastAPI REST endpoints + Temporal workflow shells
prana-portal/   — React.js (Vite + React Router) employer web app
prana-db/       — Database: schema.sql (19 tables), migrations/, seeds/
prana-ai/       — AI pipeline: extraction, resolution, insights (GPU worker, not API pods)
prana-ask/      — Ask PRANA chatbot: standalone RAG agent over local LLM
prana-docs/     — Architecture reference documents (read before coding)
```

**Deployment boundary:** `prana-api`, `prana-ai`, and `prana-ask` are three separate deployable services.
- `prana-api` — CPU, handles REST + Temporal
- `prana-ai` — GPU worker, runs LLM extraction pipeline (Stages 03–05)
- `prana-ask` — GPU worker, serves the employee chatbot

## Architecture Documents (read before coding)
All in `prana-docs/`:
- `PRANA_UserMgmt_DataArchitecture_v25.html` — 19 DB tables, YugabyteDB DDL, identity model, auth flows
- `PRANA_Portal_v52.html` — Portal architecture, platform/tenant config, 9 workflow service owners
- `PRANA_WorkflowArchitecture_v1.html` — 53 Temporal workflows across 8 domains
- `PRANA_AI_Pipeline_Plan_v2.html` — 6-stage AI pipeline, NIK model, encryption architecture
- `KAFKA_REDIS_ARCHITECTURE.md` — **DECIDED. Read before touching any ingest/pipeline/audit code.** Kafka topics, event schemas, consumer responsibilities, Redis namespaces, HTTP handler contract

## Privacy Contract (NEVER violate)
- LLM receives full document data for extraction → produces **insights only**
- Raw figures (₹ salary, PAN) are **never stored** in DB, never surfaced in mobile UI
- Password-protected docs: user provides password in time-limited session (10 min), processed in-memory, nothing persisted, session wiped on expiry
- Output contract: **LLM input = full data. LLM output = insights only. Always.**

## Encryption Model
- `pan_token` = HMAC-SHA256(PAN, platform_secret) — cross-tenant deduplication key
- `enc_pan` = FF3-1 Format-Preserving Encryption(PAN, employee_DEK)
- `enc_dek` = KMS_Encrypt(DEK, tenant_KEK) — envelope encryption
- `totp_secret_enc` = AES-256-GCM
- Passwords = Argon2id (time=2, memory=65536, parallelism=2)
- AWS KMS (ap-south-1, customer-managed) for platform_secret and tenant KEKs

## Database
- YugabyteDB (PostgreSQL-compatible distributed SQL)
- Dual-region: ap-south-1 (Mumbai) + ap-south-2 (Hyderabad)
- Schema: `prana-db/schema.sql` — 26 tables across 11 layers
- Migrations: `prana-db/migrations/`

## Event Streaming — Apache Kafka (DECIDED, NOT optional)
- **AWS MSK · KRaft mode · Both regions · MirrorMaker 2 bidirectional sync**
- Dev: `confluentinc/cp-kafka:7.6.1` container on `localhost:9092`
- **5 topics** (12 partitions each): `prana.ingest.events`, `prana.pipeline.events`, `prana.audit.events`, `prana.notifications`, `prana.analytics.events`
- **HTTP handler contract:** validate → S3 put → 1 DB write → 1 Kafka publish → return 202. No audit writes, no workflow starts, no notifications in HTTP path.
- **5 consumers** in `prana-api/kafka/consumers/`: `AuditConsumer`, `WorkflowConsumer`, `SSEFanoutConsumer`, `NotifConsumer`, `AnalyticsConsumer`
- Full reference: `prana-docs/KAFKA_REDIS_ARCHITECTURE.md`

## Cache — Redis Enterprise (DECIDED, NOT optional)
- **ElastiCache Global Datastore · CRDT active-active · Both regions · sub-10ms cross-region sync**
- Dev: `redis:7.2-alpine` container on `localhost:6379`
- **4 cache namespaces:** identity (`pan_token`), share tokens, vault completeness, JWT revocation
- **SSE pattern:** pipeline stage changes → Kafka → `SSEFanoutConsumer` → Redis Pub/Sub `sse:doc:{document_id}` → browser. Never poll YugabyteDB from SSE endpoint.
- No plaintext PAN/NIK ever cached — only `pan_token` (HMAC output) as cache key

## Workflow Engine
- Temporal Python SDK v1.x
- 53 named workflows, zero cron/Celery/polling
- Business logic in plain service classes (zero Temporal imports)
- Temporal workflows are thin adapter shells (<20 lines)
- **Temporal + Kafka are complementary:** Kafka = async fan-out event bus; Temporal = durable process with signals, timers, human-in-the-loop. WorkflowConsumer bridges them.

## AI / LLM Stack
- **Inference:** Local LLM via OpenAI-compatible API (HuggingFace hosted now → Ollama/vLLM local later)
- **Extraction model:** `Qwen/Qwen2.5-14B-Instruct` — best structured JSON output for Indian documents
- **Insights / RAG model:** `meta-llama/Llama-3.1-8B-Instruct`
- **Embeddings:** `BAAI/bge-m3` — multilingual, handles Hindi+English Indian HR docs
- **OCR:** Tesseract (local) → AWS Textract (fallback)
- All LLM calls through `prana-ai/llm_client.py` — single `LLMClient` wrapper

## Sub-project CLAUDE.md files
- `prana-mobile/CLAUDE.md` — Expo SDK 56, routing, theme tokens, privacy UI rules, EAS build
- `prana-api/CLAUDE.md` — FastAPI, 9 services, Temporal adapter pattern, DB rules, encryption
- `prana-api/workflows/CLAUDE.md` — 53 workflows, 5 patterns, task queues, config model
- `prana-portal/CLAUDE.md` — React.js portal, roles & screen access, OA flows, CISO dashboard
- `prana-db/CLAUDE.md` — schema ownership, migration rules, YugabyteDB specifics
- `prana-ai/CLAUDE.md` — extraction pipeline, resolution ladder, benchmark service
- `prana-ask/CLAUDE.md` — chatbot architecture, RAG pattern, privacy guard

## Compliance
- DPDP Act 2023: consent, erasure, export, correction, grievance workflows
- 7-year audit log retention (hot in YugabyteDB, cold in Apache Iceberg on S3)
