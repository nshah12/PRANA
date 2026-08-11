"""
PlatformOpsService — business logic behind workflows/platform_ops.py's
15 activities (PlatformSummaryWorkflow, ClamAVUpdateWorkflow,
KMSHealthCheckWorkflow, StorageQuotaCheckWorkflow, StagingCleanupWorkflow,
WebhookDeliveryWorkflow, StorageExpansionWorkflow, OnboardingReviewSLAWorkflow).
Zero Temporal imports.

WebhookDeliveryWorkflow status: registered in worker.py, but nothing yet extracts
a WEBHOOK-mode tenant's webhook_url from hrms_connector_config.enc_credentials and
starts it — that trigger is a distinct, unscoped feature (see the workflow's own
docstring in workflows/platform_ops.py). deliver_webhook/mark_webhook_failed below
are real, tested, ready-to-use activities for whoever builds that trigger.

NotificationDeliveryWorkflow (and its deliver_notification/deliver_notification_fallback
activities) removed 2026-08-10 — dead code, real notification delivery already
happens via CommunicationHubConsumer's per-channel consumers directly. See
workflows/CLAUDE.md's Corrections section.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)


class PlatformOpsService:

    def __init__(self, db, s3_client=None, kms_client=None, kafka=None) -> None:
        self._db = db
        self._s3 = s3_client
        self._kms = kms_client
        self._kafka = kafka

    # ── PlatformSummaryWorkflow ──────────────────────────────────────────────

    async def collect_platform_metrics(self) -> dict:
        """One row per active tenant: vault_health_pct (avg overall_score across
        its employees), active_threats (OPEN anomaly_event count), kek_age_days
        (days since last TENANT_KEK rotation, NULL if never rotated)."""
        rows = await self._db.fetch(
            """
            SELECT t.tenant_id, t.home_region AS region,
                   COALESCE(AVG(vhs.overall_score), 0)::numeric(5,2) AS vault_health_pct,
                   COALESCE(ae.active_threats, 0) AS active_threats,
                   kek.kek_age_days
            FROM tenant t
            LEFT JOIN employee_master em ON em.tenant_id = t.tenant_id
            LEFT JOIN vault_health_score vhs ON vhs.pan_token = em.pan_token
            LEFT JOIN (
                SELECT tenant_id, COUNT(*) AS active_threats
                FROM anomaly_event WHERE status = 'OPEN' GROUP BY tenant_id
            ) ae ON ae.tenant_id = t.tenant_id
            LEFT JOIN (
                SELECT tenant_id, EXTRACT(DAY FROM NOW() - MAX(checked_at))::int AS kek_age_days
                FROM kms_key_log WHERE key_type = 'TENANT_KEK' AND event_type = 'ROTATED'
                GROUP BY tenant_id
            ) kek ON kek.tenant_id = t.tenant_id
            WHERE t.status = 'ACTIVE'
            GROUP BY t.tenant_id, t.home_region, ae.active_threats, kek.kek_age_days
            """
        )
        return {"rows": [dict(r) for r in rows]}

    async def write_platform_summary(self, rows: list) -> None:
        for row in rows:
            await self._db.execute(
                """
                INSERT INTO pa_platform_summary
                  (region, tenant_id, vault_health_pct, active_threats, kek_age_days, last_updated)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (region, tenant_id) DO UPDATE SET
                  vault_health_pct = EXCLUDED.vault_health_pct,
                  active_threats   = EXCLUDED.active_threats,
                  kek_age_days     = EXCLUDED.kek_age_days,
                  last_updated     = NOW()
                """,
                row["region"], row["tenant_id"], row["vault_health_pct"],
                row["active_threats"], row["kek_age_days"],
            )

    # ── ClamAVUpdateWorkflow ──────────────────────────────────────────────────

    async def pull_clamav_signatures(self) -> dict:
        """Runs freshclam against the shared ClamAV signature volume that clamd
        (used by prana-ai's stage03_scan.py) also reads from — freshclam updates
        signatures on disk, clamd picks them up on its own reload cycle; no
        cross-service call into prana-ai is needed or allowed (internal-service-
        calls.md has no authorized prana-api -> prana-ai path)."""
        import anyio

        proc = await anyio.run_process(["freshclam"], check=False)
        success = proc.returncode == 0
        if not success:
            log.error("pull_clamav_signatures: freshclam exited %s: %s",
                      proc.returncode, proc.stderr.decode(errors="replace"))
        return {"success": success, "returncode": proc.returncode}

    # ── KMSHealthCheckWorkflow ────────────────────────────────────────────────

    async def verify_kms_key_health(self) -> dict:
        rows = await self._db.fetch(
            "SELECT tenant_id, kek_arn FROM tenant WHERE status = 'ACTIVE'"
        )
        failures = []
        for row in rows:
            try:
                if self._kms:
                    self._kms.describe_key(KeyId=row["kek_arn"])
            except Exception as exc:
                failures.append({"tenant_id": str(row["tenant_id"]), "kek_arn": row["kek_arn"], "error": str(exc)})
        return {"all_healthy": not failures, "failures": failures}

    async def alert_kms_key_issue(self, failures: list) -> None:
        if not self._kafka:
            return
        await self._kafka.platform_event({
            "event_type": "KMS_HEALTH_FAILED",
            "service": "kms",
            "detail": failures,
        })

    # ── StorageQuotaCheckWorkflow ─────────────────────────────────────────────

    async def check_tenant_storage_quotas(self) -> list:
        rows = await self._db.fetch(
            """
            SELECT t.tenant_id, t.storage_quota_gb,
                   COALESCE(SUM(d.file_size_bytes), 0) AS used_bytes
            FROM tenant t
            LEFT JOIN document d ON d.tenant_id = t.tenant_id AND d.is_deleted = FALSE
            WHERE t.status = 'ACTIVE'
            GROUP BY t.tenant_id, t.storage_quota_gb
            """
        )
        over = []
        for row in rows:
            quota_bytes = row["storage_quota_gb"] * 1024 ** 3
            if quota_bytes <= 0:
                continue
            pct = row["used_bytes"] / quota_bytes
            if pct >= 0.80:
                over.append({
                    "tenant_id": str(row["tenant_id"]),
                    "used_pct": round(pct * 100, 1),
                    "threshold": "CRITICAL" if pct >= 0.95 else "WARNING",
                })
        return over

    async def alert_storage_quota(self, tenant: dict) -> None:
        if not self._kafka:
            return
        await self._kafka.platform_event({
            "event_type": "STORAGE_QUOTA_ALERT",
            "service": "storage",
            "tenant_id": tenant.get("tenant_id"),
            "used_pct": tenant.get("used_pct"),
            "threshold": tenant.get("threshold"),
        })

    # ── StagingCleanupWorkflow ────────────────────────────────────────────────

    async def purge_stale_staging_objects(self, *, staging_bucket: str, older_than_days: int) -> dict:
        if not self._s3:
            return {"deleted_count": 0}
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        deleted = 0
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=staging_bucket):
            stale_keys = [
                {"Key": obj["Key"]} for obj in page.get("Contents", [])
                if obj["LastModified"] < cutoff
            ]
            if stale_keys:
                self._s3.delete_objects(Bucket=staging_bucket, Delete={"Objects": stale_keys})
                deleted += len(stale_keys)
        return {"deleted_count": deleted}

    # ── WebhookDeliveryWorkflow ───────────────────────────────────────────────

    async def deliver_webhook(self, *, delivery_id: str, tenant_id: Optional[str],
                               webhook_url: str, event_type: str, payload: dict) -> dict:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook_url, json=payload)
            success = 200 <= resp.status_code < 300
            await self._db.execute(
                """
                INSERT INTO webhook_delivery_log
                  (delivery_id, tenant_id, webhook_url, event_type, status,
                   response_code, attempt_count, last_attempt_at)
                VALUES ($1, $2, $3, $4, $5, $6, 1, NOW())
                ON CONFLICT (delivery_id) DO UPDATE SET
                  status = EXCLUDED.status, response_code = EXCLUDED.response_code,
                  attempt_count = webhook_delivery_log.attempt_count + 1, last_attempt_at = NOW()
                """,
                delivery_id, tenant_id, webhook_url, event_type,
                "DELIVERED" if success else "PENDING", resp.status_code,
            )
            return {"success": success, "response_code": resp.status_code}
        except Exception as exc:
            log.warning("deliver_webhook: attempt failed delivery_id=%s: %s", delivery_id, exc)
            await self._db.execute(
                """
                INSERT INTO webhook_delivery_log
                  (delivery_id, tenant_id, webhook_url, event_type, status, attempt_count, last_attempt_at)
                VALUES ($1, $2, $3, $4, 'PENDING', 1, NOW())
                ON CONFLICT (delivery_id) DO UPDATE SET
                  attempt_count = webhook_delivery_log.attempt_count + 1, last_attempt_at = NOW()
                """,
                delivery_id, tenant_id, webhook_url, event_type,
            )
            return {"success": False, "response_code": None}

    async def mark_webhook_failed(self, delivery_id: str) -> None:
        await self._db.execute(
            "UPDATE webhook_delivery_log SET status='FAILED' WHERE delivery_id=$1",
            delivery_id,
        )

    # ── StorageExpansionWorkflow ──────────────────────────────────────────────

    async def notify_storage_expansion_request(self, *, tenant_id: str, current_gb: int,
                                                requested_gb: int, reason: str) -> str:
        request_id = await self._db.fetchval(
            """
            INSERT INTO storage_request (tenant_id, current_gb, requested_gb, reason, status)
            VALUES ($1, $2, $3, $4, 'PENDING')
            RETURNING request_id
            """,
            tenant_id, current_gb, requested_gb, reason,
        )
        if self._kafka:
            await self._kafka.platform_event({
                "event_type": "STORAGE_EXPANSION_REQUESTED",
                "service": "storage",
                "tenant_id": tenant_id,
                "request_id": str(request_id),
            })
        return str(request_id)

    async def apply_storage_expansion(self, *, tenant_id: str, request_id: str,
                                       requested_gb: int, decided_by: Optional[str]) -> None:
        async with self._db.transaction():
            await self._db.execute(
                "UPDATE tenant SET storage_quota_gb=$1 WHERE tenant_id=$2",
                requested_gb, tenant_id,
            )
            await self._db.execute(
                "UPDATE storage_request SET status='APPROVED', decided_by=$1, decided_at=NOW() WHERE request_id=$2",
                decided_by, request_id,
            )

    async def reject_storage_expansion(self, *, request_id: str, decided_by: Optional[str]) -> None:
        await self._db.execute(
            "UPDATE storage_request SET status='REJECTED', decided_by=$1, decided_at=NOW() WHERE request_id=$2",
            decided_by, request_id,
        )

    # ── OnboardingReviewSLAWorkflow ───────────────────────────────────────────

    async def escalate_onboarding_review(self, *, tenant_id: str) -> None:
        if not self._kafka:
            return
        await self._kafka.platform_event({
            "event_type": "ONBOARDING_REVIEW_SLA_BREACH",
            "service": "onboarding",
            "tenant_id": tenant_id,
        })
