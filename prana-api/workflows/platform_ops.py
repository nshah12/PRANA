"""
Platform operations workflows — thin Temporal shells.
Business logic lives in services/platform_ops_service.py.

NOT split into one-file-per-workflow (2026-08-10 review) — same investigation
and same decision as workflows/compliance.py (see that file's docstring for
the full reasoning). This file has the same shape of problem: main.py has 5
separate lazy `from workflows.platform_ops import ensure_*_schedule` calls at
distinct startup points, plus worker.py bulk imports and ~8 test files
importing workflow classes bundled with schedule helpers. Scoped out for the
same reason — real risk of a silent schedule-registration regression, not
worth rushing without a live Temporal cluster to verify against.

Task queue: secops-queue (KMSHealthCheck), ingestsvc-queue (StagingCleanup, ClamAV),
            analytics-queue (StorageQuota), admin-queue (WebhookDelivery, StorageExpansion, OnboardingReviewSLA)

Workflows (8 — BatchTimeoutMonitorWorkflow is in batch_progress.py):
  PlatformSummaryWorkflow    — aggregate platform health metrics every N minutes
  ClamAVUpdateWorkflow       — pull latest ClamAV signatures on a schedule
  KMSHealthCheckWorkflow     — verify all KMS key ARNs are accessible and active
  StorageQuotaCheckWorkflow  — alert when any tenant approaches S3 storage quota
  StagingCleanupWorkflow     — purge abandoned staging S3 objects older than N days
  WebhookDeliveryWorkflow    — durable delivery with retries for HRMS webhooks
  StorageExpansionWorkflow   — human-signal approval flow for tenant storage bumps
  OnboardingReviewSLAWorkflow — SLA-timed escalation for pending tenant reviews

NotificationDeliveryWorkflow removed 2026-08-10 (dead code, see below). Not
listed here: SystemHealthWorkflow — despite appearing in an older version of
this list, it has never actually lived in this file; the real implementation
is workflows/system_health.py (see the comment further down where its stub
duplicate used to be).
"""
from datetime import timedelta

from temporalio import workflow, activity
from temporalio.common import RetryPolicy

_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=10),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
)


# ── Activities (implementations in services/platform_ops_service.py) ────────

async def _connect():
    import asyncpg

    from config import get_settings

    settings = get_settings()
    return await asyncpg.connect(settings.db_dsn)


@activity.defn(name="collect_platform_metrics")
async def collect_platform_metrics(params: dict) -> dict:
    from services.platform_ops_service import PlatformOpsService

    db = await _connect()
    try:
        return await PlatformOpsService(db).collect_platform_metrics()
    finally:
        await db.close()

@activity.defn(name="write_platform_summary")
async def write_platform_summary(params: dict) -> None:
    from services.platform_ops_service import PlatformOpsService

    db = await _connect()
    try:
        await PlatformOpsService(db).write_platform_summary(params.get("rows", []))
    finally:
        await db.close()

@activity.defn(name="pull_clamav_signatures")
async def pull_clamav_signatures(params: dict) -> dict:
    from services.platform_ops_service import PlatformOpsService

    db = await _connect()
    try:
        return await PlatformOpsService(db).pull_clamav_signatures()
    finally:
        await db.close()

@activity.defn(name="verify_kms_key_health")
async def verify_kms_key_health(params: dict) -> dict:
    from config import get_settings
    from services.encryption_service import KMSService
    from services.platform_ops_service import PlatformOpsService

    settings = get_settings()
    db = await _connect()
    try:
        kms = KMSService(
            region=settings.aws_region,
            access_key_id=settings.aws_access_key_id,
            secret_access_key=settings.aws_secret_access_key,
        )
        return await PlatformOpsService(db, kms_client=kms.raw_client).verify_kms_key_health()
    finally:
        await db.close()

@activity.defn(name="alert_kms_key_issue")
async def alert_kms_key_issue(params: dict) -> None:
    from kafka.producer import get_kafka_producer
    from services.platform_ops_service import PlatformOpsService

    db = await _connect()
    try:
        kafka = await get_kafka_producer()
        await PlatformOpsService(db, kafka=kafka).alert_kms_key_issue(params.get("failures", []))
    finally:
        await db.close()

@activity.defn(name="check_tenant_storage_quotas")
async def check_tenant_storage_quotas(params: dict) -> list:
    from services.platform_ops_service import PlatformOpsService

    db = await _connect()
    try:
        return await PlatformOpsService(db).check_tenant_storage_quotas()
    finally:
        await db.close()

@activity.defn(name="alert_storage_quota")
async def alert_storage_quota(params: dict) -> None:
    from kafka.producer import get_kafka_producer
    from services.platform_ops_service import PlatformOpsService

    db = await _connect()
    try:
        kafka = await get_kafka_producer()
        await PlatformOpsService(db, kafka=kafka).alert_storage_quota(params)
    finally:
        await db.close()

@activity.defn(name="purge_stale_staging_objects")
async def purge_stale_staging_objects(params: dict) -> dict:
    from config import get_settings
    from services.platform_ops_service import PlatformOpsService
    from services.s3_service import S3Service

    settings = get_settings()
    db = await _connect()
    try:
        s3 = S3Service(settings)
        return await PlatformOpsService(db, s3_client=s3.raw_client).purge_stale_staging_objects(
            staging_bucket=settings.s3_bucket_staging,
            older_than_days=int(params.get("older_than_days", 7)),
        )
    finally:
        await db.close()

@activity.defn(name="deliver_webhook")
async def deliver_webhook(params: dict) -> dict:
    from services.platform_ops_service import PlatformOpsService

    db = await _connect()
    try:
        return await PlatformOpsService(db).deliver_webhook(
            delivery_id=params["delivery_id"], tenant_id=params.get("tenant_id"),
            webhook_url=params["webhook_url"], event_type=params["event_type"],
            payload=params.get("payload", {}),
        )
    finally:
        await db.close()

@activity.defn(name="mark_webhook_failed")
async def mark_webhook_failed(params: dict) -> None:
    from services.platform_ops_service import PlatformOpsService

    db = await _connect()
    try:
        await PlatformOpsService(db).mark_webhook_failed(params["delivery_id"])
    finally:
        await db.close()

@activity.defn(name="get_ops_config")
async def get_ops_config(params: dict) -> str:
    import redis.asyncio as redis_async

    from config import get_settings
    from services.config_service import ConfigService

    settings = get_settings()
    db = await _connect()
    rdb = redis_async.from_url(settings.redis_url)
    try:
        value = await ConfigService(db, rdb).get(params["key"], params.get("tenant_id"))
        return value if value is not None else params.get("default", "")
    finally:
        await db.close()
        await rdb.aclose()


# ── PlatformSummaryWorkflow (Pattern 3 — Temporal Schedule) ──────────────────

@workflow.defn(name="PlatformSummaryWorkflow")
class PlatformSummaryWorkflow:
    """
    Aggregates platform health metrics (pipeline queue depth, exception count,
    active tenants, Kafka consumer lag) every N minutes (default: 5).
    Created as a Temporal Schedule at worker startup.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        metrics = await workflow.execute_activity(
            collect_platform_metrics, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            write_platform_summary, {**params, **metrics},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )


async def ensure_platform_summary_schedule(client, interval_minutes: int = 5) -> None:
    """Called at prana-api startup to register the Temporal Schedule (idempotent)."""
    import dataclasses

    from temporalio.client import (
        ScheduleHandle, Schedule, ScheduleSpec, ScheduleIntervalSpec,
        ScheduleActionStartWorkflow, ScheduleUpdate,
    )
    from temporalio.service import RPCError

    schedule_id = "platform-summary"
    new_spec = ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=interval_minutes))])
    try:
        handle: ScheduleHandle = client.get_schedule_handle(schedule_id)
        await handle.describe()
        async def _updater(inp):
            return ScheduleUpdate(schedule=dataclasses.replace(inp.description.schedule, spec=new_spec))
        await handle.update(_updater)
    except RPCError:
        await client.create_schedule(
            schedule_id,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    PlatformSummaryWorkflow.run, {}, id=f"{schedule_id}-run", task_queue="analytics-queue",
                ),
                spec=new_spec,
            ),
        )


# ── ClamAVUpdateWorkflow (Pattern 3 — Temporal Schedule) ─────────────────────

@workflow.defn(name="ClamAVUpdateWorkflow")
class ClamAVUpdateWorkflow:
    """
    Pulls fresh ClamAV virus + NSFW signature databases on a schedule
    (cadence from platform_config.clamav_update_interval_minutes, default 120).
    Restarts the scanner worker after successful update.
    Critical: must complete before any new documents reach stage 03.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        await workflow.execute_activity(
            pull_clamav_signatures, params,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )


async def ensure_clamav_update_schedule(client, interval_minutes: int = 120) -> None:
    """Called at prana-api startup to register the Temporal Schedule (idempotent)."""
    import dataclasses

    from temporalio.client import (
        ScheduleHandle, Schedule, ScheduleSpec, ScheduleIntervalSpec,
        ScheduleActionStartWorkflow, ScheduleUpdate,
    )
    from temporalio.service import RPCError

    schedule_id = "clamav-update"
    new_spec = ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=interval_minutes))])
    try:
        handle: ScheduleHandle = client.get_schedule_handle(schedule_id)
        await handle.describe()
        async def _updater(inp):
            return ScheduleUpdate(schedule=dataclasses.replace(inp.description.schedule, spec=new_spec))
        await handle.update(_updater)
    except RPCError:
        await client.create_schedule(
            schedule_id,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    ClamAVUpdateWorkflow.run, {}, id=f"{schedule_id}-run", task_queue="ingestsvc-queue",
                ),
                spec=new_spec,
            ),
        )


# ── KMSHealthCheckWorkflow (Pattern 3 — Temporal Schedule) ───────────────────

@workflow.defn(name="KMSHealthCheckWorkflow")
class KMSHealthCheckWorkflow:
    """
    Verifies all KMS key ARNs (platform + tenant KEKs) are accessible and enabled.
    Alerts Platform Admin immediately on any failure.
    Runs daily (cadence from platform_config.kms_health_check_cron, default 02:00 IST).
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        result = await workflow.execute_activity(
            verify_kms_key_health, params,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )
        if not result.get("all_healthy"):
            await workflow.execute_activity(
                alert_kms_key_issue, {**params, **result},
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_RETRY,
            )


async def ensure_kms_health_check_schedule(client, cron_expression: str = "0 2 * * *") -> None:
    """Called at prana-api startup to register the Temporal Schedule (idempotent)."""
    import dataclasses

    from temporalio.client import (
        ScheduleHandle, Schedule, ScheduleSpec, ScheduleActionStartWorkflow, ScheduleUpdate,
    )
    from temporalio.service import RPCError

    schedule_id = "kms-health-check"
    new_spec = ScheduleSpec(cron_expressions=[cron_expression], time_zone_name="Asia/Kolkata")
    try:
        handle: ScheduleHandle = client.get_schedule_handle(schedule_id)
        await handle.describe()
        async def _updater(inp):
            return ScheduleUpdate(schedule=dataclasses.replace(inp.description.schedule, spec=new_spec))
        await handle.update(_updater)
    except RPCError:
        await client.create_schedule(
            schedule_id,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    KMSHealthCheckWorkflow.run, {}, id=f"{schedule_id}-run", task_queue="secops-queue",
                ),
                spec=new_spec,
            ),
        )


# ── StorageQuotaCheckWorkflow (Pattern 3 — Temporal Schedule) ────────────────

@workflow.defn(name="StorageQuotaCheckWorkflow")
class StorageQuotaCheckWorkflow:
    """
    Checks S3 storage usage per tenant against their quota limit.
    Alerts CHRO + Platform Admin when any tenant reaches 80% / 95% thresholds.
    Runs daily; thresholds from tenant_config.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        tenants_over = await workflow.execute_activity(
            check_tenant_storage_quotas, params,
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=_RETRY,
        )
        for tenant in tenants_over:
            await workflow.execute_activity(
                alert_storage_quota, tenant,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_RETRY,
            )


async def ensure_storage_quota_check_schedule(client, cron_expression: str = "0 1 * * *") -> None:
    """Called at prana-api startup to register the Temporal Schedule (idempotent)."""
    import dataclasses

    from temporalio.client import (
        ScheduleHandle, Schedule, ScheduleSpec, ScheduleActionStartWorkflow, ScheduleUpdate,
    )
    from temporalio.service import RPCError

    schedule_id = "storage-quota-check"
    new_spec = ScheduleSpec(cron_expressions=[cron_expression], time_zone_name="Asia/Kolkata")
    try:
        handle: ScheduleHandle = client.get_schedule_handle(schedule_id)
        await handle.describe()
        async def _updater(inp):
            return ScheduleUpdate(schedule=dataclasses.replace(inp.description.schedule, spec=new_spec))
        await handle.update(_updater)
    except RPCError:
        await client.create_schedule(
            schedule_id,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    StorageQuotaCheckWorkflow.run, {}, id=f"{schedule_id}-run", task_queue="analytics-queue",
                ),
                spec=new_spec,
            ),
        )


# ── StagingCleanupWorkflow (Pattern 3 — Temporal Schedule) ───────────────────

@workflow.defn(name="StagingCleanupWorkflow")
class StagingCleanupWorkflow:
    """
    Purges abandoned staging S3 objects (pipeline failed / timed out) older than
    staging_cleanup_days (default: 7). Runs daily. Prevents staging bucket bloat.
    """

    @workflow.run
    async def run(self, params: dict) -> dict:
        days_str = await workflow.execute_activity(
            get_ops_config,
            {"key": "staging_cleanup_days", "default": "7"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        result = await workflow.execute_activity(
            purge_stale_staging_objects, {**params, "older_than_days": int(days_str)},
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=_RETRY,
        )
        return result


async def ensure_staging_cleanup_schedule(client, cron_expression: str = "0 4 * * *") -> None:
    """Called at prana-api startup to register the Temporal Schedule (idempotent)."""
    import dataclasses

    from temporalio.client import (
        ScheduleHandle, Schedule, ScheduleSpec, ScheduleActionStartWorkflow, ScheduleUpdate,
    )
    from temporalio.service import RPCError

    schedule_id = "staging-cleanup"
    new_spec = ScheduleSpec(cron_expressions=[cron_expression], time_zone_name="Asia/Kolkata")
    try:
        handle: ScheduleHandle = client.get_schedule_handle(schedule_id)
        await handle.describe()
        async def _updater(inp):
            return ScheduleUpdate(schedule=dataclasses.replace(inp.description.schedule, spec=new_spec))
        await handle.update(_updater)
    except RPCError:
        await client.create_schedule(
            schedule_id,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    StagingCleanupWorkflow.run, {}, id=f"{schedule_id}-run", task_queue="ingestsvc-queue",
                ),
                spec=new_spec,
            ),
        )


# ── WebhookDeliveryWorkflow (Pattern 1 — durable delivery) ───────────────────

@workflow.defn(name="WebhookDeliveryWorkflow")
class WebhookDeliveryWorkflow:
    """
    Durable delivery of a webhook event to an HRMS endpoint.
    Retries up to webhook_max_retries (default: 10) with exponential backoff.
    On final failure: marks webhook as failed in webhook_delivery_log.

    Intentionally built ahead of its trigger: `hrms_connector_config.integration_mode`
    already supports 'WEBHOOK' as a connector mode (schema.sql), but no caller anywhere
    in the codebase currently extracts a tenant's registered webhook_url from
    `enc_credentials` and starts this workflow — that wiring is a distinct, unscoped
    feature (decrypt WEBHOOK-mode credentials, decide the firing event, e.g. DOC_ROUTED),
    not a bug in this workflow. `deliver_webhook`/`mark_webhook_failed` below are
    real, tested, ready-to-use activities for whoever builds that trigger. Do not
    confuse this with `kafka/consumers/integration_consumer.py`'s HRMS_WEBHOOK_FAILED
    handling — that's unrelated: it tracks ingest-rejection retry counts in
    `api_ingest_log` (a real table, despite an earlier docstring here claiming
    otherwise), not HRMS webhook delivery.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        max_retries_str = await workflow.execute_activity(
            get_ops_config,
            {"key": "webhook_max_retries", "default": "10"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        result = await workflow.execute_activity(
            deliver_webhook, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=int(max_retries_str)),
        )
        if not result.get("success"):
            await workflow.execute_activity(
                mark_webhook_failed, params,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_RETRY,
            )


# NotificationDeliveryWorkflow removed 2026-08-10 — was fully built but nothing ever
# called start_workflow for it (dead code, same class of bug as the already-removed
# VaultCompletenessWorkflow). Real notification delivery already happens via
# CommunicationHubConsumer's per-channel consumers (email/sms/push/whatsapp/bell/ivr),
# each with its own vendor-chain + circuit breaker — this workflow's primary/fallback
# retry logic duplicated that, through a parallel path nothing triggered. See
# workflows/CLAUDE.md's Corrections section.


# SystemHealthWorkflow lives in workflows/system_health.py — this was a duplicate
# stub (unimplemented activities) that was accidentally the one wired into
# worker.py's admin-queue while the real implementation sat unregistered.
# See workflows/system_health.py for the real workflow + activity.


# ── StorageExpansionWorkflow (Pattern 5 — Human Signal) ──────────────────────

@activity.defn(name="notify_storage_expansion_request")
async def notify_storage_expansion_request(params: dict) -> str:
    from kafka.producer import get_kafka_producer
    from services.platform_ops_service import PlatformOpsService

    db = await _connect()
    try:
        kafka = await get_kafka_producer()
        return await PlatformOpsService(db, kafka=kafka).notify_storage_expansion_request(
            tenant_id=params["tenant_id"], current_gb=params["current_gb"],
            requested_gb=params["requested_gb"], reason=params.get("reason", ""),
        )
    finally:
        await db.close()

@activity.defn(name="apply_storage_expansion")
async def apply_storage_expansion(params: dict) -> None:
    from services.platform_ops_service import PlatformOpsService

    db = await _connect()
    try:
        await PlatformOpsService(db).apply_storage_expansion(
            tenant_id=params["tenant_id"], request_id=params["request_id"],
            requested_gb=params["requested_gb"], decided_by=params.get("decided_by"),
        )
    finally:
        await db.close()

@activity.defn(name="reject_storage_expansion")
async def reject_storage_expansion(params: dict) -> None:
    from services.platform_ops_service import PlatformOpsService

    db = await _connect()
    try:
        await PlatformOpsService(db).reject_storage_expansion(
            request_id=params["request_id"], decided_by=params.get("decided_by"),
        )
    finally:
        await db.close()


@workflow.defn(name="StorageExpansionWorkflow")
class StorageExpansionWorkflow:
    """
    Tenant requests additional S3 storage quota beyond default limit.
    Waits for Portal Admin 'approve' or 'reject' signal.
    SLA: PA must decide within 3 business days.
    """

    def __init__(self):
        self._decision: tuple | None = None

    @workflow.signal(name="approve")
    def approve(self, actor_id: str) -> None:
        self._decision = ("APPROVED", actor_id)

    @workflow.signal(name="reject")
    def reject(self, actor_id: str, reason: str = "") -> None:
        self._decision = ("REJECTED", actor_id, reason)

    @workflow.run
    async def run(self, params: dict) -> None:
        await self._execute(params)

    async def _execute(self, params: dict) -> None:
        request_id = await workflow.execute_activity(
            notify_storage_expansion_request, params,
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
        )
        received = await workflow.wait_condition(
            lambda: self._decision is not None, timeout=timedelta(days=3),
        )
        approved   = received and self._decision and self._decision[0] == "APPROVED"
        decided_by = self._decision[1] if received and self._decision else None
        act        = apply_storage_expansion if approved else reject_storage_expansion
        timeout    = timedelta(minutes=10)    if approved else timedelta(minutes=5)
        await workflow.execute_activity(
            act, {**params, "request_id": request_id, "decided_by": decided_by},
            start_to_close_timeout=timeout, retry_policy=_RETRY,
        )


# ── OnboardingReviewSLAWorkflow (Pattern 5 — Human Signal) ───────────────────

@activity.defn(name="escalate_onboarding_review")
async def escalate_onboarding_review(params: dict) -> None:
    from kafka.producer import get_kafka_producer
    from services.platform_ops_service import PlatformOpsService

    db = await _connect()
    try:
        kafka = await get_kafka_producer()
        await PlatformOpsService(db, kafka=kafka).escalate_onboarding_review(tenant_id=params["tenant_id"])
    finally:
        await db.close()


@workflow.defn(name="OnboardingReviewSLAWorkflow")
class OnboardingReviewSLAWorkflow:
    """
    Tracks Portal Admin review SLA for tenant onboarding applications.
    PA must approve or reject within domain_verification_max_hours (default 48).
    On SLA breach: notifies every active PA Admin (email, via CommunicationHubConsumer's
    _handle_onboarding_review_sla_breach) — PRANA has no PA sub-hierarchy to
    escalate "up" to, so all active PAs are the escalation target.
    """

    def __init__(self):
        self._reviewed = False

    @workflow.signal(name="review_complete")
    def review_complete(self, payload: dict) -> None:
        self._reviewed = True

    @workflow.run
    async def run(self, params: dict) -> None:
        hours_str = await workflow.execute_activity(
            get_ops_config,
            {"key": "domain_verification_max_hours", "default": "48"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        reviewed_in_time = await workflow.wait_condition(
            lambda: self._reviewed,
            timeout=timedelta(hours=int(hours_str)),
        )
        if not reviewed_in_time:
            await workflow.execute_activity(
                escalate_onboarding_review, params,
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=_RETRY,
            )
