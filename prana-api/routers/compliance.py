"""
Compliance / DPDP Act 2023 employee-facing endpoints.

POST /vault/compliance/erasure          â€” request account deletion (triggers ErasureConfirmationWorkflow)
POST /vault/compliance/erasure/cancel   â€” cancel erasure during cooling-off window
POST /vault/compliance/export           â€” request data export (triggers DataExportWorkflow)
POST /vault/compliance/consent/withdraw â€” withdraw processing consent
POST /vault/compliance/consent/grant    â€” re-grant consent
POST /vault/compliance/grievance        â€” file a grievance
GET  /vault/compliance/grievances       â€” list employee's grievances

All routes require employee JWT. employee_user_id always from JWT claims.
"""
import uuid
import json
import logging
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from dependencies import require_employee, DbConn
from errors import PranaError

log = logging.getLogger(__name__)
router = APIRouter()
Employee = Depends(require_employee)


# â”€â”€ Erasure â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/erasure", status_code=status.HTTP_202_ACCEPTED)
async def request_erasure(request: Request, db: DbConn, current=Employee):
    """
    Start 30-day erasure cooling-off window.
    Triggers ErasureConfirmationWorkflow â€” employee can cancel within 30 days.
    """
    workflow_id = f"erasure-{current.user_id}"

    # WorkflowConsumer starts ErasureConfirmationWorkflow on seeing ERASURE_REQUESTED
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.compliance_event({
            "event_type": "ERASURE_REQUESTED",
            "employee_user_id": str(current.user_id),
            "tenant_id": str(current.tenant_id) if current.tenant_id else None,
            "workflow_id": workflow_id,
        })

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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.NO_PENDING_ERASURE)

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.compliance_event({
            "event_type": "ERASURE_CANCELLED",
            "employee_user_id": str(current.user_id),
            "tenant_id": str(current.tenant_id) if current.tenant_id else None,
        })
    return {"message": "Erasure cancelled. Your account is safe."}


# â”€â”€ Data export â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/export", status_code=status.HTTP_202_ACCEPTED)
async def request_export(request: Request, db: DbConn, current=Employee):
    """
    Trigger DataExportWorkflow â€” packages all metadata as encrypted ZIP.
    Download link delivered within 24 hours (DPDP mandates 30 days; we target <24h).
    """
    workflow_id = f"export-{current.user_id}-{uuid.uuid4().hex[:8]}"

    # WorkflowConsumer starts DataExportWorkflow on seeing DATA_EXPORT_REQUESTED
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.compliance_event({
            "event_type": "DATA_EXPORT_REQUESTED",
            "employee_user_id": str(current.user_id),
            "tenant_id": str(current.tenant_id) if current.tenant_id else None,
            "workflow_id": workflow_id,
        })

    return {
        "message": "Export request received. A download link will be sent to your registered number within 24 hours.",
        "workflow_id": workflow_id,
    }


# â”€â”€ Consent â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/consent/withdraw", status_code=status.HTTP_200_OK)
async def withdraw_consent(request: Request, db: DbConn, current=Employee):
    """
    Mark employee as having withdrawn processing consent.
    New documents pushed by employers will not be processed.
    """
    await db.execute(
        "UPDATE employee_user SET consent_status='WITHDRAWN' WHERE employee_user_id=$1",
        current.user_id,
    )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.compliance_event({
            "event_type": "CONSENT_WITHDRAWN",
            "employee_user_id": str(current.user_id),
            "tenant_id": str(current.tenant_id) if current.tenant_id else None,
        })
    return {"message": "Consent withdrawn. PRANA will not process new documents from your employers."}


@router.post("/consent/grant", status_code=status.HTTP_200_OK)
async def grant_consent(request: Request, db: DbConn, current=Employee):
    """Re-grant processing consent after a previous withdrawal."""
    await db.execute(
        "UPDATE employee_user SET consent_status='GRANTED' WHERE employee_user_id=$1",
        current.user_id,
    )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.compliance_event({
            "event_type": "CONSENT_GRANTED",
            "employee_user_id": str(current.user_id),
            "tenant_id": str(current.tenant_id) if current.tenant_id else None,
        })
    return {"message": "Consent granted. PRANA will process documents pushed by your employers."}


# â”€â”€ Consent status â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/consent")
async def get_consent_status(db: DbConn, current=Employee):
    row = await db.fetchrow(
        "SELECT consent_status FROM employee_user WHERE employee_user_id=$1",
        current.user_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    granted = row["consent_status"] == "GRANTED"
    return {
        "consent_granted": granted,
        "consent_status": row["consent_status"],
    }


# â”€â”€ Grievance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
    File a DPDP grievance. Triggers GrievanceWorkflow â€” 30-day SLA, escalates to PA on breach.
    """
    grievance_id = str(uuid.uuid4())

    # Write the row directly (workflow also calls open_grievance activity but idempotent)
    await db.execute(
        """
        INSERT INTO dpdp_grievance
          (grievance_id, employee_user_id, tenant_id, grievance_type, category, description, status, raised_at)
        VALUES ($1, $2, $3, $4, $4, $5, 'RAISED', NOW())
        """,
        grievance_id, current.user_id,
        str(current.tenant_id) if current.tenant_id else None,
        body.category, body.description,
    )

    # WorkflowConsumer starts GrievanceWorkflow on seeing GRIEVANCE_FILED
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.compliance_event({
            "event_type": "GRIEVANCE_FILED",
            "employee_user_id": str(current.user_id),
            "tenant_id": str(current.tenant_id) if current.tenant_id else None,
            "grievance_id": grievance_id,
            "category": body.category,
            "workflow_id": f"grievance-{grievance_id}",
        })

    return {"grievance_id": grievance_id, "status": "RAISED", "sla_days": 30}


@router.get("/grievances")
async def list_grievances(db: DbConn, current=Employee):
    rows = await db.fetch(
        """
        SELECT grievance_id, category, description, status,
               raised_at, resolved_at, resolution_note
        FROM dpdp_grievance
        WHERE employee_user_id=$1
        ORDER BY raised_at DESC
        LIMIT 100
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
                "filed_at": r["raised_at"].isoformat() if r["raised_at"] else None,
                "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
                "resolution_note": r["resolution_note"],
            }
            for r in rows
        ]
    }

