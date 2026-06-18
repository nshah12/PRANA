"""
Compliance / DPDP Act 2023 employee-facing endpoints.

POST /vault/compliance/erasure          — request account deletion (triggers ErasureConfirmationWorkflow)
POST /vault/compliance/erasure/cancel   — cancel erasure during cooling-off window
POST /vault/compliance/export           — request data export (triggers DataExportWorkflow)
POST /vault/compliance/consent/withdraw — withdraw processing consent
POST /vault/compliance/consent/grant    — re-grant consent
POST /vault/compliance/grievance        — file a grievance
GET  /vault/compliance/grievances       — list employee's grievances

All routes require employee JWT. employee_user_id always from JWT claims.
"""
import uuid
import json
import logging
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from dependencies import Employee, DbConn

log = logging.getLogger(__name__)
router = APIRouter()


# ── Erasure ───────────────────────────────────────────────────────────────────

@router.post("/erasure", status_code=status.HTTP_202_ACCEPTED)
async def request_erasure(request: Request, db: DbConn, current=Employee):
    """
    Start 30-day erasure cooling-off window.
    Triggers ErasureConfirmationWorkflow — employee can cancel within 30 days.
    """
    workflow_id = f"erasure-{current.user_id}"

    # WorkflowConsumer starts ErasureConfirmationWorkflow on seeing ERASURE_REQUESTED
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.publish("prana.ingest.events", {
            "event_type": "ERASURE_REQUESTED",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.utcnow().isoformat(),
            "employee_user_id": str(current.user_id),
            "tenant_id": str(current.tenant_id) if current.tenant_id else None,
            "workflow_id": workflow_id,
        }, key=str(current.user_id))
        # Audit via separate topic — AuditConsumer writes to audit_event table
        await kafka.publish("prana.audit.events", {
            "event_type": "ERASURE_REQUESTED",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.utcnow().isoformat(),
            "actor_user_id": str(current.user_id),
            "actor_type": "employee",
            "workflow_id": workflow_id,
        }, key=str(current.user_id))

    return {
        "message": "Erasure request received. Your account will be deleted in 30 days unless you cancel.",
        "cancel_before_days": 30,
        "workflow_id": workflow_id,
    }


@router.post("/erasure/cancel", status_code=status.HTTP_200_OK)
async def cancel_erasure(request: Request, db: DbConn, current=Employee):
    """Send 'cancel_erasure' signal to the running ErasureConfirmationWorkflow."""
    temporal = request.app.state.temporal_client
    if temporal:
        try:
            handle = temporal.get_workflow_handle(f"erasure-{current.user_id}")
            await handle.signal("cancel_erasure")
        except Exception as exc:
            log.warning("Could not cancel erasure workflow: %s", exc)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NO_PENDING_ERASURE")

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.publish("prana.audit.events", {
            "event_type": "ERASURE_CANCELLED",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.utcnow().isoformat(),
            "actor_user_id": str(current.user_id),
            "actor_type": "employee",
        }, key=str(current.user_id))
    return {"message": "Erasure cancelled. Your account is safe."}


# ── Data export ───────────────────────────────────────────────────────────────

@router.post("/export", status_code=status.HTTP_202_ACCEPTED)
async def request_export(request: Request, db: DbConn, current=Employee):
    """
    Trigger DataExportWorkflow — packages all metadata as encrypted ZIP.
    Download link delivered within 24 hours (DPDP mandates 30 days; we target <24h).
    """
    workflow_id = f"export-{current.user_id}-{uuid.uuid4().hex[:8]}"

    # WorkflowConsumer starts DataExportWorkflow on seeing DATA_EXPORT_REQUESTED
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.publish("prana.ingest.events", {
            "event_type": "DATA_EXPORT_REQUESTED",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.utcnow().isoformat(),
            "employee_user_id": str(current.user_id),
            "workflow_id": workflow_id,
        }, key=str(current.user_id))
        await kafka.publish("prana.audit.events", {
            "event_type": "DATA_EXPORT_REQUESTED",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.utcnow().isoformat(),
            "actor_user_id": str(current.user_id),
            "actor_type": "employee",
            "workflow_id": workflow_id,
        }, key=str(current.user_id))

    return {
        "message": "Export request received. A download link will be sent to your registered number within 24 hours.",
        "workflow_id": workflow_id,
    }


# ── Consent ───────────────────────────────────────────────────────────────────

@router.post("/consent/withdraw", status_code=status.HTTP_200_OK)
async def withdraw_consent(request: Request, db: DbConn, current=Employee):
    """
    Mark employee as having withdrawn processing consent.
    New documents pushed by employers will not be processed.
    """
    await db.execute(
        "UPDATE employee_user SET status='CONSENT_WITHDRAWN', updated_at=NOW() WHERE employee_user_id=$1",
        current.user_id,
    )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.publish("prana.audit.events", {
            "event_type": "CONSENT_WITHDRAWN",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.utcnow().isoformat(),
            "actor_user_id": str(current.user_id),
            "actor_type": "employee",
        }, key=str(current.user_id))
    return {"message": "Consent withdrawn. PRANA will not process new documents from your employers."}


@router.post("/consent/grant", status_code=status.HTTP_200_OK)
async def grant_consent(request: Request, db: DbConn, current=Employee):
    """Re-grant processing consent after a previous withdrawal."""
    await db.execute(
        "UPDATE employee_user SET status='ACTIVE', updated_at=NOW() WHERE employee_user_id=$1",
        current.user_id,
    )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.publish("prana.audit.events", {
            "event_type": "CONSENT_GRANTED",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.utcnow().isoformat(),
            "actor_user_id": str(current.user_id),
            "actor_type": "employee",
        }, key=str(current.user_id))
    return {"message": "Consent granted. PRANA will process documents pushed by your employers."}


# ── Consent status ────────────────────────────────────────────────────────────

@router.get("/consent")
async def get_consent_status(db: DbConn, current=Employee):
    row = await db.fetchrow(
        "SELECT status, updated_at FROM employee_user WHERE employee_user_id=$1",
        current.user_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    granted = row["status"] == "ACTIVE"
    return {
        "consent_granted": granted,
        "status": row["status"],
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


# ── Grievance ─────────────────────────────────────────────────────────────────

class GrievanceIn(BaseModel):
    category: str = Field(..., description="WRONG_DOCUMENT | DATA_ERROR | ACCESS_DENIED | OTHER")
    description: str = Field(..., min_length=10, max_length=2000)


@router.post("/grievance", status_code=status.HTTP_201_CREATED)
async def file_grievance(
    body: GrievanceIn,
    request: Request,
    db: DbConn,
    current=Employee,
):
    """
    File a DPDP grievance. Triggers GrievanceWorkflow — 30-day SLA, escalates to PA on breach.
    """
    grievance_id = str(uuid.uuid4())

    # Write the row directly (workflow also calls open_grievance activity but idempotent)
    await db.execute(
        """
        INSERT INTO dpdp_grievance
          (grievance_id, employee_user_id, tenant_id, category, description, status, filed_at)
        VALUES ($1, $2, $3, $4, $5, 'OPEN', NOW())
        """,
        grievance_id, current.user_id,
        str(current.tenant_id) if current.tenant_id else None,
        body.category, body.description,
    )

    # WorkflowConsumer starts GrievanceWorkflow on seeing GRIEVANCE_FILED
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.publish("prana.ingest.events", {
            "event_type": "GRIEVANCE_FILED",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.utcnow().isoformat(),
            "grievance_id": grievance_id,
            "employee_user_id": str(current.user_id),
            "tenant_id": str(current.tenant_id) if current.tenant_id else None,
            "category": body.category,
            "description": body.description,
            "workflow_id": f"grievance-{grievance_id}",
        }, key=str(current.user_id))

    return {"grievance_id": grievance_id, "status": "OPEN", "sla_days": 30}


@router.get("/grievances")
async def list_grievances(db: DbConn, current=Employee):
    rows = await db.fetch(
        """
        SELECT grievance_id, category, description, status,
               filed_at, resolved_at, resolution_note
        FROM dpdp_grievance
        WHERE employee_user_id=$1
        ORDER BY filed_at DESC
        """,
        current.user_id,
    )
    return {
        "grievances": [
            {
                "grievance_id": str(r["grievance_id"]),
                "category": r["category"],
                "description": r["description"],
                "status": r["status"],
                "filed_at": r["filed_at"].isoformat() if r["filed_at"] else None,
                "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
                "resolution_note": r["resolution_note"],
            }
            for r in rows
        ]
    }
