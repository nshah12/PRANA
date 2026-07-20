"""
TenantIsolationGuard — CROSS_TENANT_QUERY anomaly detection.

Called from an HTTP handler AFTER an ownership-scoped lookup
(`WHERE id = $1 AND tenant_id = $2`) returns nothing, to distinguish a genuine
cross-tenant read attempt (the resource exists, just under a DIFFERENT tenant)
from a plain bad ID (the resource doesn't exist anywhere) — only the former is
worth flagging.

Publishes via Kafka only — never writes anomaly_event directly. The HTTP
handler contract forbids audit-adjacent writes in HTTP handlers; SecurityConsumer
persists the anomaly_event row and creates an incident downstream, the same
pipeline every other anomaly source uses. See
prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §3.2/§4.

Each resource type gets its own hardcoded, fully-parameterized query — never a
dynamic table name built with an f-string.
"""
import logging
import uuid
from typing import Optional

log = logging.getLogger(__name__)


class TenantIsolationGuard:

    def __init__(self, db) -> None:
        self._db = db

    async def check_document_access(
        self, *, document_id: str, requesting_tenant_id: str, actor_id: Optional[str],
    ) -> None:
        actual_tenant_id = await self._db.fetchval(
            "SELECT tenant_id FROM document WHERE document_id = $1", document_id,
        )
        await self._flag_if_cross_tenant(
            actual_tenant_id=actual_tenant_id, requesting_tenant_id=requesting_tenant_id,
            actor_id=actor_id, resource_type="document", resource_id=document_id,
        )

    async def check_employee_access(
        self, *, employee_uuid: str, requesting_tenant_id: str, actor_id: Optional[str],
    ) -> None:
        actual_tenant_id = await self._db.fetchval(
            "SELECT tenant_id FROM employee_master WHERE employee_uuid = $1", employee_uuid,
        )
        await self._flag_if_cross_tenant(
            actual_tenant_id=actual_tenant_id, requesting_tenant_id=requesting_tenant_id,
            actor_id=actor_id, resource_type="employee_master", resource_id=employee_uuid,
        )

    async def _flag_if_cross_tenant(
        self, *, actual_tenant_id, requesting_tenant_id: str, actor_id: Optional[str],
        resource_type: str, resource_id: str,
    ) -> None:
        if not actual_tenant_id or str(actual_tenant_id) == str(requesting_tenant_id):
            return  # genuinely not found, or same tenant — not a cross-tenant attempt

        try:
            from kafka.producer import get_kafka_producer
            kafka = await get_kafka_producer()
            await kafka.security_event({
                "event_type": "ANOMALY_DETECTED",
                "anomaly_id": str(uuid.uuid4()),
                "rule_name": "CROSS_TENANT_QUERY",
                "tenant_id": str(requesting_tenant_id),
                "actor_id": actor_id,
                "event_metadata": {"resource_type": resource_type, "resource_id": resource_id},
            })
            log.warning(
                "TenantIsolationGuard: CROSS_TENANT_QUERY flagged resource_type=%s "
                "resource_id=%s requesting_tenant=%s",
                resource_type, resource_id, requesting_tenant_id,
            )
        except Exception:
            log.exception("TenantIsolationGuard: failed to publish CROSS_TENANT_QUERY anomaly")
