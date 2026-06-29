"""
Public endpoints — no auth required.

Contact form:
  POST /public/contact               — submit a contact message

Org self-registration (3-step):
  POST /public/org-register/init     — step 1: collect email + basics, send OTP
  POST /public/org-register/verify   — step 2: verify OTP, get verified_token
  POST /public/org-register/complete — step 3: submit full form

PA read endpoints (auth required — Portal Admin only):
  GET  /public/contact-inquiries     — all contact submissions
  GET  /public/org-applications      — all self-registration applications
  PATCH /public/org-applications/{id} — mark reviewed / set status
"""
import hashlib
import random
import string
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
import asyncpg

from db import get_db as get_conn
from dependencies import PortalAdmin, DbConn
from lib.email import send_otp_email, send_contact_confirmation, send_pa_contact_alert

router = APIRouter(prefix="/public", tags=["public"])

OTP_TTL_MINUTES = 10


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gen_otp() -> str:
    return "".join(random.choices(string.digits, k=6))

def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


# ── Contact form ──────────────────────────────────────────────────────────────

class ContactIn(BaseModel):
    name:         str
    email:        EmailStr
    org:          str = ""
    enquiry_type: str = "General"
    message:      str = ""


@router.post("/contact", status_code=201)
async def submit_contact(
    body: ContactIn,
    request: Request,
    conn: asyncpg.Connection = Depends(get_conn),
):
    ip = request.client.host if request.client else None
    await conn.execute(
        """
        INSERT INTO contact_inquiry (name, email, org, enquiry_type, message, ip_address)
        VALUES ($1, $2, $3, $4, $5, $6::inet)
        """,
        body.name, body.email, body.org, body.enquiry_type, body.message, ip,
    )
    # Best-effort emails — do not block the response
    try:
        send_contact_confirmation(body.email, body.name, body.enquiry_type)
        send_pa_contact_alert(body.name, body.email, body.org, body.enquiry_type)
    except Exception:
        pass
    return {"status": "received"}


# ── Org self-registration ─────────────────────────────────────────────────────

class OrgRegisterInitIn(BaseModel):
    email:        EmailStr
    org_name:     str
    contact_name: str
    how_heard:    str = ""


class OrgRegisterVerifyIn(BaseModel):
    session_token: str    # UUID from init step
    otp:           str    # 6 digits entered by user


class OrgRegisterCompleteIn(BaseModel):
    verified_token: str   # UUID from verify step
    org_name:       str
    domain:         str
    entity_type:    str = ""
    industry:       str = ""
    headcount_band: str = ""
    contact_name:   str
    contact_email:  EmailStr
    contact_mobile: str = ""
    message:        str = ""
    how_heard:      str = ""
    agreed_to_dpa:  bool = False


@router.post("/org-register/init", status_code=200)
async def org_register_init(
    body: OrgRegisterInitIn,
    request: Request,
    conn: asyncpg.Connection = Depends(get_conn),
):
    """Step 1 — collect email + basics, send OTP."""
    # Rate-limit: max 3 pending OTPs per email (simple guard)
    count = await conn.fetchval(
        """
        SELECT COUNT(*) FROM org_registration_otp
        WHERE email = $1 AND verified = FALSE AND expires_at > NOW()
        """,
        body.email,
    )
    if count and int(count) >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests for this email. Please wait 10 minutes.",
        )

    otp = _gen_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)
    form_data = json.dumps({
        "org_name": body.org_name,
        "contact_name": body.contact_name,
        "how_heard": body.how_heard,
    })

    row = await conn.fetchrow(
        """
        INSERT INTO org_registration_otp (email, otp_hash, form_data, expires_at)
        VALUES ($1, $2, $3::jsonb, $4)
        RETURNING token
        """,
        body.email,
        _hash_otp(otp),
        form_data,
        expires_at,
    )

    try:
        send_otp_email(body.email, otp, body.org_name)
    except Exception:
        # In prod this should bubble — in dev the email is logged to console
        pass

    return {
        "session_token": str(row["token"]),
        "expires_in_minutes": OTP_TTL_MINUTES,
        "message": f"OTP sent to {body.email}",
    }


@router.post("/org-register/verify", status_code=200)
async def org_register_verify(
    body: OrgRegisterVerifyIn,
    conn: asyncpg.Connection = Depends(get_conn),
):
    """Step 2 — verify OTP, return a verified_token for step 3."""
    row = await conn.fetchrow(
        """
        SELECT token, email, otp_hash, form_data, expires_at, verified
        FROM org_registration_otp
        WHERE token = $1::uuid
        """,
        body.session_token,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Session not found. Please restart registration.")

    if row["verified"]:
        raise HTTPException(status_code=400, detail="OTP already used.")

    if row["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP expired. Please restart registration.")

    if row["otp_hash"] != _hash_otp(body.otp.strip()):
        raise HTTPException(status_code=400, detail="Incorrect code. Please try again.")

    # Mark as verified — the same token becomes the verified_token for step 3
    await conn.execute(
        "UPDATE org_registration_otp SET verified = TRUE WHERE token = $1::uuid",
        body.session_token,
    )
    return {
        "verified_token": body.session_token,
        "email": row["email"],
        "form_data": row["form_data"] if isinstance(row["form_data"], dict) else {},
    }


@router.post("/org-register/complete", status_code=201)
async def org_register_complete(
    body: OrgRegisterCompleteIn,
    conn: asyncpg.Connection = Depends(get_conn),
):
    """Step 3 — submit full application after email is verified."""
    row = await conn.fetchrow(
        """
        SELECT token, email, verified, expires_at
        FROM org_registration_otp
        WHERE token = $1::uuid AND verified = TRUE
        """,
        body.verified_token,
    )
    if not row:
        raise HTTPException(
            status_code=400,
            detail="Email verification required. Please complete the OTP step first.",
        )

    # Token expires 10 min after creation — verified session must be used promptly
    if row["expires_at"] < datetime.now(timezone.utc) - timedelta(minutes=30):
        raise HTTPException(status_code=400, detail="Verification session expired. Please restart.")

    if not body.agreed_to_dpa:
        raise HTTPException(status_code=400, detail="Data Processing Agreement acceptance is required.")

    app_id = await conn.fetchval(
        """
        INSERT INTO self_service_application
          (org_name, domain, entity_type, industry, headcount_band,
           contact_name, contact_email, contact_mobile,
           message, how_heard, agreed_to_dpa, email_verified)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,TRUE)
        RETURNING id
        """,
        body.org_name, body.domain, body.entity_type, body.industry, body.headcount_band,
        body.contact_name, body.contact_email, body.contact_mobile,
        body.message, body.how_heard, body.agreed_to_dpa,
    )

    # Clean up the OTP row
    await conn.execute(
        "DELETE FROM org_registration_otp WHERE token = $1::uuid",
        body.verified_token,
    )

    return {"status": "received", "application_id": str(app_id)}


# ── PA read endpoints ─────────────────────────────────────────────────────────

@router.get("/contact-inquiries", status_code=200)
async def list_contact_inquiries(
    current: PortalAdmin,
    conn: asyncpg.Connection = Depends(get_conn),
    page: int = 1,
    limit: int = 50,
):
    offset = (page - 1) * limit
    rows = await conn.fetch(
        """
        SELECT id, name, email, org, enquiry_type, message, status, submitted_at
        FROM contact_inquiry
        ORDER BY submitted_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit, offset,
    )
    total = await conn.fetchval("SELECT COUNT(*) FROM contact_inquiry")
    return {
        "total": total,
        "page": page,
        "items": [
            {
                "id":           str(r["id"]),
                "name":         r["name"],
                "email":        r["email"],
                "org":          r["org"],
                "enquiry_type": r["enquiry_type"],
                "message":      r["message"],
                "status":       r["status"],
                "submitted_at": r["submitted_at"].isoformat(),
            }
            for r in rows
        ],
    }


@router.get("/org-applications", status_code=200)
async def list_org_applications(
    current: PortalAdmin,
    conn: asyncpg.Connection = Depends(get_conn),
    page: int = 1,
    limit: int = 50,
    app_status: Optional[str] = None,
):
    offset = (page - 1) * limit
    where = "WHERE status = $3" if app_status else ""
    params: list = [limit, offset]
    if app_status:
        params.append(app_status)

    rows = await conn.fetch(
        f"""
        SELECT id, org_name, domain, entity_type, industry, headcount_band,
               contact_name, contact_email, contact_mobile,
               message, how_heard, agreed_to_dpa, email_verified,
               status, review_notes, submitted_at, reviewed_at
        FROM self_service_application
        {where}
        ORDER BY submitted_at DESC
        LIMIT $1 OFFSET $2
        """,
        *params,
    )
    total = await conn.fetchval(
        "SELECT COUNT(*) FROM self_service_application " + where,
        *params[2:],
    )
    return {
        "total": total,
        "page": page,
        "items": [dict(r) | {"id": str(r["id"]), "submitted_at": r["submitted_at"].isoformat()} for r in rows],
    }


class ReviewIn(BaseModel):
    status:       str            # REVIEWED | APPROVED | REJECTED
    review_notes: str = ""


@router.patch("/org-applications/{app_id}", status_code=200)
async def review_application(
    app_id: str,
    body: ReviewIn,
    current: PortalAdmin,
    conn: asyncpg.Connection = Depends(get_conn),
):
    await conn.execute(
        """
        UPDATE self_service_application
        SET status = $1, review_notes = $2, reviewed_at = NOW()
        WHERE id = $3::uuid
        """,
        body.status, body.review_notes, app_id,
    )
    return {"status": body.status}
