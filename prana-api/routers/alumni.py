"""
Alumni Network router.

Employee endpoints  — /v1/alumni/...      (requires employee JWT)
CHRO/OA endpoints  — /v1/alumni/org/...   (requires OA JWT, CHRO or OA-Admin role)

Consent model:
  Employee grants consent PER past employer via alumni_consent table.
  When granted: CHRO sees full name + contact details (mobile/email if employee allows).
  CHRO can download CSV with all consented alumni for direct outreach via email/WhatsApp/call.
  In-app outreach messages are supplementary — primary contact is direct.

Privacy:
  PAN is never in any response.
  mobile/email only in CHRO response when employee set share_mobile/share_email = TRUE.
  Withdrawn consent → employee disappears from CHRO list immediately.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from db import get_db
from kafka.producer import get_kafka_producer
from config import settings
from services.alumni_service import AlumniService

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_employee_jwt(authorization: Annotated[str | None, Header()] = None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="MISSING_TOKEN")
    from auth_utils import decode_jwt
    claims = decode_jwt(authorization.removeprefix("Bearer "))
    if claims.get("role") != "employee":
        raise HTTPException(status_code=403, detail="EMPLOYEE_ONLY")
    return claims

def _require_chro_jwt(authorization: Annotated[str | None, Header()] = None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="MISSING_TOKEN")
    from auth_utils import decode_jwt
    claims = decode_jwt(authorization.removeprefix("Bearer "))
    if claims.get("role") not in ("CHRO", "OA-Admin"):
        raise HTTPException(status_code=403, detail="CHRO_OR_ADMIN_REQUIRED")
    return claims

async def _alumni_service(db=Depends(get_db), kafka=Depends(get_kafka_producer)):
    return AlumniService(db=db, kafka=kafka, config={
        "outreach_max_per_month": settings.alumni_outreach_max_per_month,
    })


# ── Employee: per-org consent management ──────────────────────────────────────

class PerOrgConsentBody(BaseModel):
    tenant_id:    str
    granted:      bool
    share_mobile: bool = True
    share_email:  bool = True

@router.get("/employers")
async def list_past_employers(
    claims: dict = Depends(_require_employee_jwt),
    svc:    AlumniService = Depends(_alumni_service),
):
    """
    Employee sees all past employers with their current alumni consent status for each.
    Used to drive the per-org consent toggles in the mobile app.
    """
    return await svc.list_past_employers(employee_user_id=claims["sub"])

@router.post("/consent")
async def set_per_org_consent(
    body:   PerOrgConsentBody,
    claims: dict = Depends(_require_employee_jwt),
    svc:    AlumniService = Depends(_alumni_service),
):
    """
    Employee grants or withdraws alumni consent for a specific past employer.
    share_mobile / share_email control which contact details the CHRO can see.
    """
    result = await svc.set_per_org_consent(
        employee_user_id=claims["sub"],
        tenant_id=body.tenant_id,  # noqa: SEC-03 — employee targets a past employer's tenant, not their own
        granted=body.granted,
        share_mobile=body.share_mobile,
        share_email=body.share_email,
    )
    if result.get("error") == "NOT_A_PAST_EMPLOYER":
        raise HTTPException(422, detail="NOT_A_PAST_EMPLOYER")
    return result


# ── Employee: outreach inbox ───────────────────────────────────────────────────

@router.get("/outreach")
async def list_employee_outreach(
    limit:  int = Query(default=20, le=100),
    offset: int = Query(default=0,  ge=0),
    claims: dict = Depends(_require_employee_jwt),
    svc:    AlumniService = Depends(_alumni_service),
):
    return await svc.list_employee_outreach(
        employee_user_id=claims["sub"],
        limit=limit,
        offset=offset,
    )

@router.post("/outreach/{outreach_id}/read")
async def mark_outreach_read(
    outreach_id: str,
    claims: dict = Depends(_require_employee_jwt),
    svc:    AlumniService = Depends(_alumni_service),
):
    await svc.mark_outreach_read(employee_user_id=claims["sub"], outreach_id=outreach_id)
    return {"status": "READ"}


class OutreachReplyBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)

@router.post("/outreach/{outreach_id}/reply")
async def reply_to_outreach(
    outreach_id: str,
    payload:     OutreachReplyBody,
    claims: dict = Depends(_require_employee_jwt),
    svc:    AlumniService = Depends(_alumni_service),
):
    """Employee replies to an in-app outreach message from a past employer's CHRO."""
    await svc.reply_to_outreach(
        employee_user_id=claims["sub"],
        outreach_id=outreach_id,
        reply_body=payload.body,
    )
    return {"status": "REPLIED"}


# ── CHRO: alumni list + contact details + CSV download ────────────────────────

@router.get("/org/list")
async def list_alumni(
    limit:                int        = Query(default=50, le=200),
    offset:               int        = Query(default=0,  ge=0),
    city:                 str | None = Query(default=None),
    designation_contains: str | None = Query(default=None),
    min_tenure_months:    int | None = Query(default=None),
    claims: dict = Depends(_require_chro_jwt),
    svc:    AlumniService = Depends(_alumni_service),
):
    """
    CHRO sees all alumni who have granted consent for this org.
    Includes full_name, designation, dept, grade, city, DOJ, DOL.
    mobile/email present only when employee set share_mobile/share_email = TRUE.
    """
    return await svc.list_alumni(
        tenant_id=claims["tenant_id"],
        limit=limit,
        offset=offset,
        city=city,
        designation_contains=designation_contains,
        min_tenure_months=min_tenure_months,
    )

@router.get("/org/download")
async def download_alumni_csv(
    city:                 str | None = Query(default=None),
    designation_contains: str | None = Query(default=None),
    min_tenure_months:    int | None = Query(default=None),
    claims: dict = Depends(_require_chro_jwt),
    svc:    AlumniService = Depends(_alumni_service),
):
    """
    CSV export: Full Name, Designation, Department, Grade, City,
    DOJ, DOL, Mobile (if shared), Email (if shared), Tenure, Time Since Exit.
    CHRO downloads this and reaches out directly via email/WhatsApp/call.
    """
    csv_content = await svc.download_alumni_csv(
        tenant_id=claims["tenant_id"],
        city=city,
        designation_contains=designation_contains,
        min_tenure_months=min_tenure_months,
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=alumni_network.csv"},
    )


# ── CHRO: in-app outreach messages (supplementary) ───────────────────────────

class OutreachBody(BaseModel):
    employee_uuid: str
    subject:       str = Field(min_length=3,  max_length=200)
    body_text:     str = Field(min_length=10, max_length=2000)

@router.post("/org/outreach")
async def send_outreach(
    body:   OutreachBody,
    claims: dict = Depends(_require_chro_jwt),
    svc:    AlumniService = Depends(_alumni_service),
):
    result = await svc.send_outreach(
        tenant_id=claims["tenant_id"],
        oa_user_id=claims["sub"],
        employee_uuid=body.employee_uuid,
        subject=body.subject,
        body_text=body.body_text,
    )
    error = result.get("error")
    if error == "ALUMNI_NOT_FOUND":
        raise HTTPException(404, detail="ALUMNI_NOT_FOUND")
    if error == "ALUMNI_NO_CONSENT":
        raise HTTPException(403, detail="ALUMNI_NO_CONSENT")
    if error == "EMPLOYEE_STILL_ACTIVE":
        raise HTTPException(422, detail="EMPLOYEE_STILL_ACTIVE")
    if error == "OUTREACH_RATE_LIMIT":
        raise HTTPException(429, detail=f"OUTREACH_RATE_LIMIT_{result['limit']}_PER_30_DAYS")
    return result

@router.get("/org/outreach")
async def list_sent_outreach(
    employee_uuid: str | None = Query(default=None),
    limit:         int        = Query(default=50, le=200),
    offset:        int        = Query(default=0,  ge=0),
    claims: dict = Depends(_require_chro_jwt),
    svc:    AlumniService = Depends(_alumni_service),
):
    return await svc.list_sent_outreach(
        tenant_id=claims["tenant_id"],
        employee_uuid=employee_uuid,
        limit=limit,
        offset=offset,
    )
