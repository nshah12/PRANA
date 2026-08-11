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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from db import get_db
from dependencies import Employee, require_oa
from config import settings
from services.alumni_service import AlumniService
from services.encryption_service import resolve_platform_auth_kek_arn

logger = logging.getLogger(__name__)
router = APIRouter()

# Was a router-local `from auth_utils import decode_jwt` — that module doesn't
# exist anywhere in this codebase, so every request carrying a real Bearer
# token 500'd with ModuleNotFoundError (the only auth tests that existed only
# checked the no-token 401 path, which never reached that import). The role
# check was also comparing against the wrong casing ("CHRO"/"OA-Admin" instead
# of the real oa_user.role values — schema.sql's CHECK constraint is
# ('oa_operator','oa_admin','chro','cfo','ciso')). Fixed 2026-08-10 by
# switching to the standard dependencies.py DI chain every other router uses —
# see .claude/rules/frontend.md-adjacent note in prana-api/CLAUDE.md's Auth
# Middleware section, which names this exact anti-pattern (doc_manifest.py hit
# it first).
_CHRO = Depends(require_oa("chro", "oa_admin"))


async def _alumni_service(request: Request, db=Depends(get_db)):
    # Was Depends(get_kafka_producer) — kafka.producer's module-level singleton
    # getter, which raises RuntimeError until set_kafka_producer() runs at real
    # app startup. Every other router reads request.app.state.kafka_producer
    # instead (settable per-app, mockable in tests); found 2026-08-10 while
    # fixing this router's auth (the auth bug crashed before dependency
    # resolution ever reached this one, masking it).
    kafka = getattr(request.app.state, "kafka_producer", None)
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
    current: Employee,
    svc:    AlumniService = Depends(_alumni_service),
):
    """
    Employee sees all past employers with their current alumni consent status for each.
    Used to drive the per-org consent toggles in the mobile app.
    """
    return await svc.list_past_employers(employee_user_id=current.user_id)

@router.post("/consent")
async def set_per_org_consent(
    body:   PerOrgConsentBody,
    current: Employee,
    svc:    AlumniService = Depends(_alumni_service),
):
    """
    Employee grants or withdraws alumni consent for a specific past employer.
    share_mobile / share_email control which contact details the CHRO can see.
    """
    result = await svc.set_per_org_consent(
        employee_user_id=current.user_id,
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
    current: Employee,
    limit:  int = Query(default=20, le=100),
    offset: int = Query(default=0,  ge=0),
    svc:    AlumniService = Depends(_alumni_service),
):
    return await svc.list_employee_outreach(
        employee_user_id=current.user_id,
        limit=limit,
        offset=offset,
    )

@router.post("/outreach/{outreach_id}/read")
async def mark_outreach_read(
    outreach_id: str,
    current: Employee,
    svc:    AlumniService = Depends(_alumni_service),
):
    await svc.mark_outreach_read(employee_user_id=current.user_id, outreach_id=outreach_id)
    return {"status": "READ"}


class OutreachReplyBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)

@router.post("/outreach/{outreach_id}/reply")
async def reply_to_outreach(
    outreach_id: str,
    payload:     OutreachReplyBody,
    current: Employee,
    svc:    AlumniService = Depends(_alumni_service),
):
    """Employee replies to an in-app outreach message from a past employer's CHRO."""
    await svc.reply_to_outreach(
        employee_user_id=current.user_id,
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
    current=_CHRO,
    svc:    AlumniService = Depends(_alumni_service),
):
    """
    CHRO sees all alumni who have granted consent for this org.
    Includes full_name, designation, dept, grade, city, DOJ, DOL.
    mobile/email present only when employee set share_mobile/share_email = TRUE.
    """
    return await svc.list_alumni(
        tenant_id=current.tenant_id,
        limit=limit,
        offset=offset,
        city=city,
        designation_contains=designation_contains,
        min_tenure_months=min_tenure_months,
    )

@router.get("/org/download")
async def download_alumni_csv(
    request: Request,
    city:                 str | None = Query(default=None),
    designation_contains: str | None = Query(default=None),
    min_tenure_months:    int | None = Query(default=None),
    current=_CHRO,
    svc:    AlumniService = Depends(_alumni_service),
):
    """
    CSV export: Full Name, Designation, Department, Grade, City,
    DOJ, DOL, Mobile (if shared), Email (if shared), Tenure, Time Since Exit.
    CHRO downloads this and reaches out directly via email/WhatsApp/call.
    """
    csv_content = await svc.download_alumni_csv(
        tenant_id=current.tenant_id,
        city=city,
        designation_contains=designation_contains,
        min_tenure_months=min_tenure_months,
        kms=request.app.state.kms_service,
        auth_kek_arn=resolve_platform_auth_kek_arn(request.app.state.settings),
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
    current=_CHRO,
    svc:    AlumniService = Depends(_alumni_service),
):
    result = await svc.send_outreach(
        tenant_id=current.tenant_id,
        oa_user_id=current.user_id,
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
    current=_CHRO,
    svc:    AlumniService = Depends(_alumni_service),
):
    return await svc.list_sent_outreach(
        tenant_id=current.tenant_id,
        employee_uuid=employee_uuid,
        limit=limit,
        offset=offset,
    )
