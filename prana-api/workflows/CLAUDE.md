@../../CLAUDE.md

# PRANA Workflows — Temporal Architecture

## Overview
53 named Temporal workflows replace ALL cron jobs, Celery tasks, and scheduled polling.
**Zero cron anywhere in the system.**

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
auth-queue            → AuthService (TOTPLockoutWorkflow, PolicyLockWorkflow, SessionExpiryWorkflow)
vault-queue           → VaultService (ShareExpiryWorkflow, WatermarkWorkflow)
admin-queue           → AdminService (EmployeeExitWorkflow, PushWindowExpiryWorkflow, ElevationWorkflow)
analytics-queue       → AnalyticsService (VaultHealthWorkflow, DigestWorkflow)
insight-queue         → InsightService (InsightRefreshWorkflow, AnomalyAcknowledgementWorkflow)
secops-queue          → SecurityService (AnomalyDetectionWorkflow, KMSKeyRotationWorkflow)
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
```python
async def ensure_schedule(client: Client, config: ConfigService):
    interval = await config.get_int("platform_summary_interval_minutes")
    handle = client.get_schedule_handle("platform-summary")
    try:
        await handle.describe()
        await handle.update(lambda s: s.with_spec(
            ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=interval))])
        ))
    except RPCError:  # does not exist — create
        await client.create_schedule("platform-summary",
            Schedule(action=ScheduleAction(workflow=PlatformSummaryWorkflow),
                     spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=interval))]))
        )
```
**Used by:** PlatformSummaryWorkflow, DigestWorkflow (weekly/monthly), KMSHealthCheckWorkflow, StorageQuotaCheckWorkflow, ClamAVUpdateWorkflow, RetentionWorkflow

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

## Workflow Domains (53 total)

| Domain | Count | Key workflows |
|--------|-------|---------------|
| Document Pipeline | 4 | DocumentPipelineWorkflow, BatchProgressWorkflow, BatchTimeoutMonitorWorkflow, EmbeddingUpdateWorkflow |
| Employee Lifecycle | 7 | EmployeeExitWorkflow, PushWindowExpiryWorkflow, VaultActivationWorkflow, VaultHealthWorkflow, NomineeAccessWorkflow, RejoiningWorkflow, AccountDormancyWorkflow |
| Security & Access Control | 9 | PolicyLockWorkflow, TOTPLockoutWorkflow, ElevationWorkflow, SessionExpiryWorkflow, SessionForceRevokeWorkflow, AnomalyDetectionWorkflow, KMSKeyRotationWorkflow, HMACSecretRotationWorkflow, CSAMReportingWorkflow |
| DPDP & Legal Compliance | 8 | ErasureConfirmationWorkflow, DataExportWorkflow, ConsentRebumpWorkflow, GrievanceWorkflow, DataCorrectionWorkflow, RetentionWorkflow, AuditArchivalWorkflow, LegalHoldWorkflow |
| Intelligence Layer | 8 | InsightRefreshWorkflow, CareerInsightWorkflow, VaultCompletenessWorkflow, AnomalyAcknowledgementWorkflow, DigestWorkflow, PeerBenchmarkWorkflow, SkillGapWorkflow, MarketCompWorkflow |
| Platform Operations | 9 | PlatformSummaryWorkflow, ClamAVUpdateWorkflow, KMSHealthCheckWorkflow, StorageQuotaCheckWorkflow, StagingCleanupWorkflow, BatchTimeoutMonitorWorkflow, WebhookDeliveryWorkflow, NotificationDeliveryWorkflow, SystemHealthWorkflow |
| Onboarding & Tenant Management | 4 | DomainVerificationWorkflow, TenantProvisioningWorkflow, TenantOffboardingWorkflow, TenantMigrationWorkflow |
| Vault & Shares | 3 | ShareExpiryWorkflow, ShareRevocationWorkflow, DocumentShareWorkflow |

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
4. **LLM Extraction** — Bedrock Claude Sonnet (ap-south-1) with schema-specific prompt → `extracted_fields` JSONB. Confidence < 0.60 → exception
5. **Identity Resolution** — 4-level ladder: pan_token exact → employee_id exact → name+DOJ fuzzy → embedding cosine. Unresolved → wait up to 7 days for `exception_resolved` signal from OA-Admin
6. **Tag & Route** — Write immutable metadata tag, move S3 staging→permanent, `pipeline_status=ROUTED`, trigger VaultHealthWorkflow, publish DOC_ROUTED to Kafka
