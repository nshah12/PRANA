# PRANA Temporal Workflow Rules
# Auto-loaded when editing prana-api/workflows/**
# ENFORCEMENT: scripts/enforce_rules.py — TEMPORAL-01 (workflow.run must stay under 20 lines)
# Run /enforce before any PR merge. Violations block deployment.

## Core pattern — ALWAYS follow, no exceptions

```python
# ✅ Business logic in plain service class — ZERO Temporal imports
class DocumentResolutionService:
    async def resolve(self, document_id: str, employee_uuid: str):
        ...  # writes to DB, pure Python, testable without Temporal

# ✅ Temporal workflow = thin adapter shell ONLY (<20 lines)
@workflow.defn
class DocumentResolutionWorkflow:
    @workflow.run
    async def run(self, input: ResolutionInput) -> ResolutionResult:
        return await workflow.execute_activity(
            DocumentResolutionService.resolve,
            input,
            start_to_close_timeout=timedelta(minutes=5),
        )
```

**Never put business logic inside `@workflow.run` directly.**
**Never import Temporal inside service classes.**

## 53 workflows across 8 domains
Reference: `prana-docs/PRANA_WorkflowArchitecture_v1.html`
Read this file before adding any new workflow — it may already exist.

## Task queues
| Queue | Workers | Purpose |
|-------|---------|---------|
| `prana-ingest` | prana-api | Document ingestion |
| `prana-pipeline` | prana-ai | AI pipeline stages |
| `prana-compliance` | prana-api | DPDP erasure, consent |
| `prana-admin` | prana-api | Elevation, lock/unlock |
| `prana-analytics` | prana-api | Vault health, digests |

## Temporal + Kafka relationship
- **Kafka** = async fan-out event bus (fire and forget, multiple consumers)
- **Temporal** = durable process (retries, signals, timers, human-in-the-loop)
- **WorkflowConsumer** bridges them: consumes Kafka event → starts Temporal workflow

## Signals (direct, allowed in HTTP handlers)
These are the ONLY Temporal calls allowed in HTTP path:
- `exception_resolved` signal → running ExceptionResolutionWorkflow
- `elevation_approved` signal → running ElevationWorkflow
All other workflow starts go through WorkflowConsumer.

## Workflow rules
- Zero cron jobs, zero Celery, zero polling — all scheduled work via Temporal timers
- All durations from `platform_config` / `tenant_config` — never hardcoded in workflow
- Workflow ID must be deterministic: `f"{workflow_name}-{entity_id}"` — enables dedup
- Always set `start_to_close_timeout` on every activity — never let activities hang forever
- Idempotency: workflows must be safe to replay — no side effects on replay
