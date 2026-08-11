"""
Portal Admin (PA) endpoints — account, identity & exception admin.
Split 2026-08-10 out of pa_admin.py (see that file's docstring). Covers:
OA emergency override, employee TOTP/password reset, employee record merge,
PA account unlock, storage requests, pipeline health, platform exception overview.
"""
import uuid
from messages import SuccessCode, success_response
import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from dependencies import DbConn, require_pa
from errors import PranaError
from services.encryption_service import compute_mobile_token

router = APIRouter()
PA = Depends(require_pa)

# ── OA Emergency Override ─────────────────────────────────────────────────────

class OaEmergencyIn(BaseModel):
    email: Optional[str] = None
    tenant_domain: str
    reason: str


class PaUnlockIn(BaseModel):
    email: str


# Controlled vocabulary for PA override actions — mirrors account_status_event's
# reason_code (NOT NULL, from a fixed set) + reason_note (optional free elaboration)
# pattern instead of a single unstructured free-text field, so overrides are
# actually filterable/reportable in the audit trail.
OVERRIDE_REASON_CODES = {
    "SUPPORT_ESCALATION",
    "EMPLOYEE_LOST_DEVICE",
    "SECURITY_INCIDENT",
    "COMPLIANCE_REQUEST",
    "OTHER",
}


def _validate_override_reason(reason_code: Optional[str], reason_note: Optional[str]) -> tuple[str, Optional[str]]:
    code = (reason_code or "").strip()
    if not code:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PranaError.OVERRIDE_REASON_REQUIRED)
    if code not in OVERRIDE_REASON_CODES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PranaError.INVALID_REASON_CODE)
    note = (reason_note or "").strip() or None
    if code == "OTHER" and not note:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PranaError.REASON_NOTE_REQUIRED_FOR_OTHER)
    return code, note


class ResetEmployeeTotpIn(BaseModel):
    identifier: str   # employee's email or mobile (E.164 or bare 10-digit)
    reason_code: str
    reason_note: Optional[str] = None


class ResetEmployeePasswordIn(BaseModel):
    identifier: str   # employee's email or mobile (E.164 or bare 10-digit)
    reason_code: str
    reason_note: Optional[str] = None


class MergeEmployeesIn(BaseModel):
    duplicate_identifier: str   # email or mobile of the duplicate (to be absorbed) record
    canonical_identifier: str   # email or mobile of the canonical (surviving) record
    reason: str


# Every table with a column referencing employee_user(employee_user_id) directly
# (tables keyed by employee_master.employee_uuid instead — document, career_event's
# employee_uuid column, employee_master_history, exception_queue — are untouched:
# employee_master itself is re-pointed here, so employee_uuid values never change).
_MERGE_REPOINT_TABLES = [
    ("employee_master", "employee_user_id"),
    ("career_event", "employee_user_id"),
    ("device_credential", "employee_user_id"),
    ("share_token", "employee_user_id"),
    ("document_access_log", "employee_user_id"),
    ("employee_consent", "employee_user_id"),
    ("erasure_request", "employee_user_id"),
    ("data_export_request", "employee_user_id"),
    ("data_correction_request", "employee_user_id"),
    ("dpdp_grievance", "employee_user_id"),
    ("oa_user", "linked_employee_user_id"),
]


def _normalise_identifier(raw: str) -> tuple[str, str]:
    """Return (column_name, value) for a mobile or email identifier."""
    raw = raw.strip()
    if "@" in raw:
        return "email", raw.lower()
    digits = raw.replace("+91", "").replace(" ", "").replace("-", "")
    if len(digits) == 10 and digits[0] in "6789":
        return "mobile", f"+91{digits}"
    return "mobile", raw   # pass through, DB will reject


@router.post("/oa-emergency/create")
async def oa_emergency_create(body: OaEmergencyIn, request: Request, db: DbConn, current=PA):
    tenant = await db.fetchrow("SELECT tenant_id FROM tenant WHERE domain=$1", body.tenant_domain)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.TENANT_NOT_FOUND)

    import secrets, string
    temp_pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))

    from services.encryption_service import hash_password
    await db.execute(
        """
        INSERT INTO oa_user (tenant_id, email, role, temp_password_hash, force_reset)
        VALUES ($1,$2,'oa_admin',$3,TRUE)
        """,
        tenant["tenant_id"], body.email or f"emergency@{body.tenant_domain}",
        hash_password(temp_pw),
    )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.tenant_event({
            "event_type": "PA_EMERGENCY_OVERRIDE",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tenant_id": str(tenant["tenant_id"]),
            "actor_id": str(current.user_id),
            "actor_type": "PORTAL_ADMIN",
            "action": "create",
            "reason": body.reason,
        })
    return {"message": SuccessCode.EMERGENCY_ACCOUNT_CREATED, "temp_password": temp_pw}


@router.post("/oa-emergency/suspend")
async def oa_emergency_suspend(body: OaEmergencyIn, db: DbConn, current=PA):
    tenant = await db.fetchrow("SELECT tenant_id FROM tenant WHERE domain=$1", body.tenant_domain)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.TENANT_NOT_FOUND)

    await db.execute(
        "UPDATE oa_user SET status='INACTIVE' WHERE email=$1 AND tenant_id=$2",
        body.email, tenant["tenant_id"],
    )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.tenant_event({
            "event_type": "PA_EMERGENCY_OVERRIDE",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tenant_id": str(tenant["tenant_id"]),
            "actor_id": str(current.user_id),
            "actor_type": "PORTAL_ADMIN",
            "action": "suspend",
            "reason": body.reason,
        })
    return {"message": SuccessCode.ACCOUNT_SUSPENDED}


@router.post("/oa-emergency/reset")
async def oa_emergency_reset(body: OaEmergencyIn, db: DbConn, current=PA):
    tenant = await db.fetchrow("SELECT tenant_id FROM tenant WHERE domain=$1", body.tenant_domain)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.TENANT_NOT_FOUND)

    import secrets, string
    temp_pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    from services.encryption_service import hash_password

    await db.execute(
        "UPDATE oa_user SET temp_password_hash=$1, force_reset=TRUE, status='ACTIVE' WHERE email=$2 AND tenant_id=$3",
        hash_password(temp_pw), body.email, tenant["tenant_id"],
    )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.tenant_event({
            "event_type": "PA_EMERGENCY_OVERRIDE",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tenant_id": str(tenant["tenant_id"]),
            "actor_id": str(current.user_id),
            "actor_type": "PORTAL_ADMIN",
            "action": "reset",
            "reason": body.reason,
        })
    return {"message": SuccessCode.ADMIN_PASSWORD_RESET, "temp_password": temp_pw}


# ── Employee TOTP reset (platform-wide override) ──────────────────────────────
# Departure from this file's usual "zero employee PII" boundary — deliberate,
# reason-required, matching the oa-emergency/* override pattern above.

@router.post("/employees/reset-totp")
async def pa_reset_employee_totp(body: ResetEmployeeTotpIn, request: Request, db: DbConn, current=PA):
    reason_code, reason_note = _validate_override_reason(body.reason_code, body.reason_note)

    identifier = body.identifier.strip()
    if not identifier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PranaError.IDENTIFIER_REQUIRED)

    col, value = _normalise_identifier(identifier)
    if col == "email":
        row = await db.fetchrow("SELECT employee_user_id FROM employee_user WHERE email = $1", value)
    else:
        mobile_token = compute_mobile_token(value, request.app.state.settings.platform_hmac_secret)
        row = await db.fetchrow("SELECT employee_user_id FROM employee_user WHERE mobile_token = $1", mobile_token)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EMPLOYEE_NOT_FOUND)

    employee_user_id = str(row["employee_user_id"])

    await db.execute(
        "UPDATE employee_user SET totp_secret_enc = NULL, totp_configured_at = NULL WHERE employee_user_id = $1",
        employee_user_id,
    )

    # Multi-org employees have one employee_master row per tenant — fan out one
    # audit event per affected tenant so every relevant tenant's CISO sees it.
    tenant_rows = await db.fetch(
        "SELECT DISTINCT tenant_id, employee_uuid FROM employee_master WHERE employee_user_id = $1",
        employee_user_id,
    )

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        for t in tenant_rows:
            await kafka.employee_event({
                "event_type":        "EMPLOYEE_TOTP_RESET",
                "tenant_id":         str(t["tenant_id"]),
                "actor_id":          str(current.user_id),
                "actor_type":        "PORTAL_ADMIN",
                "employee_user_id":  employee_user_id,
                "employee_uuid":     str(t["employee_uuid"]),
                "reason_code":       reason_code,
                "reason_note":       reason_note,
                "override":          True,
            })

    return {"message": SuccessCode.EMPLOYEE_TOTP_RESET}


@router.post("/employees/reset-password")
async def pa_reset_employee_password(body: ResetEmployeePasswordIn, request: Request, db: DbConn, current=PA):
    reason_code, reason_note = _validate_override_reason(body.reason_code, body.reason_note)

    identifier = body.identifier.strip()
    if not identifier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PranaError.IDENTIFIER_REQUIRED)

    col, value = _normalise_identifier(identifier)
    if col == "email":
        row = await db.fetchrow("SELECT employee_user_id FROM employee_user WHERE email = $1", value)
    else:
        mobile_token = compute_mobile_token(value, request.app.state.settings.platform_hmac_secret)
        row = await db.fetchrow("SELECT employee_user_id FROM employee_user WHERE mobile_token = $1", mobile_token)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EMPLOYEE_NOT_FOUND)

    employee_user_id = str(row["employee_user_id"])

    import secrets, string
    from services.password_service import hash_password
    temp_password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))

    await db.execute(
        "UPDATE employee_user SET password_hash = $2, force_reset = TRUE WHERE employee_user_id = $1",
        employee_user_id, hash_password(temp_password),
    )

    # Multi-org employees have one employee_master row per tenant — fan out one
    # audit event per affected tenant so every relevant tenant's CISO sees it.
    tenant_rows = await db.fetch(
        "SELECT DISTINCT tenant_id, employee_uuid FROM employee_master WHERE employee_user_id = $1",
        employee_user_id,
    )

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        for t in tenant_rows:
            await kafka.employee_event({
                "event_type":        "EMPLOYEE_PASSWORD_RESET",
                "tenant_id":         str(t["tenant_id"]),
                "actor_id":          str(current.user_id),
                "actor_type":        "PORTAL_ADMIN",
                "employee_user_id":  employee_user_id,
                "employee_uuid":     str(t["employee_uuid"]),
                "reason_code":       reason_code,
                "reason_note":       reason_note,
                "override":          True,
            })

    return {"message": SuccessCode.EMPLOYEE_PASSWORD_RESET, "temp_password": temp_password}


# ── Employee record merge/dedupe ──────────────────────────────────────────────
# PA-only, platform-wide: a PAN/NIK typo can create two employee_user rows for
# the same physical person. This merges the duplicate into a canonical record.

@router.post("/employees/merge")
async def merge_employee_records(body: MergeEmployeesIn, request: Request, db: DbConn, current=PA):
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PranaError.OVERRIDE_REASON_REQUIRED)

    hmac_secret = request.app.state.settings.platform_hmac_secret

    dup_col, dup_val = _normalise_identifier(body.duplicate_identifier)
    if dup_col == "email":
        dup_row = await db.fetchrow("SELECT employee_user_id FROM employee_user WHERE email = $1", dup_val)
    else:
        dup_row = await db.fetchrow(
            "SELECT employee_user_id FROM employee_user WHERE mobile_token = $1",
            compute_mobile_token(dup_val, hmac_secret),
        )
    if not dup_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EMPLOYEE_NOT_FOUND)

    can_col, can_val = _normalise_identifier(body.canonical_identifier)
    if can_col == "email":
        can_row = await db.fetchrow("SELECT employee_user_id FROM employee_user WHERE email = $1", can_val)
    else:
        can_row = await db.fetchrow(
            "SELECT employee_user_id FROM employee_user WHERE mobile_token = $1",
            compute_mobile_token(can_val, hmac_secret),
        )
    if not can_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EMPLOYEE_NOT_FOUND)

    duplicate_id = str(dup_row["employee_user_id"])
    canonical_id = str(can_row["employee_user_id"])
    if duplicate_id == canonical_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PranaError.CANNOT_MERGE_SAME_EMPLOYEE)

    async with db.transaction():
        for table, column in _MERGE_REPOINT_TABLES:
            sql = f"UPDATE {table} SET {column} = $1 WHERE {column} = $2"
            await db.execute(sql, canonical_id, duplicate_id)
        # Never delete the duplicate — mark it absorbed, keep the audit trail.
        await db.execute(
            "UPDATE employee_user SET status = 'MERGED', merged_into = $1 WHERE employee_user_id = $2",
            canonical_id, duplicate_id,
        )

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.employee_event({
            "event_type":                 "EMPLOYEE_RECORDS_MERGED",
            "actor_id":                   str(current.user_id),
            "actor_type":                 "PORTAL_ADMIN",
            "duplicate_employee_user_id": duplicate_id,
            "canonical_employee_user_id": canonical_id,
            "reason":                     reason,
        })

    return {"message": SuccessCode.EMPLOYEE_RECORDS_MERGED, "canonical_employee_user_id": canonical_id}


# ── PA account unlock ──────────────────────────────────────────────────────────
# auth_pa.py: PA lockout (3 failed TOTP attempts) is NOT auto-unlocked —
# it requires another PA to unlock manually.

@router.post("/pa-users/unlock")
async def pa_unlock(body: PaUnlockIn, request: Request, db: DbConn, current=PA):
    target = await db.fetchrow(
        "SELECT pa_id, status FROM portal_admin WHERE email=$1", body.email,
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.USER_NOT_FOUND)
    if target["status"] != "LOCKED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PranaError.ALREADY_UNLOCKED)

    event_id = uuid.uuid4()
    async with db.transaction():
        await db.execute(
            "UPDATE portal_admin SET status='ACTIVE', failed_totp_count=0 WHERE pa_id=$1",
            target["pa_id"],
        )
        await db.execute(
            """
            INSERT INTO account_status_event
              (event_id, event_type, user_type, user_id, from_status, to_status,
               reason_code, actor_type, actor_id, occurred_at)
            VALUES ($1, 'MANUAL_UNLOCK', 'pa', $2, 'LOCKED', 'ACTIVE',
                    'PA_MANUAL_UNLOCK', 'PORTAL_ADMIN', $3, NOW())
            """,
            event_id, target["pa_id"], current.user_id,
        )

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.security_event({
            "event_type": "ACCOUNT_UNLOCKED",
            "actor_id": str(current.user_id),
            "actor_type": "PORTAL_ADMIN",
            "target_account_id": str(target["pa_id"]),
        })
    return {"message": SuccessCode.LOCK_REMOVED}


# ── Storage requests ──────────────────────────────────────────────────────────

@router.get("/storage-requests")
async def list_storage_requests(db: DbConn, current=PA):
    rows = await db.fetch(
        """
        SELECT sr.request_id, sr.tenant_id, t.tenant_name,
               sr.current_gb, sr.requested_gb, sr.reason,
               sr.status, sr.requested_at
        FROM storage_request sr
        JOIN tenant t ON t.tenant_id = sr.tenant_id
        ORDER BY sr.requested_at DESC
        """
    )
    return {"requests": [
        {
            "request_id": str(r["request_id"]),
            "tenant_id": str(r["tenant_id"]),
            "tenant_name": r["tenant_name"],
            "current_gb": r["current_gb"],
            "requested_gb": r["requested_gb"],
            "reason": r["reason"],
            "status": r["status"],
            "requested_at": r["requested_at"].isoformat() if r["requested_at"] else None,
        }
        for r in rows
    ], "total": len(rows)}


@router.post("/storage-requests/{request_id}/approve")
async def approve_storage(request_id: str, db: DbConn, current=PA):
    await db.execute(
        "UPDATE storage_request SET status='APPROVED', decided_by=$2, decided_at=NOW() WHERE request_id=$1",
        request_id, current.user_id,
    )
    return {"message": SuccessCode.STORAGE_REQUEST_APPROVED}


@router.post("/storage-requests/{request_id}/reject")
async def reject_storage(request_id: str, db: DbConn, current=PA):
    await db.execute(
        "UPDATE storage_request SET status='REJECTED', decided_by=$2, decided_at=NOW() WHERE request_id=$1",
        request_id, current.user_id,
    )
    return {"message": SuccessCode.STORAGE_REQUEST_REJECTED}


@router.post("/storage-requests/{request_id}/hold")
async def hold_storage(request_id: str, db: DbConn, current=PA):
    await db.execute(
        "UPDATE storage_request SET status='ON_HOLD', decided_by=$2, decided_at=NOW() WHERE request_id=$1",
        request_id, current.user_id,
    )
    return {"message": SuccessCode.STORAGE_REQUEST_HELD}


# ── Pipeline health ───────────────────────────────────────────────────────────

@router.get("/pipeline-health")
async def pipeline_health(db: DbConn, current=PA):
    counts = await db.fetch(
        """
        SELECT pipeline_status, COUNT(*) AS cnt
        FROM document
        WHERE is_deleted = FALSE
        GROUP BY pipeline_status
        """
    )
    return {
        "counts": {r["pipeline_status"]: r["cnt"] for r in counts},
        "latency": {},   # populated from prana-ai metrics endpoint in production
    }


# ── Platform-wide exception overview ─────────────────────────────────────────

@router.post("/exceptions/{exception_id}/resolve")
async def pa_resolve_exception(exception_id: str, db: DbConn, current=PA):
    await db.execute(
        "UPDATE exception_queue SET status='RESOLVED', resolved_by=$2, resolved_at=NOW() "
        "WHERE exception_id=$1 AND status='OPEN'",
        exception_id, str(current.user_id),
    )
    return {"message": "Resolved"}


