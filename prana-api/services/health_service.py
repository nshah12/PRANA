"""
HealthService — business logic for SystemHealthWorkflow.

Pings each internal service's /health endpoint.
On failure: creates service_incident row + sends PA notification.
On recovery: auto-resolves the open incident.

Called by SystemHealthWorkflow (thin Temporal shell).
Zero Temporal imports here.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg
import httpx

log = logging.getLogger(__name__)

# Services checked on every poll cycle
# severity: P1 = data loss / auth down, P2 = feature degraded, P3 = non-critical
HEALTH_TARGETS = [
    {"name": "prana-api",  "url": "http://localhost:8000/health", "severity": "P1"},
    {"name": "prana-ai",   "url": "http://localhost:8001/health", "severity": "P2"},
    {"name": "prana-ask",  "url": "http://localhost:8002/health", "severity": "P3"},
]


class HealthService:

    def __init__(self, db: asyncpg.Connection):
        self._db = db

    async def run_checks(self) -> list[dict]:
        """
        Ping all health targets. Open incident on failure; resolve on recovery.
        Returns list of check results.
        """
        results = []
        for target in HEALTH_TARGETS:
            ok, detail = await _ping(target["url"])
            if ok:
                await self._resolve_if_open(target["name"])
            else:
                await self._open_or_update(target["name"], target["severity"], detail, target["url"])
            results.append({"service": target["name"], "healthy": ok, "detail": detail})
        return results

    async def _open_or_update(self, service: str, severity: str, detail: str, url: str) -> None:
        """Create a new OPEN incident only if one doesn't already exist for this service."""
        existing = await self._db.fetchval(
            "SELECT incident_id FROM service_incident WHERE service_name=$1 AND status='OPEN' LIMIT 1",
            service,
        )
        if existing:
            return  # incident already open — don't spam duplicates

        incident_id = await self._db.fetchval(
            """
            INSERT INTO service_incident
              (service_name, severity, title, detail, check_url)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING incident_id
            """,
            service,
            severity,
            f"{service} health check failed",
            detail,
            url,
        )
        log.error("service_incident opened", extra={"incident_id": str(incident_id), "service": service})
        await self._notify_pa(service, severity, str(incident_id), detail)

    async def _resolve_if_open(self, service: str) -> None:
        """Auto-resolve any open incident for this service when health check passes again."""
        await self._db.execute(
            """
            UPDATE service_incident
            SET status='RESOLVED', resolved_at=NOW(), resolution_note='Auto-resolved: health check passed'
            WHERE service_name=$1 AND status='OPEN'
            """,
            service,
        )

    async def _notify_pa(self, service: str, severity: str, incident_id: str, detail: str) -> None:
        """
        Write a notification audit event. PA sees it in the portal immediately.
        In production this also sends email/SMS via NotifConsumer reading prana.notifications.
        """
        try:
            await self._db.execute(
                """
                INSERT INTO audit_event (event_type, actor_type, event_metadata)
                VALUES ('SERVICE_INCIDENT_OPENED', 'system', $1::jsonb)
                """,
                f'{{"service": "{service}", "severity": "{severity}", "incident_id": "{incident_id}", "detail": "{detail[:200]}"}}'
            )
        except Exception as e:
            log.warning("failed to write incident audit event: %s", e)

    async def get_open_incidents(self) -> list[dict]:
        rows = await self._db.fetch(
            """
            SELECT incident_id, service_name, severity, status, title, detail,
                   detected_at, acknowledged_at, resolved_at, resolution_note
            FROM service_incident
            ORDER BY
              CASE severity WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
              detected_at DESC
            LIMIT 100
            """
        )
        return [dict(r) for r in rows]

    async def acknowledge(self, incident_id: UUID, pa_id: UUID) -> None:
        await self._db.execute(
            """
            UPDATE service_incident
            SET status='ACKNOWLEDGED', acknowledged_at=NOW(), acknowledged_by=$2
            WHERE incident_id=$1 AND status='OPEN'
            """,
            incident_id, pa_id,
        )

    async def resolve(self, incident_id: UUID, pa_id: UUID, note: str) -> None:
        await self._db.execute(
            """
            UPDATE service_incident
            SET status='RESOLVED', resolved_at=NOW(), resolved_by=$2, resolution_note=$3
            WHERE incident_id=$1 AND status IN ('OPEN','ACKNOWLEDGED')
            """,
            incident_id, pa_id, note,
        )


async def _ping(url: str) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url)
            if r.status_code == 200:
                return True, ""
            return False, f"HTTP {r.status_code}"
    except httpx.ConnectError:
        return False, "Connection refused — service is down"
    except httpx.TimeoutException:
        return False, "Health check timed out (>5s)"
    except Exception as e:
        return False, str(e)[:200]
