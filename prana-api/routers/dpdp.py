"""
DPDP Act 2023 self-service endpoints — employee-facing.

Prefix: /dpdp

Endpoints:
  GET  /dpdp/consents                  — list per-purpose consent records
  POST /dpdp/consents/{id}/withdraw    — withdraw a specific consent purpose
  POST /dpdp/export                    — request full data export (triggers DataExportWorkflow)
  POST /dpdp/correction                — flag incorrect insight for correction review
  POST /dpdp/erasure                   — request account deletion (30-day cooling-off)
  POST /dpdp/grievance                 — file a formal DPDP grievance
  GET  /dpdp/grievances                — list employee's grievances

All routes require employee JWT. employee_user_id always from JWT claims — never from body.

HTTP handler contract (NEVER violate):
  validate → DB write → Kafka publish → return 2xx
  No direct Temporal calls in HTTP path except Temporal signals (targeting specific in-flight instances).
"""
import uuid
from messages import SuccessCode, success_response
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from dependencies import require_employee, DbConn
from errors import PranaError

log = logging.getLogger(__name__)
router = APIRouter()
Employee = Depends(require_employee)


# ── Consent — per-purpose records ────────────────────────────────────────────

CONSENT_PURPOSES = [
    ("document_processing", "Document processing and AI analysis"),
    ("insight_generation",  "Career insight and analytics generation"),
    ("peer_benchmark",      "Anonymous peer benchmarking (your data in aggregate)"),
    ("notifications",       "Push notifications and email alerts"),
]


@router.get("/consents")
async def list_consents(db: DbConn, current=Employee):
    """
    Returns per-purpose consent status.
    If no explicit record exists for a purpose, defaults to ACTIVE (implicit consent on registration).
    """
    rows = await db.fetch(
        """
        SELECT consent_id, purpose, consented_at, consent_version, is_active
        FROM employee_consent
        WHERE employee_user_id = $1
        ORDER BY consented_at DESC
        """,
        current.user_id,
    )
    existing_purposes = {r["purpose"]: r for r in rows}

    consents = []
    for purpose_key, purpose_label in CONSENT_PURPOSES:
        if purpose_key in existing_purposes:
            r = existing_purposes[purpose_key]
            consents.append({
                "id": str(r["consent_id"]),
                "purpose": purpose_key,
                "purpose_label": purpose_label,
                "consented_at": r["consented_at"].isoformat() if r["consented_at"] else None,
                "consent_version": r["consent_version"],
                "is_active": r["is_active"],
            })
        else:
            # Implicit active consent — no explicit record yet
            consents.append({
                "id": f"implicit-{purpose_key}",
                "purpose": purpose_key,
                "purpose_label": purpose_label,
                "consented_at": None,
                "consent_version": "implicit",
                "is_active": True,
            })

    return {"consents": consents}


@router.post("/consents/{consent_id}/withdraw", status_code=status.HTTP_200_OK)
async def withdraw_consent_purpose(
    consent_id: str,
    request: Request,
    db: DbConn,
    current=Employee,
):
    """
    Withdraw consent for a specific purpose.
    If consent is implicit (no DB record), creates a WITHDRAWN record.
    """
    if consent_id.startswith("implicit-"):
        purpose = consent_id.removeprefix("implicit-")
        valid_purposes = [p for p, _ in CONSENT_PURPOSES]
        if purpose not in valid_purposes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PranaError.INVALID_PURPOSE)
        await db.execute(
            """
            INSERT INTO employee_consent
              (consent_id, employee_user_id, purpose, consent_version, is_active, consented_at)
            VALUES (gen_random_uuid(), $1, $2, 'withdrawn-explicit', FALSE, NOW())
            ON CONFLICT (employee_user_id, purpose) DO UPDATE
              SET is_active = FALSE, updated_at = NOW()
            """,
            current.user_id, purpose,
        )
    else:
        row = await db.fetchrow(
            "SELECT employee_user_id FROM employee_consent WHERE consent_id=$1",
            uuid.UUID(consent_id),
        )
        if not row or str(row["employee_user_id"]) != str(current.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.NOT_FOUND)
        await db.execute(
            "UPDATE employee_consent SET is_active=FALSE, updated_at=NOW() WHERE consent_id=$1",
            uuid.UUID(consent_id),
        )
        purpose = consent_id

    # Publish audit event via Kafka (AuditConsumer writes to audit_event table)
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.compliance_event({
            "event_type": "CONSENT_WITHDRAWN",
            "employee_user_id": str(current.user_id),
            "tenant_id": str(current.tenant_id) if current.tenant_id else None,
            "purpose": purpose,
        })

    return {"message": SuccessCode.CONSENT_WITHDRAWN, "purpose": purpose}


# ── Data export ───────────────────────────────────────────────────────────────

@router.post("/export", status_code=status.HTTP_202_ACCEPTED)
async def request_export(request: Request, db: DbConn, current=Employee):
    """
    Trigger DataExportWorkflow — packages all documents + insights as encrypted ZIP.
    DPDP mandates delivery within 30 days; PRANA targets <24 hours.

    HTTP contract: validate → DB write → Kafka publish (WorkflowConsumer starts workflow) → 202.
    """
    job_id = str(uuid.uuid4())

    await db.execute(
        """
        INSERT INTO data_export_request
          (export_id, employee_user_id, tenant_id, status, requested_at)
        VALUES ($1, $2, $3, 'PENDING', NOW())
        """,
        uuid.UUID(job_id),
        current.user_id,
        current.tenant_id,
    )

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.compliance_event({
            "event_type": "DATA_EXPORT_REQUESTED",
            "export_id": job_id,
            "employee_user_id": str(current.user_id),
            "tenant_id": str(current.tenant_id) if current.tenant_id else None,
            "workflow_id": f"export-{current.user_id}-{job_id}",
        })

    return {
        "job_id": job_id,
        "message": SuccessCode.EXPORT_REQUESTED,
    }


# ── Data correction ───────────────────────────────────────────────────────────

class CorrectionIn(BaseModel):
    field: str = Field(..., min_length=1, max_length=100, description="Insight field name (e.g. designation, department)")
    current_value: Optional[str] = Field(None, max_length=500, description="Current (incorrect) value as shown in PRANA")
    correct_value: str = Field(..., min_length=1, max_length=500, description="Correct value")
    evidence_note: Optional[str] = Field(None, max_length=1000, description="Additional context or evidence")


@router.post("/correction", status_code=status.HTTP_201_CREATED)
async def request_correction(
    body: CorrectionIn,
    request: Request,
    db: DbConn,
    current=Employee,
):
    """
    Employee flags incorrect insight data for manual review.
    Triggers DataCorrectionWorkflow — OA-Admin reviews and applies correction.
    DPDP Act 2023 mandates correction within 30 days.
    """
    correction_id = str(uuid.uuid4())

    await db.execute(
        """
        INSERT INTO data_correction_request
          (correction_id, employee_user_id, tenant_id, field_name,
           current_value, correct_value, evidence_note, status, requested_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, 'PENDING', NOW())
        """,
        uuid.UUID(correction_id),
        current.user_id,
        current.tenant_id,
        body.field,
        body.current_value,
        body.correct_value,
        body.evidence_note,
    )

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.compliance_event({
            "event_type": "DATA_CORRECTION_REQUESTED",
            "correction_id": correction_id,
            "employee_user_id": str(current.user_id),
            "tenant_id": str(current.tenant_id) if current.tenant_id else None,
            "field": body.field,
            "correct_value": body.correct_value,
        })

    return {
        "correction_id": correction_id,
        "status": "PENDING",
        "message": SuccessCode.CORRECTION_REQUESTED,
    }


# ── Erasure ───────────────────────────────────────────────────────────────────

class ErasureIn(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


@router.post("/erasure", status_code=status.HTTP_202_ACCEPTED)
async def request_erasure(
    body: ErasureIn,
    request: Request,
    db: DbConn,
    current=Employee,
):
    """
    Start 30-day erasure cooling-off window. Employee can cancel within 30 days.
    After 30 days with no cancellation: ErasureConfirmationWorkflow hard-deletes all data.
    DPDP Act 2023 requires execution within 30 days of confirmed request.
    """
    # Check if erasure already pending
    existing = await db.fetchrow(
        """
        SELECT erasure_id FROM erasure_request
        WHERE employee_user_id=$1 AND status='PENDING'
        """,
        current.user_id,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=PranaError.ERASURE_ALREADY_PENDING,
        )

    erasure_id = str(uuid.uuid4())
    await db.execute(
        """
        INSERT INTO erasure_request
          (erasure_id, employee_user_id, tenant_id, reason, status, requested_at)
        VALUES ($1, $2, $3, $4, 'PENDING', NOW())
        """,
        uuid.UUID(erasure_id),
        current.user_id,
        current.tenant_id,
        body.reason,
    )

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.compliance_event({
            "event_type": "ERASURE_REQUESTED",
            "erasure_id": erasure_id,
            "employee_user_id": str(current.user_id),
            "tenant_id": str(current.tenant_id) if current.tenant_id else None,
            "reason": body.reason,
            "workflow_id": f"erasure-{current.user_id}",
        })

    return {
        "erasure_id": erasure_id,
        "message": SuccessCode.ERASURE_REQUESTED,
        "cancel_before_days": 30,
    }


@router.get("/erasure", status_code=status.HTTP_200_OK)
async def get_erasure_status(db: DbConn, current=Employee):
    """Check if an erasure request is pending and how many days remain."""
    row = await db.fetchrow(
        """
        SELECT erasure_id, status, requested_at, confirmed_at, completed_at
        FROM erasure_request
        WHERE employee_user_id=$1
        ORDER BY requested_at DESC
        LIMIT 1
        """,
        current.user_id,
    )
    if not row:
        return {"pending": False}
    import datetime
    days_remaining = None
    if row["status"] == "PENDING":
        elapsed = (datetime.datetime.now(datetime.timezone.utc) - row["requested_at"]).days
        sla_days_raw = await db.fetchval(
            "SELECT config_value FROM platform_config WHERE config_key='dpdp_erasure_confirmation_days'"
        )
        sla_days = int(sla_days_raw) if sla_days_raw else 30
        days_remaining = max(0, sla_days - elapsed)
    return {
        "pending": row["status"] == "PENDING",
        "erasure_id": str(row["erasure_id"]),
        "status": row["status"],
        "requested_at": row["requested_at"].isoformat() if row["requested_at"] else None,
        "days_remaining": days_remaining,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
    }


@router.post("/erasure/cancel", status_code=status.HTTP_200_OK)
async def cancel_erasure(request: Request, db: DbConn, current=Employee):
    """Signal ErasureConfirmationWorkflow to cancel — must be within cooling-off window."""
    row = await db.fetchrow(
        "SELECT erasure_id FROM erasure_request WHERE employee_user_id=$1 AND status='PENDING'",
        current.user_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.NO_PENDING_ERASURE)

    temporal = getattr(request.app.state, "temporal_client", None)
    if temporal:
        try:
            handle = temporal.get_workflow_handle(f"erasure-{current.user_id}")
            await handle.signal("cancel_erasure")
        except Exception as exc:
            log.warning("Could not signal ErasureConfirmationWorkflow: %s", exc)

    await db.execute(
        "UPDATE erasure_request SET status='CANCELLED', updated_at=NOW() WHERE employee_user_id=$1 AND status='PENDING'",
        current.user_id,
    )
    return {"message": SuccessCode.ERASURE_CANCELLED}


# ── Grievance ─────────────────────────────────────────────────────────────────

class GrievanceIn(BaseModel):
    subject: str = Field(..., min_length=3, max_length=120)
    description: str = Field(..., min_length=10, max_length=2000)


@router.post("/grievance", status_code=status.HTTP_201_CREATED)
async def file_grievance(
    body: GrievanceIn,
    request: Request,
    db: DbConn,
    current=Employee,
):
    """
    File a DPDP grievance. PRANA Grievance Officer must respond within 30 days.
    GrievanceWorkflow starts via WorkflowConsumer from Kafka event.
    """
    grievance_id = str(uuid.uuid4())

    await db.execute(
        """
        INSERT INTO dpdp_grievance
          (grievance_id, employee_user_id, tenant_id, grievance_type, category, description, status, raised_at)
        VALUES ($1, $2, $3, 'OTHER', 'GENERAL', $4, 'RAISED', NOW())
        """,
        uuid.UUID(grievance_id),
        current.user_id,
        current.tenant_id,
        f"{body.subject}\n\n{body.description}",
    )

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.compliance_event({
            "event_type": "GRIEVANCE_FILED",
            "grievance_id": grievance_id,
            "employee_user_id": str(current.user_id),
            "tenant_id": str(current.tenant_id) if current.tenant_id else None,
            "subject": body.subject,
        })

    return {
        "grievance_id": grievance_id,
        "status": "RAISED",
        "message": SuccessCode.GRIEVANCE_SUBMITTED,
        "sla_days": 30,
    }


@router.get("/grievances")
async def list_grievances(db: DbConn, current=Employee):
    rows = await db.fetch(
        """
        SELECT grievance_id, grievance_type, category, description, status,
               raised_at, acknowledged_at, resolved_at, resolution_note, dpb_escalated
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
                "grievance_type": r["grievance_type"],
                "category": r["category"],
                "description": r["description"],
                "status": r["status"],
                "raised_at": r["raised_at"].isoformat() if r["raised_at"] else None,
                "acknowledged_at": r["acknowledged_at"].isoformat() if r["acknowledged_at"] else None,
                "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
                "resolution_note": r["resolution_note"],
                "dpb_escalated": r["dpb_escalated"],
            }
            for r in rows
        ]
    }
