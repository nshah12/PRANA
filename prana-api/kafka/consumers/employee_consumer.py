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
  HRMS_EMPLOYEE_SYNCED   → upsert employee_master; publish EMPLOYEE_ONBOARDED for new entries
"""
import json
import logging
from typing import Optional
from uuid import UUID

import asyncpg
from aiokafka import AIOKafkaConsumer

from config import Settings
from connectors.base import strip_salary_fields

log = logging.getLogger(__name__)
GROUP_ID = "prana-employee-consumer"

_INACTIVE_STATUSES = {"inactive", "offboarded", "terminated", "resigned", "left"}


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

        elif etype == "HRMS_EMPLOYEE_SYNCED":
            if self._pool:
                async with self._pool.acquire() as conn:
                    await self._handle_hrms_employee_synced(event, conn)
            else:
                log.warning("EmployeeConsumer: no db_pool — cannot handle HRMS_EMPLOYEE_SYNCED")

        else:
            log.debug("EmployeeConsumer: no workflow for event_type=%s", etype)

    async def _handle_hrms_employee_synced(self, event: dict, conn) -> None:
        """
        Upsert employee_master from an HRMS pull record.

        New employee  → INSERT + publish EMPLOYEE_ONBOARDED (triggers IdentityResolutionWorkflow)
        Known employee → UPDATE mutable fields (designation, department, location)
        Inactive status → set dol (date of leaving)
        Privacy: salary fields stripped before any DB write.
        """
        tenant_id_str = event.get("tenant_id")
        employee_data = event.get("employee_data") or {}

        if not tenant_id_str or not employee_data.get("employee_id"):
            log.warning("HRMS_EMPLOYEE_SYNCED: missing tenant_id or employee_id — skipping")
            return

        # Privacy: strip salary fields before touching any DB column
        clean = strip_salary_fields(employee_data)

        tenant_id  = UUID(tenant_id_str)
        emp_id_org = clean["employee_id"]
        status_raw = (clean.get("status") or "active").lower()
        is_inactive = status_raw in _INACTIVE_STATUSES

        existing = await conn.fetchrow(
            """
            SELECT employee_uuid, employee_user_id, designation, department, status, dol
            FROM   employee_master
            WHERE  tenant_id  = $1
              AND  emp_id_org = $2
            """,
            tenant_id,
            emp_id_org,
        )

        if existing is None:
            await self._insert_new_employee(clean, tenant_id, conn)
        else:
            await self._update_existing_employee(
                existing=existing,
                clean=clean,
                tenant_id=tenant_id,
                is_inactive=is_inactive,
                conn=conn,
            )

    async def _insert_new_employee(self, clean: dict, tenant_id: UUID, conn) -> None:
        full_name = f"{clean.get('first_name', '')} {clean.get('last_name', '')}".strip()
        doj       = clean.get("date_of_join") or clean.get("date_of_joining")

        employee_uuid = await conn.fetchval(
            """
            INSERT INTO employee_master (
                tenant_id, emp_id_org, full_name,
                designation, department, location,
                employment_type, status, doj,
                pan_token, enc_pan, enc_dek
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::date,
                    'PENDING_RESOLUTION', 'PENDING_RESOLUTION', 'PENDING_RESOLUTION')
            RETURNING employee_uuid
            """,
            tenant_id,
            clean.get("employee_id"),
            full_name or "UNKNOWN",
            clean.get("designation"),
            clean.get("department"),
            clean.get("location"),
            (clean.get("employment_type") or "PERMANENT").upper(),
            "ACTIVE",
            doj,
        )

        log.info("HRMS_EMPLOYEE_SYNCED: inserted employee_uuid=%s emp_id=%s", employee_uuid, clean.get("employee_id"))

        if self._kafka:
            await self._kafka.employee_event({
                "event_type":    "EMPLOYEE_ONBOARDED",
                "tenant_id":     str(tenant_id),
                "employee_uuid": str(employee_uuid),
                "emp_id_org":    clean.get("employee_id"),
                "source":        "HRMS_SYNC",
            })

    async def _update_existing_employee(
        self, existing, clean: dict, tenant_id: UUID, is_inactive: bool, conn
    ) -> None:
        if is_inactive:
            await conn.execute(
                """
                UPDATE employee_master
                SET    dol        = CURRENT_DATE,
                       status     = 'ALUMNI',
                       updated_at = NOW()
                WHERE  tenant_id  = $1
                  AND  emp_id_org = $2
                """,
                tenant_id,
                clean.get("employee_id"),
            )
        else:
            await conn.execute(
                """
                UPDATE employee_master
                SET    designation = COALESCE($3, designation),
                       department  = COALESCE($4, department),
                       location    = COALESCE($5, location),
                       updated_at  = NOW()
                WHERE  tenant_id   = $1
                  AND  emp_id_org  = $2
                """,
                tenant_id,
                clean.get("employee_id"),
                clean.get("designation"),
                clean.get("department"),
                clean.get("location"),
            )

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
