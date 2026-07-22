@../../CLAUDE.md

# PRANA Workflows — Temporal Architecture

## Overview
59 named Temporal workflows replace ALL cron jobs, Celery tasks, and scheduled polling.
**Zero cron anywhere in the system.**

Reconciled 2026-07-05 against the actual `@workflow.defn` classes in this directory —
previous count (53) undercounted real workflows and double-counted
`BatchTimeoutMonitorWorkflow` across two domains. `prana-docs/PRANA_WorkflowArchitecture_v1.html`
is an early design doc that predates several renames (e.g. `DPDPErasureWorkflow` →
`ErasureConfirmationWorkflow`) and the removal of `ConsentWithdrawalWorkflow` from the
design (consent withdrawal is immediate — no grace period — so it never needed a durable
workflow; see `kafka/consumers/compliance_consumer.py`). **This file is the source of truth
for what's actually implemented — the HTML doc was not updated to match.**

## Infrastructure
| Property | Value |
|----------|-------|
| Engine | Temporal Python SDK v1.x (self-hosted on EKS) |
| Regions | Both ap-south-1 (Mumbai) + ap-south-2 (Hyderabad) — active-active |
| Task queues | One per service (see table below) |
| History limit | 50,000 events — use Continue-As-New before reaching this |
| Visibility | Temporal Web UI + OpenTelemetry traces |

## Task Queues (one per service)
```
ingestsvc-queue       → IngestService (DocumentPipelineWorkflow, BatchProgressWorkflow)
auth-queue            → AuthService (TOTPLockoutWorkflow, SessionExpiryWorkflow, SessionForceRevokeWorkflow)
vault-queue           → VaultService (ShareExpiryWorkflow, WatermarkWorkflow)
admin-queue           → AdminService (EmployeeExitWorkflow, PushWindowExpiryWorkflow, ElevationWorkflow)
analytics-queue       → AnalyticsService (VaultHealthWorkflow, DigestWorkflow)
insight-queue         → InsightService (InsightRefreshWorkflow, AnomalyAcknowledgementWorkflow)
secops-queue          → SecurityService (PolicyLockWorkflow, AnomalyDetectionWorkflow, KMSKeyRotationWorkflow, SystemHealthWorkflow, AuditIntegrityVerificationWorkflow, ErrorThresholdEvaluationWorkflow)
safety-queue          → SafetyService (CSAMReportingWorkflow)
resolution-queue      → ResolutionService (EmbeddingUpdateWorkflow)
resolution-low-priority-queue → ResolutionService (low-priority embedding updates — yields to pipeline)
compliance-queue      → ComplianceService (ErasureConfirmationWorkflow, ConsentRebumpWorkflow, DataExportWorkflow)
```

## The 5 Composable Patterns (ALL 53 workflows use one of these)

### Pattern 1 — Durable Timer
Sleep until a point in time or for a duration. Survives pod restarts and deploys.
```python
@workflow.defn
class ExampleTimerWorkflow:
    async def run(self, input: TimerInput) -> None:
        duration = timedelta(days=input.duration_days)  # from config, not hardcoded
        await workflow.sleep(duration)
        await workflow.execute_activity(
            service.act, input.payload,
            schedule_to_close_timeout=timedelta(minutes=10)
        )
```
**Used by:** EmployeeExitWorkflow, PushWindowExpiryWorkflow, TOTPLockoutWorkflow, SessionExpiryWorkflow, ShareExpiryWorkflow, ErasureConfirmationWorkflow

### Pattern 2 — Signal-Driven Timer (interruptible)
Timer that can be cancelled early by an external signal. Admin acts → signal fires → workflow exits cleanly. Timer expires → auto-action. Idempotency check: `reversed_by_event_id IS NULL`.
```python
@workflow.defn
class InterruptibleTimerWorkflow:
    def __init__(self): self._early_exit = False

    @workflow.signal
    async def cancel_early(self, reason: str) -> None:
        self._early_exit = True

    async def run(self, input: Input) -> None:
        await workflow.wait_condition(
            lambda: self._early_exit, timeout=input.duration_seconds
        )
        if self._early_exit:
            await workflow.execute_activity(on_early_exit, self._early_exit, ...)
        else:
            await workflow.execute_activity(on_timer_expiry, input.payload, ...)
```
**Used by:** PolicyLockWorkflow, ElevationWorkflow, ErasureConfirmationWorkflow, ShareRevocationWorkflow, OnboardingReviewSLAWorkflow

### Pattern 3 — Temporal Schedule (replaces cron)
Created once at service startup (idempotent). Cadence read from `platform_config` at creation time, updatable via Temporal API — no redeployment.

Corrected 2026-07-22: the previous version of this example was itself wrong in three
ways that got copy-pasted into `system_health.py`/`audit_integrity.py`/`error_threshold.py`/
`hrms_sync_schedule.py` and went undetected because none of their tests actually called
the function (source-inspection tests only) — `Schedule`/`ScheduleSpec`/
`ScheduleActionStartWorkflow`/etc. live in `temporalio.client`, not `temporalio.common`;
`ScheduleActionStartWorkflow` requires a non-empty `id=`; and `Schedule` has no
`with_spec()` method — `ScheduleHandle.update()` takes an
`updater(ScheduleUpdateInput) -> ScheduleUpdate` callable, not a `Schedule -> Schedule`
lambda. Verify against the installed `temporalio` SDK before copying this again.
```python
import dataclasses
from temporalio.client import (
    Schedule, ScheduleSpec, ScheduleIntervalSpec, ScheduleActionStartWorkflow, ScheduleUpdate,
)
from temporalio.service import RPCError

async def ensure_schedule(client: Client, config: ConfigService):
    interval = await config.get_int("platform_summary_interval_minutes")
    schedule_id = "platform-summary"
    new_spec = ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=interval))])
    try:
        handle = client.get_schedule_handle(schedule_id)
        await handle.describe()
        async def _updater(inp):
            return ScheduleUpdate(schedule=dataclasses.replace(inp.description.schedule, spec=new_spec))
        await handle.update(_updater)
    except RPCError:  # does not exist — create
        await client.create_schedule(schedule_id,
            Schedule(action=ScheduleActionStartWorkflow(
                         PlatformSummaryWorkflow.run, id=f"{schedule_id}-run", task_queue="analytics-queue"),
                     spec=new_spec)
        )
```
**Used by (documented — see NOTE on registration status below):** PlatformSummaryWorkflow, DigestWorkflow (weekly/monthly), KMSHealthCheckWorkflow, StorageQuotaCheckWorkflow, ClamAVUpdateWorkflow, RetentionWorkflow, SystemHealthWorkflow, AuditIntegrityVerificationWorkflow, ErrorThresholdEvaluationWorkflow

**NOTE (found 2026-07-22, NOT yet fixed):** only `SystemHealthWorkflow`, `AuditIntegrityVerificationWorkflow`, and `ErrorThresholdEvaluationWorkflow` actually have an `ensure_*_schedule()` call wired into `main.py`'s startup. `PlatformSummaryWorkflow`, `DigestWorkflow`, `KMSHealthCheckWorkflow`, `StorageQuotaCheckWorkflow`, `ClamAVUpdateWorkflow`, and `RetentionWorkflow` are registered on their task queues in `worker.py` (so a worker *can* run them) but have **no schedule-registration code anywhere** — `compliance.py`'s comment on `RetentionWorkflow` claims one is "created at startup by worker.py ensure_schedules()", but no such function exists in `worker.py`. None of these six ever fire automatically as things stand.

### Pattern 4 — Continue-As-New (perpetual)
For workflows that run forever without unbounded history. Restart with fresh state at `RENEW_THRESHOLD`.
```python
@workflow.defn
class PerpetualWorkflow:
    async def run(self, input: PerpetualInput) -> None:
        events_processed = input.events_processed_so_far
        while events_processed < RENEW_THRESHOLD:
            event = await workflow.execute_activity(consume_next_event, ...)
            await workflow.execute_activity(process_event, event, ...)
            events_processed += 1
        workflow.continue_as_new(PerpetualInput(
            events_processed_so_far=0, checkpoint=input.checkpoint
        ))
```
**Used by:** AnomalyDetectionWorkflow, KMSKeyRotationWorkflow, HMACSecretRotationWorkflow, RetentionWorkflow (7-year boundary)

### Pattern 5 — Human Signal (multi-actor)
Workflow waits indefinitely for a human decision. Optional SLA timeout triggers escalation.
```python
@workflow.defn
class HumanSignalWorkflow:
    def __init__(self): self._decision = None

    @workflow.signal
    async def approve(self, actor_id: str) -> None:
        self._decision = ("APPROVED", actor_id)

    @workflow.signal
    async def reject(self, actor_id: str, reason: str) -> None:
        self._decision = ("REJECTED", actor_id, reason)

    async def run(self, input: Input) -> None:
        await workflow.execute_activity(notify_approver, input, ...)
        decision_received = await workflow.wait_condition(
            lambda: self._decision is not None,
            timeout=timedelta(days=input.sla_days)
        )
        if not decision_received:
            await workflow.execute_activity(escalate_sla_breach, input, ...)
            return
        decision, actor = self._decision[:2]
        if decision == "APPROVED":
            await workflow.execute_activity(on_approved, input, ...)
```
**Used by:** ElevationWorkflow, StorageExpansionWorkflow, OnboardingReviewSLAWorkflow, TenantMigrationWorkflow

## Workflow Domains (59 total, verified against `@workflow.defn` classes 2026-07-05, +1 2026-07-15)

| Domain | Count | Key workflows |
|--------|-------|---------------|
| Document Pipeline | 4 | DocumentPipelineWorkflow, BatchProgressWorkflow, BatchTimeoutMonitorWorkflow, EmbeddingUpdateWorkflow |
| Employee Lifecycle | 7 | EmployeeExitWorkflow, PushWindowExpiryWorkflow, VaultActivationWorkflow, VaultHealthWorkflow, NomineeAccessWorkflow, RejoiningWorkflow, AccountDormancyWorkflow |
| Security & Access Control | 12 | PolicyLockWorkflow, TOTPLockoutWorkflow, ElevationWorkflow, SessionExpiryWorkflow, SessionForceRevokeWorkflow, AnomalyDetectionWorkflow, KMSKeyRotationWorkflow, HMACSecretRotationWorkflow, CSAMReportingWorkflow, SystemHealthWorkflow, AuditIntegrityVerificationWorkflow, ErrorThresholdEvaluationWorkflow |
| DPDP & Legal Compliance | 9 | ErasureConfirmationWorkflow, DataExportWorkflow, ConsentRebumpWorkflow, GrievanceWorkflow, DataCorrectionWorkflow, RetentionWorkflow, AuditArchivalWorkflow, LegalHoldWorkflow, StatutoryComplianceWorkflow |
| Intelligence Layer | 8 | InsightRefreshWorkflow, CareerInsightWorkflow, VaultCompletenessWorkflow, AnomalyAcknowledgementWorkflow, DigestWorkflow, PeerBenchmarkWorkflow, SkillGapWorkflow, MarketCompWorkflow |
| Platform Operations | 9 | PlatformSummaryWorkflow, ClamAVUpdateWorkflow, KMSHealthCheckWorkflow, StorageQuotaCheckWorkflow, StagingCleanupWorkflow, WebhookDeliveryWorkflow, NotificationDeliveryWorkflow, StorageExpansionWorkflow, OnboardingReviewSLAWorkflow |
| Onboarding & Tenant Management | 4 | DomainVerificationWorkflow, TenantProvisioningWorkflow, TenantOffboardingWorkflow, TenantMigrationWorkflow |
| Vault & Shares | 3 | ShareExpiryWorkflow, ShareRevocationWorkflow, DocumentShareWorkflow |
| Gamification & HRMS Integration | 3 | GamificationRefreshWorkflow (registered on `insight-queue`), HRMSSyncWorkflow + HRMSSyncScheduleWorkflow (registered on `hrms-queue`). Fixed 2026-07-09: previously none were registered, and `WorkflowConsumer` started `GamificationRefreshWorkflow` on `"prana-analytics"` — a queue no worker polled, so it silently never ran. Consumer now targets `insight-queue`. Fixed 2026-07-22: `HRMSSyncScheduleWorkflow`'s Temporal-Schedule creation (`hrms_sync_schedule.py`) was a placeholder dict, not a real `client.create_schedule(...)` call (same bug independently found in `audit_integrity.py`/`error_threshold.py`/`system_health.py`'s schedule registration — wrong import location, missing required `id=`, nonexistent `Schedule.with_spec()`); the manual `/sync` trigger was also starting `HRMSSyncWorkflow` on `"prana-analytics"` instead of `hrms-queue`. Both fixed, and `HRMSSyncScheduleWorkflow` is now actually triggered: `hrms_config.py`'s create/pause/resume endpoints publish `HRMS_CONNECTOR_STATUS_CHANGED`, and `IntegrationConsumer` starts it in response. |

Corrections from the previous (53-count) version of this table:
- `BatchTimeoutMonitorWorkflow` was listed under both Document Pipeline and Platform
  Operations — it only exists once, in `batch_progress.py`. Kept under Document Pipeline.
- `SystemHealthWorkflow` was duplicate-defined in `platform_ops.py` (stub activities,
  wired to `worker.py`) and `system_health.py` (real implementation, never registered).
  Consolidated to the `system_health.py` version, now correctly registered on
  `secops-queue` and moved to the Security & Access Control domain.
- `StatutoryComplianceWorkflow` (compliance.py) existed in code but wasn't in this table.
- `StorageExpansionWorkflow` and `OnboardingReviewSLAWorkflow` were named in the Pattern 5
  usage example below but never counted in any domain row.
- `GamificationRefreshWorkflow`, `HRMSSyncWorkflow`, `HRMSSyncScheduleWorkflow` existed in
  code but weren't in this table at all — built after this doc was last reconciled.
- `AuditIntegrityVerificationWorkflow` added 2026-07-15 (`workflows/audit_integrity.py`,
  Pattern 3, `secops-queue`) — periodically re-verifies recent `audit_event` rows against
  their Immudb dual-write. Companion to the `prana_app_role` DB-privilege split
  (`prana-db/migrations/039_audit_role_revoke.sql`): the REVOKE stops the app from
  mutating audit history, this workflow is what makes tampering by anyone else with DB
  access actually get noticed. See `KAFKA_REDIS_ARCHITECTURE.md` §8.
- `ErrorThresholdEvaluationWorkflow` added 2026-07-15 (`workflows/error_threshold.py`,
  Pattern 3, `secops-queue`) — the 4th incident track (application error observability,
  `prana-docs/ERROR_OBSERVABILITY_DESIGN.md`). Scans open `error_event` rows every
  `error_threshold_check_interval_minutes` and promotes qualifying ones to real
  `incident` rows via `services/error_threshold_service.py`'s classification rules
  (security/crypto paths → P1 on first occurrence, compliance paths → P2 after 3
  occurrences in 10 minutes, novel bugs → P2 on first occurrence, noisy recurrence →
  P3 after 10 occurrences in 15 minutes).
- `PolicyLockWorkflow`'s `apply_policy_lock`/`release_policy_lock`/`notify_policy_lock`
  activities were bare stubs until 2026-07-16 — fixed alongside `get_security_config`
  (also a stub; every workflow in `workflows/security.py` that reads a duration from
  config depended on it). Now has a real trigger: `SecurityConsumer._maybe_auto_lock`
  starts this workflow off a `BULK_DOC_ACCESS`/`BRUTE_FORCE` anomaly, gated behind
  `bulk_access_auto_lock_enabled`/`brute_force_auto_lock_enabled` (both seeded `false`).
  See `KAFKA_REDIS_ARCHITECTURE.md` §10 and `prana-docs/SEVERITY_SLA_POLICY_DESIGN.md`.

## Configuration Model (critical rule)
Every duration and schedule is read at workflow **trigger time** from `get_config(key, tenant_id)`.
- `tenant_config` overrides `platform_config` (resolution order: tenant first, platform fallback)
- Config changes apply to **new workflow instances only** — never retroactively to in-progress workflows
- Never hardcode durations. Always:
```python
duration_minutes = await config_svc.get_int("totp_lockout_cooldown_minutes", tenant_id)
await workflow.sleep(timedelta(minutes=duration_minutes))
```

## Key Config Keys
| Key | Default | Used by |
|-----|---------|---------|
| `totp_lockout_cooldown_minutes` | 30 | TOTPLockoutWorkflow |
| `dpdp_erasure_confirmation_days` | 30 | ErasureConfirmationWorkflow |
| `retention_years_default` | 7 | RetentionWorkflow |
| `exception_sla_p50_hours` | 4 | DocumentPipelineWorkflow exception path |
| `exception_sla_p95_hours` | 24 | PA escalation |
| `share_otp_ttl_minutes` | 10 | ShareExpiryWorkflow |
| `domain_verification_poll_minutes` | 15 | DomainVerificationWorkflow |
| `domain_verification_max_hours` | 48 | DomainVerificationWorkflow |
| `consent_rebump_window_days` | 30 | ConsentRebumpWorkflow |
| `nominee_access_window_days` | 90 | NomineeAccessWorkflow |
| `platform_summary_interval_minutes` | 5 | PlatformSummaryWorkflow schedule |
| `audit_integrity_check_interval_minutes` | 60 | AuditIntegrityVerificationWorkflow schedule |
| `error_threshold_check_interval_minutes` | 15 | ErrorThresholdEvaluationWorkflow schedule |

## Engine Independence Rule
Business logic lives in plain service classes (zero Temporal imports). Temporal workflows are thin shells that call service methods. This means:
- Workflows can be unit-tested without a Temporal cluster (mock `workflow.execute_activity`)
- Service methods can be called directly from REST endpoints, CLI, or integration tests
- Migrating orchestrators requires rewriting only the thin `@workflow.defn` shell

**Pattern to follow:**
```
services/account_lock.py   ← business logic, zero Temporal imports
workflows/totp_lockout.py  ← @workflow.defn shell, calls service via execute_activity
```

## DocumentPipelineWorkflow — 6 Stages in Detail
The core pipeline (owner: IngestService, queue: `ingestsvc-queue`):
1. **Batch Ingestion** — Write `document` row, generate staging S3 key
2. **Encryption Boundary** — OCR if needed → extract NIK → `pan_token = HMAC-SHA256(NIK, platform_secret)` → `enc_pan = FF3-1(NIK, emp_DEK)` → zero NIK from memory → redact NIK in text
3. **Safety Scan** — ClamAV virus + NSFW + CSAM PhotoDNA. CSAM → `CSAMReportingWorkflow` + legal_hold
4. **LLM Extraction** — `Qwen/Qwen2.5-14B-Instruct` (via `prana-ai/llm_client.py`'s OpenAI-compatible `LLMClient`) with schema-specific prompt → `extracted_fields` JSONB. Confidence < 0.60 → exception
5. **Identity Resolution** — 4-level ladder: pan_token exact → employee_id exact → name+DOJ fuzzy → embedding cosine. Unresolved → wait up to 7 days for `exception_resolved` signal from OA-Admin
6. **Tag & Route** — Write immutable metadata tag, move S3 staging→permanent, `pipeline_status=ROUTED`, trigger VaultHealthWorkflow, publish DOC_ROUTED to Kafka
