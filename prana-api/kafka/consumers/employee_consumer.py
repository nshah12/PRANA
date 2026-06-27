"""
EmployeeConsumer — prana.employee.events

Handles employee lifecycle: vault activation, exit, profile updates.

Events handled:
  EMPLOYEE_ONBOARDED     → start IdentityResolutionWorkflow
  VAULT_ACTIVATED        → start VaultActivationWorkflow
  EMPLOYEE_EXITED        → start EmployeeExitWorkflow (triggers push window, archive)
  EMPLOYEE_REJOINED      → start IdentityResolutionWorkflow (re-check dedup)
  ACCOUNT_DORMANT        → start AccountDormancyWorkflow
  EMPLOYEE_PROFILE_UPDATED → publish EMPLOYEE_PROFILE_INVALIDATE to cache.invalidation
"""
import json
import logging
from typing import Optional

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings

log = logging.getLogger(__name__)
GROUP_ID = "prana-employee-consumer"


class EmployeeConsumer:
    def __init__(self, settings: Settings, db_pool: Optional[asyncpg.Pool] = None, temporal_client=None, kafka_producer=None) -> None:
        self._pool = db_pool
        self._temporal = temporal_client
        self._kafka = kafka_producer
        self._consumer = AIOKafkaConsumer(
            "prana.employee.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("EmployeeConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                etype = event.get("event_type")
                try:
                    await self._dispatch(etype, event)
                except Exception:
                    log.exception("EmployeeConsumer error event_type=%s", etype)
        finally:
            await self._consumer.stop()

    async def _dispatch(self, etype: Optional[str], event: dict) -> None:
        if etype in ("EMPLOYEE_ONBOARDED", "EMPLOYEE_REJOINED"):
            await self._start_workflow("IdentityResolutionWorkflow",
                                       f"identity-{event.get('employee_uuid')}", event, "prana-ingest")

        elif etype == "VAULT_ACTIVATED":
            await self._start_workflow("VaultActivationWorkflow",
                                       f"vault-activate-{event.get('employee_uuid')}", event, "prana-ingest")

        elif etype == "EMPLOYEE_EXITED":
            await self._start_workflow("EmployeeExitWorkflow",
                                       f"emp-exit-{event.get('employee_uuid')}-{event.get('tenant_id')}", event, "prana-admin")

        elif etype == "ACCOUNT_DORMANT":
            await self._start_workflow("AccountDormancyWorkflow",
                                       f"dormant-{event.get('employee_user_id')}", event, "prana-admin")

        elif etype == "EMPLOYEE_PROFILE_UPDATED":
            if self._kafka:
                try:
                    await self._kafka.cache_invalidate(
                        "EMPLOYEE_PROFILE_INVALIDATE",
                        employee_user_id=event.get("employee_user_id"),
                        tenant_id=event.get("tenant_id"),
                    )
                except Exception:
                    log.exception("EmployeeConsumer: failed to publish cache invalidation")

        else:
            log.debug("EmployeeConsumer: no workflow for event_type=%s", etype)

    async def _start_workflow(self, workflow: str, wf_id: str, event: dict, task_queue: str) -> None:
        if not self._temporal:
            return
        try:
            await self._temporal.start_workflow(
                workflow, event, id=wf_id, task_queue=task_queue,
            )
            log.info("EmployeeConsumer: started %s workflow_id=%s", workflow, wf_id)
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                log.exception("EmployeeConsumer: failed to start %s", workflow)
                raise
