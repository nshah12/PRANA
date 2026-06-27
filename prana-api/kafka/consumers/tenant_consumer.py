"""
TenantConsumer — prana.tenant.events

Handles tenant lifecycle: provisioning, activation, suspension.

Events handled:
  TENANT_CREATED     → start TenantProvisioningWorkflow (KEK, S3 prefix, first OA-Admin)
  TENANT_ACTIVATED   → start TenantOnboardingWorkflow (send welcome to OA-Admin)
  TENANT_SUSPENDED   → start TenantSuspensionWorkflow (revoke sessions, block ingest)
  TENANT_OFFBOARDED  → start TenantOffboardingWorkflow (full data cleanup)
  KEK_ROTATED        → start KekRotationWorkflow
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
                except Exception:
                    log.exception("TenantConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _dispatch(self, etype: Optional[str], event: dict) -> None:
        tid = event.get("tenant_id")

        if etype == "TENANT_CREATED":
            await self._start_workflow("TenantProvisioningWorkflow",
                                       f"tenant-provision-{tid}", event, "prana-admin")

        elif etype == "TENANT_ACTIVATED":
            await self._start_workflow("TenantOnboardingWorkflow",
                                       f"tenant-onboard-{tid}", event, "prana-admin")

        elif etype == "TENANT_SUSPENDED":
            await self._start_workflow("TenantSuspensionWorkflow",
                                       f"tenant-suspend-{tid}", event, "prana-admin")

        elif etype == "TENANT_OFFBOARDED":
            await self._start_workflow("TenantOffboardingWorkflow",
                                       f"tenant-offboard-{tid}", event, "prana-admin")

        elif etype == "KEK_ROTATED":
            await self._start_workflow("KekRotationWorkflow",
                                       f"kek-rotate-{tid}", event, "prana-admin")

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
