"""
Elevation API — OA-Operator requests, OA-Admin approves/denies.

POST   /org/elevations                    — operator: request elevation
GET    /org/elevations/active             — operator: my current active session
GET    /org/elevations/pending            — admin: pending requests for this tenant
GET    /org/elevations/history            — both: past requests for this tenant
POST   /org/elevations/{id}/approve       — admin: approve + signal ElevationWorkflow
POST   /org/elevations/{id}/deny          — admin: deny + signal ElevationWorkflow
POST   /org/elevations/{id}/end-early     — operator: end own active session early

Audit events (written via Kafka → AuditConsumer):
  ELEVATION_REQUESTED, ELEVATION_APPROVED, ELEVATION_DENIED, ELEVATION_ENDED_EARLY
"""
import datetime
import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from dependencies import DbConn, require_oa

router = APIRouter()

OAOperator = Depends(require_oa("oa_operator", "oa_admin"))
OAAdmin    = Depends(require_oa("oa_admin"))


# ── Request models ─────────────────────────────────────────────────────────────

class RequestElevationIn(BaseModel):
    duration_hours: int   # must be 2, 4, or 8 — enforced by DB CHECK constraint
    reason: str


class ApproveElevationIn(BaseModel):
    pass   # no body needed — approver_id comes from JWT


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/elevations", status_code=status.HTTP_202_ACCEPTED)
async def request_elevation(
    body: RequestElevationIn,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_operator", "oa_admin")),
):
    if body.duration_hours not in (2, 4, 8):
        raise HTTPException(status_code=422, detail="INVALID_DURATION")
    if not body.reason.strip():
        raise HTTPException(status_code=422, detail="REASON_REQUIRED")

    # Block if already has a PENDING or ACTIVE elevation
    existing = await db.fetchval(
        """
        SELECT elevation_id FROM elevation_request
        WHERE tenant_id=$1 AND requestor_id=$2 AND status IN ('PENDING','ACTIVE')
        """,
        current.tenant_id, current.user_id,
    )
    if existing:
        raise HTTPException(status_code=409, detail="ELEVATION_ALREADY_ACTIVE")

    elevation_id = str(uuid.uuid4())

    await db.execute(
        """
        INSERT INTO elevation_request
          (elevation_id, requestor_id, tenant_id, reason, duration_hours, status, requested_at)
        VALUES ($1, $2, $3, $4, $5, 'PENDING', NOW())
        """,
        elevation_id, current.user_id, current.tenant_id,
        body.reason.strip(), body.duration_hours,
    )

    # kafka02-correlated-start-ok: ElevationWorkflow must be running before admin can signal approve/deny.
    # Direct start ensures workflow is live before this handler returns 202.
    temporal = getattr(request.app.state, "temporal_client", None)
    if temporal:
        from workflows.elevation import ElevationWorkflow
        TASK_QUEUE = "admin-queue"
        await temporal.start_workflow(  # kafka02-correlated-start-ok: approve/deny signals need workflow live before returning
            ElevationWorkflow.run,
            {
                "elevation_id": elevation_id,
                "tenant_id":    current.tenant_id,
                "requestor_id": current.user_id,
            },
            id=f"elevation-{elevation_id}",
            task_queue=TASK_QUEUE,
        )

    # Kafka audit event
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.publish("prana.audit.events", {
            "event_type":   "ELEVATION_REQUESTED",
            "event_id":     str(uuid.uuid4()),
            "occurred_at":  datetime.datetime.utcnow().isoformat(),
            "tenant_id":    current.tenant_id,
            "actor_id":     current.user_id,
            "actor_type":   "OA_OPERATOR",
            "ip_address":   _client_ip(request),
            "elevation_id": elevation_id,
            "duration_hours": body.duration_hours,
            "reason":       body.reason.strip(),
        }, key=current.tenant_id)

    return {"elevation_id": elevation_id, "status": "PENDING"}


@router.get("/elevations/active")
async def get_active_elevation(
    db: DbConn,
    current=Depends(require_oa("oa_operator", "oa_admin")),
):
    """Returns the caller's current ACTIVE elevation, or null."""
    row = await db.fetchrow(
        """
        SELECT elevation_id, duration_hours, reason, expires_at, approved_at
        FROM elevation_request
        WHERE tenant_id=$1 AND requestor_id=$2 AND status='ACTIVE'
          AND expires_at > NOW()
        ORDER BY approved_at DESC LIMIT 1
        """,
        current.tenant_id, current.user_id,
    )
    if not row:
        return None
    return {
        "elevation_id": str(row["elevation_id"]),
        "tenant_id": str(row["tenant_id"]),
        "requestor_id": str(row["requestor_id"]),
        "approved_by": str(row["approved_by"]) if row["approved_by"] else None,
        "duration_hours": row["duration_hours"],
        "approved_at": row["approved_at"].isoformat() if row["approved_at"] else None,
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
    }


@router.get("/elevations/pending")
async def get_pending_elevations(
    db: DbConn,
    current=Depends(require_oa("oa_admin")),
):
    """OA-Admin: list all PENDING elevation requests for this tenant."""
    rows = await db.fetch(
        """
        SELECT er.elevation_id, er.requestor_id, er.reason, er.duration_hours,
               er.status, er.requested_at,
               u.full_name AS requestor_name, u.email AS requestor_email
        FROM elevation_request er
        JOIN oa_user u ON u.oa_user_id = er.requestor_id
        WHERE er.tenant_id=$1 AND er.status='PENDING'
        ORDER BY er.requested_at ASC
        """,
        current.tenant_id,
    )
    return {"elevations": [
        {
            "elevation_id": str(r["elevation_id"]),
            "requestor_id": str(r["requestor_id"]),
            "requestor_name": r["requestor_name"],
            "requestor_email": r["requestor_email"],
            "reason": r["reason"],
            "duration_hours": r["duration_hours"],
            "status": r["status"],
            "requested_at": r["requested_at"].isoformat() if r["requested_at"] else None,
        }
        for r in rows
    ], "total": len(rows)}


@router.get("/elevations/history")
async def get_elevation_history(
    db: DbConn,
    limit: int = 50,
    current=Depends(require_oa("oa_operator", "oa_admin")),
):
    # Operators see only their own; admins see all
    if current.role == "oa_admin":
        rows = await db.fetch(
            """
            SELECT er.elevation_id, er.requestor_id, er.approver_id,
                   er.reason, er.duration_hours, er.status,
                   er.requested_at, er.approved_at, er.expires_at,
                   u.full_name AS requestor_name,
                   a.full_name AS approver_name
            FROM elevation_request er
            JOIN oa_user u ON u.oa_user_id = er.requestor_id
            LEFT JOIN oa_user a ON a.oa_user_id = er.approver_id
            WHERE er.tenant_id=$1
            ORDER BY er.requested_at DESC LIMIT $2
            """,
            current.tenant_id, limit,
        )
    else:
        rows = await db.fetch(
            """
            SELECT elevation_id, reason, duration_hours, status,
                   requested_at, approved_at, expires_at
            FROM elevation_request
            WHERE tenant_id=$1 AND requestor_id=$2
            ORDER BY requested_at DESC LIMIT $3
            """,
            current.tenant_id, current.user_id, limit,
        )
    return {"elevations": [
        {
            "elevation_id": str(r["elevation_id"]),
            "requestor_id": str(r["requestor_id"]),
            "requestor_name": r.get("requestor_name"),
            "approver_id": str(r["approver_id"]) if r.get("approver_id") else None,
            "approver_name": r.get("approver_name"),
            "reason": r["reason"],
            "duration_hours": r["duration_hours"],
            "status": r["status"],
            "requested_at": r["requested_at"].isoformat() if r["requested_at"] else None,
            "approved_at": r["approved_at"].isoformat() if r.get("approved_at") else None,
            "expires_at": r["expires_at"].isoformat() if r.get("expires_at") else None,
        }
        for r in rows
    ], "total": len(rows)}


@router.post("/elevations/{elevation_id}/approve", status_code=status.HTTP_200_OK)
async def approve_elevation(
    elevation_id: str,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_admin")),
):
    row = await db.fetchrow(
        "SELECT requestor_id, duration_hours, status FROM elevation_request "
        "WHERE elevation_id=$1 AND tenant_id=$2",
        elevation_id, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="ELEVATION_NOT_FOUND")
    if row["status"] != "PENDING":
        raise HTTPException(status_code=409, detail="ELEVATION_NOT_PENDING")

    # Signal the waiting ElevationWorkflow — it handles the DB status update
    temporal = getattr(request.app.state, "temporal_client", None)
    if temporal:
        try:
            wf = temporal.get_workflow_handle(f"elevation-{elevation_id}")
            await wf.signal("admin_decision", {
                "approved":       True,
                "approver_id":    current.user_id,
                "duration_hours": row["duration_hours"],
            })
        except Exception:
            raise HTTPException(status_code=503, detail="WORKFLOW_UNAVAILABLE")

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.publish("prana.audit.events", {
            "event_type":   "ELEVATION_APPROVED",
            "event_id":     str(uuid.uuid4()),
            "occurred_at":  datetime.datetime.utcnow().isoformat(),
            "tenant_id":    current.tenant_id,
            "actor_id":     current.user_id,
            "actor_type":   "OA_ADMIN",
            "ip_address":   _client_ip(request),
            "elevation_id": elevation_id,
            "requestor_id": str(row["requestor_id"]),
            "duration_hours": row["duration_hours"],
        }, key=current.tenant_id)

        # Notify operator
        await kafka.publish("prana.notifications", {
            "event_type":   "ELEVATION_APPROVED",
            "tenant_id":    current.tenant_id,
            "elevation_id": elevation_id,
            "requestor_id": str(row["requestor_id"]),
            "duration_hours": row["duration_hours"],
        }, key=str(row["requestor_id"]))

    return {"elevation_id": elevation_id, "status": "APPROVED"}


@router.post("/elevations/{elevation_id}/deny", status_code=status.HTTP_200_OK)
async def deny_elevation(
    elevation_id: str,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_admin")),
):
    row = await db.fetchrow(
        "SELECT requestor_id, status FROM elevation_request "
        "WHERE elevation_id=$1 AND tenant_id=$2",
        elevation_id, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="ELEVATION_NOT_FOUND")
    if row["status"] != "PENDING":
        raise HTTPException(status_code=409, detail="ELEVATION_NOT_PENDING")

    temporal = getattr(request.app.state, "temporal_client", None)
    if temporal:
        try:
            wf = temporal.get_workflow_handle(f"elevation-{elevation_id}")
            await wf.signal("admin_decision", {
                "approved":    False,
                "approver_id": current.user_id,
            })
        except Exception:
            raise HTTPException(status_code=503, detail="WORKFLOW_UNAVAILABLE")

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.publish("prana.audit.events", {
            "event_type":   "ELEVATION_DENIED",
            "event_id":     str(uuid.uuid4()),
            "occurred_at":  datetime.datetime.utcnow().isoformat(),
            "tenant_id":    current.tenant_id,
            "actor_id":     current.user_id,
            "actor_type":   "OA_ADMIN",
            "ip_address":   _client_ip(request),
            "elevation_id": elevation_id,
            "requestor_id": str(row["requestor_id"]),
        }, key=current.tenant_id)

    return {"elevation_id": elevation_id, "status": "DENIED"}


@router.post("/elevations/{elevation_id}/end-early", status_code=status.HTTP_200_OK)
async def end_elevation_early(
    elevation_id: str,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_operator", "oa_admin")),
):
    row = await db.fetchrow(
        "SELECT requestor_id, status FROM elevation_request "
        "WHERE elevation_id=$1 AND tenant_id=$2",
        elevation_id, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="ELEVATION_NOT_FOUND")
    if row["status"] != "ACTIVE":
        raise HTTPException(status_code=409, detail="ELEVATION_NOT_ACTIVE")
    # Operator can only end their own; admin can end any
    if current.role != "oa_admin" and str(row["requestor_id"]) != current.user_id:
        raise HTTPException(status_code=403, detail="NOT_YOUR_ELEVATION")

    temporal = getattr(request.app.state, "temporal_client", None)
    if temporal:
        try:
            wf = temporal.get_workflow_handle(f"elevation-{elevation_id}")
            await wf.signal("end_early")
        except Exception:
            raise HTTPException(status_code=503, detail="WORKFLOW_UNAVAILABLE")

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.publish("prana.audit.events", {
            "event_type":   "ELEVATION_ENDED_EARLY",
            "event_id":     str(uuid.uuid4()),
            "occurred_at":  datetime.datetime.utcnow().isoformat(),
            "tenant_id":    current.tenant_id,
            "actor_id":     current.user_id,
            "actor_type":   "OA_ADMIN" if current.role == "oa_admin" else "OA_OPERATOR",
            "ip_address":   _client_ip(request),
            "elevation_id": elevation_id,
        }, key=current.tenant_id)

    return {"elevation_id": elevation_id, "status": "ENDED_EARLY"}


# ── Helper ────────────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return str(request.client.host) if request.client else "unknown"
