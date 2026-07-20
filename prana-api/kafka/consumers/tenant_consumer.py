"""
TenantConsumer — prana.tenant.events

Handles tenant lifecycle: provisioning, activation, suspension.

Events handled:
  TENANT_CREATED     → start TenantProvisioningWorkflow (KEK, S3 prefix, first OA-Admin,
                        welcome email — see workflows/tenant.py)
  TENANT_ACTIVATED   → no workflow ("TenantOnboardingWorkflow" was never @workflow.defn'd;
                        the welcome-email/provisioning it would have done is already
                        covered by TenantProvisioningWorkflow off TENANT_CREATED)
  TENANT_SUSPENDED   → no workflow (never published — routers/pa_admin.py's suspend_tenant
                        writes the DB status directly without publishing this event; no
                        "TenantSuspensionWorkflow" exists either)
  TENANT_OFFBOARDED  → start TenantOffboardingWorkflow (full data cleanup)
  KEK_ROTATED        → no workflow (never published; no "KekRotationWorkflow" exists —
                        real KEK rotation is KMSKeyRotationWorkflow, workflows/security.py,
                        a single perpetual Continue-As-New process on secops-queue that
                        iterates all tenants itself, not a per-tenant per-event workflow)
  TENANT_CONFIG_UPDATED / API_KEY_REVOKED
                     → CacheInvalidationConsumer already handles these via auto-publish;
                        this consumer only needs to log — no workflow needed.
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings

log = logging.getLogger(__name__)
GROUP_ID = "prana-tenant-consumer"


class TenantConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None, temporal_client=None) -> None:
        self._pool = db_pool
        self._temporal = temporal_client
        self._consumer = AIOKafkaConsumer(
            "prana.tenant.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("TenantConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                etype = event.get("event_type")
                try:
                    await self._dispatch(etype, event)
                except Exception as exc:
                    from kafka.error_capture import record_consumer_error
                    await record_consumer_error(
                        self._pool, consumer_name="TenantConsumer", exc=exc, event_type=etype,
                    )
                    log.exception("TenantConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _dispatch(self, etype: Optional[str], event: dict) -> None:
        tid = event.get("tenant_id")

        if etype == "TENANT_CREATED":
            await self._start_workflow("TenantProvisioningWorkflow",
                                       f"tenant-provision-{tid}", event, "admin-queue")

        elif etype == "TENANT_ACTIVATED":
            # No workflow: "TenantOnboardingWorkflow" was never @workflow.defn'd —
            # starting it would silently queue a workflow no worker could execute.
            # The welcome-email/provisioning it would have done already happens in
            # TenantProvisioningWorkflow off TENANT_CREATED.
            log.debug("TenantConsumer: TENANT_ACTIVATED has no event-driven handler "
                      "— provisioning already ran off TENANT_CREATED")

        elif etype == "TENANT_SUSPENDED":
            # No workflow: never published (routers/pa_admin.py's suspend_tenant writes
            # the DB status directly, no Kafka event) and "TenantSuspensionWorkflow" was
            # never @workflow.defn'd.
            log.debug("TenantConsumer: TENANT_SUSPENDED has no event-driven handler")

        elif etype == "TENANT_OFFBOARDED":
            await self._start_workflow("TenantOffboardingWorkflow",
                                       f"tenant-offboard-{tid}", event, "admin-queue")

        elif etype == "KEK_ROTATED":
            # No workflow: never published, and "KekRotationWorkflow" was never
            # @workflow.defn'd. Real KEK rotation is KMSKeyRotationWorkflow
            # (workflows/security.py) — a single perpetual process on secops-queue
            # that iterates all tenants itself, not a per-event per-tenant workflow.
            log.debug("TenantConsumer: KEK_ROTATED has no event-driven handler "
                      "— see KMSKeyRotationWorkflow's perpetual schedule")

        else:
            log.debug("TenantConsumer: no workflow for event_type=%s — audit handles it", etype)

    async def _start_workflow(self, workflow: str, wf_id: str, event: dict, task_queue: str) -> None:
        if not self._temporal:
            return
        try:
            await self._temporal.start_workflow(
                workflow, event, id=wf_id, task_queue=task_queue,
            )
            log.info("TenantConsumer: started %s workflow_id=%s", workflow, wf_id)
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                log.exception("TenantConsumer: failed to start %s", workflow)
                raise
