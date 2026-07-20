"""
IncidentService — creates and manages incident rows.

Severity → SLA deadline and severity → auto-create-incident are both read from
the PA-editable `sla_policy` table (via SeverityPolicyService) — see
prana-docs/SEVERITY_SLA_POLICY_DESIGN.md. No longer hardcoded in Python.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import asyncpg

from services.severity_policy_service import SeverityPolicyService

log = logging.getLogger(__name__)


class IncidentService:
    def __init__(self, db: asyncpg.Connection) -> None:
        self._db = db
        self._policy = SeverityPolicyService(db)

    async def create_incident(
        self,
        *,
        incident_type: str,
        severity: str,
        title: str,
        tenant_id: Optional[str] = None,
        description: Optional[str] = None,
        source_table: Optional[str] = None,
        source_id: Optional[str] = None,
        assigned_to: Optional[str] = None,
        assigned_role: Optional[str] = None,
    ) -> str:
        """Insert an incident row and return the new incident_id."""
        sla = await self._policy.get_sla(severity=severity)
        sla_deadline = (
            datetime.now(timezone.utc) + timedelta(minutes=sla["sla_minutes"]) if sla else None
        )

        import uuid as _uuid
        incident_id = str(_uuid.uuid4())
        await self._db.execute(
            """
            INSERT INTO incident
              (incident_id, tenant_id, incident_type, severity, title, description,
               source_table, source_id,
               assigned_to, assigned_role,
               status, sla_deadline)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'OPEN',$11)
            """,
            incident_id,
            tenant_id, incident_type, severity, title, description,
            source_table, source_id,
            assigned_to, assigned_role,
            sla_deadline,
        )

        log.info("Incident created incident_type=%s severity=%s tenant=%s",
                 incident_type, severity, tenant_id)
        return str(incident_id) if incident_id else ""

    async def auto_create_for_anomaly(
        self,
        *,
        anomaly_id: str,
        tenant_id: str,
        rule_name: str,
        severity: str,
        assigned_ciso_id: Optional[str] = None,
    ) -> Optional[str]:
        """Create incident only if sla_policy.auto_create_incident is set for this
        severity (PA-editable, formerly hardcoded to P0/P1 only). Returns incident_id or None."""
        sla = await self._policy.get_sla(severity=severity)
        if not sla or not sla["auto_create_incident"]:
            return None

        return await self.create_incident(
            incident_type="SECURITY_ANOMALY",
            severity=severity,
            title=f"Security anomaly: {rule_name}",
            tenant_id=tenant_id,
            source_table="anomaly_event",
            source_id=anomaly_id,
            assigned_to=assigned_ciso_id,
            assigned_role="CISO",
        )

    async def resolve_incident(
        self,
        *,
        incident_id: str,
        resolved_by: str,
        resolution_note: str,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Mark incident resolved. Raises ValueError if not found or cross-tenant."""
        row = await self._db.fetchrow(
            "SELECT incident_id, tenant_id, status FROM incident WHERE incident_id = $1",
            incident_id,
        )
        if not row:
            raise ValueError(f"Incident not found: {incident_id}")
        if tenant_id and str(row["tenant_id"]) != tenant_id:
            raise ValueError(f"Incident not found: {incident_id}")

        await self._db.execute(
            """
            UPDATE incident
               SET status = 'RESOLVED',
                   resolved_at = $1,
                   resolved_by = $2,
                   resolution_note = $3
             WHERE incident_id = $4
            """,
            datetime.now(timezone.utc),
            resolved_by,
            resolution_note,
            incident_id,
        )

    async def escalate_incident(
        self,
        *,
        incident_id: str,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Mark incident escalated. Raises ValueError if not found or cross-tenant."""
        row = await self._db.fetchrow(
            "SELECT incident_id, tenant_id, status FROM incident WHERE incident_id = $1",
            incident_id,
        )
        if not row:
            raise ValueError(f"Incident not found: {incident_id}")
        if tenant_id and str(row["tenant_id"]) != tenant_id:
            raise ValueError(f"Incident not found: {incident_id}")

        await self._db.execute(
            """
            UPDATE incident
               SET status = 'ESCALATED',
                   escalated_at = $1
             WHERE incident_id = $2
            """,
            datetime.now(timezone.utc),
            incident_id,
        )

    async def get_incidents(
        self,
        *,
        tenant_id: Optional[str],
        severity: Optional[str],
        status: Optional[str],
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        List incidents.
        - tenant_id=str → CISO view (own tenant only)
        - tenant_id=None → PA view (all tenants)
        """
        conditions: list[str] = []
        params: list[Any] = []
        idx = 1

        if tenant_id is not None:
            conditions.append(f"tenant_id = ${idx}")
            params.append(tenant_id)
            idx += 1

        if severity:
            conditions.append(f"severity = ${idx}")
            params.append(severity)
            idx += 1

        if status:
            conditions.append(f"status = ${idx}")
            params.append(status)
            idx += 1

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)

        rows = await self._db.fetch(
            f"""
            SELECT incident_id, tenant_id, incident_type, severity, title,
                   status, sla_deadline, escalated_at, resolved_at, created_at,
                   assigned_role, assigned_to
              FROM incident
             {where}
             ORDER BY created_at DESC
             LIMIT ${idx}
            """,
            *params,
        )
        return [
            {
                "incident_id": str(r["incident_id"]),
                "tenant_id":   str(r["tenant_id"]) if r["tenant_id"] else None,
                "incident_type": r["incident_type"],
                "severity":    r["severity"],
                "title":       r["title"],
                "status":      r["status"],
                "sla_deadline": r["sla_deadline"].isoformat() if r["sla_deadline"] else None,
                "escalated_at": r["escalated_at"].isoformat() if r["escalated_at"] else None,
                "resolved_at":  r["resolved_at"].isoformat() if r["resolved_at"] else None,
                "created_at":   r["created_at"].isoformat() if r["created_at"] else None,
                "assigned_role": r["assigned_role"],
            }
            for r in rows
        ]
