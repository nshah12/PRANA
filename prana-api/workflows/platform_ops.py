"""
Platform operations workflows — thin Temporal shells.
Business logic lives in services/platform_ops_service.py.

Task queue: secops-queue (KMSHealthCheck), ingestsvc-queue (StagingCleanup, ClamAV),
            analytics-queue (StorageQuota), admin-queue (WebhookDelivery, Notification, SystemHealth)

Workflows (8 — BatchTimeoutMonitorWorkflow is in batch_progress.py):
  PlatformSummaryWorkflow    — aggregate platform health metrics every N minutes
  ClamAVUpdateWorkflow       — pull latest ClamAV signatures on a schedule
  KMSHealthCheckWorkflow     — verify all KMS key ARNs are accessible and active
  StorageQuotaCheckWorkflow  — alert when any tenant approaches S3 storage quota
  StagingCleanupWorkflow     — purge abandoned staging S3 objects older than N days
  WebhookDeliveryWorkflow    — durable delivery with retries for HRMS webhooks
  NotificationDeliveryWorkflow — durable push/email/SMS with retry + fallback
  SystemHealthWorkflow       — end-to-end healthcheck emitter (used by monitoring)
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

@activity.defn(name="deliver_notification")
async def deliver_notification(params: dict) -> dict:
    from services.platform_ops_service import PlatformOpsService

    db = await _connect()
    try:
        return await PlatformOpsService(db).deliver_notification(params)
    finally:
        await db.close()

@activity.defn(name="deliver_notification_fallback")
async def deliver_notification_fallback(params: dict) -> None:
    from services.platform_ops_service import PlatformOpsService

    db = await _connect()
    try:
        await PlatformOpsService(db).deliver_notification_fallback(params)
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


# ── ClamAVUpdateWorkflow (Pattern 3 — Temporal Schedule) ─────────────────────

@workflow.defn(name="ClamAVUpdateWorkflow")
class ClamAVUpdateWorkflow:
    """
    Pulls fresh ClamAV virus + NSFW signature databases on a schedule (default: daily).
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


# ── KMSHealthCheckWorkflow (Pattern 3 — Temporal Schedule) ───────────────────

@workflow.defn(name="KMSHealthCheckWorkflow")
class KMSHealthCheckWorkflow:
    """
    Verifies all KMS key ARNs (platform + tenant KEKs) are accessible and enabled.
    Alerts Platform Admin immediately on any failure.
    Runs every N minutes (default: 15).
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


# ── WebhookDeliveryWorkflow (Pattern 1 — durable delivery) ───────────────────

@workflow.defn(name="WebhookDeliveryWorkflow")
class WebhookDeliveryWorkflow:
    """
    Durable delivery of a webhook event to an HRMS endpoint.
    Retries up to webhook_max_retries (default: 10) with exponential backoff.
    On final failure: marks webhook as failed in webhook_delivery_log.
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


# ── NotificationDeliveryWorkflow (Pattern 1 — durable delivery) ──────────────

@workflow.defn(name="NotificationDeliveryWorkflow")
class NotificationDeliveryWorkflow:
    """
    Durable delivery of a notification (push / email / SMS) to an employee.
    Primary channel → fallback channel if primary fails.
    Consumed by NotifConsumer from prana.notifications Kafka topic.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        result = await workflow.execute_activity(
            deliver_notification, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )
        if not result.get("delivered") and params.get("fallback_channel"):
            await workflow.execute_activity(
                deliver_notification_fallback,
                {**params, "channel": params["fallback_channel"]},
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_RETRY,
            )


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
    On SLA breach: auto-escalates to senior PA team.
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
