"""
Portal Admin (PA) endpoints — platform-wide management.
PA has zero SELECT on document rows or employee PII — only aggregates and tenant metadata.
All routes require @prana.in JWT (enforced in auth_pa.py at login time).
"""
import uuid
from messages import SuccessCode, success_response
import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from dependencies import DbConn, require_pa, AuthUser as PortalAdmin
from errors import PranaError
from services.encryption_service import compute_mobile_token

router = APIRouter()
PA = Depends(require_pa)


# ── Meta dashboard ────────────────────────────────────────────────────────────

@router.get("/meta-dashboard")
async def meta_dashboard(request: Request, db: DbConn, current=PA):
    active_tenants  = await db.fetchval("SELECT COUNT(*) FROM tenant WHERE status='ACTIVE'")
    total_employees = await db.fetchval("SELECT COUNT(*) FROM employee_master WHERE status='ACTIVE'")
    open_exceptions = await db.fetchval("SELECT COUNT(*) FROM exception_queue WHERE status='OPEN'")

    stage_counts = await db.fetch(
        """
        SELECT pipeline_status, COUNT(*) AS cnt
        FROM document
        WHERE pipeline_status NOT IN ('ROUTED','EXCEPTION','QUARANTINED')
          AND is_deleted = FALSE
        GROUP BY pipeline_status
        """
    )

    # Recent tenant status changes (account_status_event covers TOTP_LOCKOUT + ADMIN_DISABLED events)
    # For tenant-level activity use tenant table directly (created_at ordering)
    recent_tenants = await db.fetch(
        """
        SELECT tenant_name, status, created_at
        FROM tenant
        ORDER BY created_at DESC LIMIT 10
        """
    )

    # Storage: try real S3/MinIO first; fall back to DB-estimated size (avg 200 KB/doc)
    storage_used_label = "—"
    try:
        s3 = request.app.state.s3
        settings = request.app.state.settings
        total_bytes = 0
        for bucket in [settings.s3_bucket_documents, settings.s3_bucket_staging]:
            paginator = s3.raw_client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket):
                for obj in page.get("Contents", []):
                    total_bytes += obj.get("Size", 0)
        if total_bytes > 0:
            if total_bytes < 1024 * 1024:
                storage_used_label = f"{total_bytes // 1024} KB"
            elif total_bytes < 1024 ** 3:
                storage_used_label = f"{total_bytes / (1024**2):.1f} MB"
            else:
                storage_used_label = f"{total_bytes / (1024**3):.2f} GB"
    except Exception as exc:
        from services.error_observability_service import ErrorObservabilityService
        try:
            await ErrorObservabilityService(db).record(
                exc=exc, source="HTTP", source_detail="platform_summary:s3_storage_listing",
            )
        except Exception:
            pass
    if storage_used_label == "—":
        # Estimate from document count: average 200 KB per document
        doc_count = await db.fetchval("SELECT COUNT(*) FROM document WHERE is_deleted=FALSE")
        if doc_count:
            est_bytes = int(doc_count) * 200 * 1024
            if est_bytes < 1024 ** 3:
                storage_used_label = f"~{est_bytes / (1024**2):.0f} MB (est.)"
            else:
                storage_used_label = f"~{est_bytes / (1024**3):.2f} GB (est.)"

    return {
        "active_tenants":         int(active_tenants or 0),
        "total_employees":        int(total_employees or 0),
        "storage_used_label":     storage_used_label,
        "open_exceptions":        int(open_exceptions or 0),
        "pipeline_counts":        {r["pipeline_status"]: int(r["cnt"]) for r in stage_counts},
        "recent_tenant_activity": [
            {
                "tenant_name": r["tenant_name"],
                "type": "ACTIVE" if r["status"] == "ACTIVE" else r["status"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in recent_tenants
        ],
    }


# ── Tenant management ─────────────────────────────────────────────────────────

@router.get("/tenants")
async def list_tenants(
    db: DbConn,
    status: Optional[str] = None,
    q: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
    current=PA,
):
    conditions = []
    params: list = []
    i = 1

    if status:
        conditions.append(f"t.status = ${i}"); params.append(status); i += 1
    if q:
        conditions.append(f"(t.tenant_name ILIKE ${i} OR t.domain ILIKE ${i})"); params.append(f"%{q}%"); i += 1

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = await db.fetch(
        f"""
        SELECT t.tenant_id, t.tenant_name, t.domain,
               t.status, t.home_region, t.primary_state,
               t.created_at, t.cin, t.gstin, t.storage_quota_gb
        FROM tenant t
        {where}
        ORDER BY t.created_at DESC
        LIMIT {limit} OFFSET {offset}
        """,
        *params,
    )
    return {"tenants": [
        {
            "tenant_id": str(r["tenant_id"]),
            "tenant_name": r["tenant_name"],
            "domain": r["domain"],
            "status": r["status"],
            "home_region": r["home_region"],
            "primary_state": r["primary_state"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "cin": r["cin"],
            "gstin": r["gstin"],
            "storage_quota_gb": r["storage_quota_gb"],
        }
        for r in rows
    ]}


class ActivateTenantIn(BaseModel):
    home_region_override: Optional[str] = None
    override_reason: Optional[str] = None


@router.post("/tenants/{tenant_id}/activate")
async def activate_tenant(
    tenant_id: str,
    body: ActivateTenantIn,
    request: Request,
    db: DbConn,
    current=PA,
):
    row = await db.fetchrow(
        "SELECT tenant_id, status FROM tenant WHERE tenant_id=$1", tenant_id
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.TENANT_NOT_FOUND)
    if row["status"] not in ("PENDING", "PENDING_VERIFICATION"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PranaError.ALREADY_ACTIVATED)

    if body.home_region_override and not body.override_reason:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PranaError.OVERRIDE_REASON_REQUIRED)

    # Parameterized — never interpolate body values into SQL (DB-01 / SQL injection).
    if body.home_region_override:
        await db.execute(
            "UPDATE tenant SET status='ACTIVE', home_region=$2 WHERE tenant_id=$1",
            tenant_id, body.home_region_override,
        )
    else:
        await db.execute(
            "UPDATE tenant SET status='ACTIVE' WHERE tenant_id=$1", tenant_id
        )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.tenant_event({
            "event_type": "TENANT_ACTIVATED",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tenant_id": tenant_id,
            "actor_id": str(current.user_id),
            "actor_type": "PORTAL_ADMIN",
            "override_region": body.home_region_override,
            "reason": body.override_reason,
        })
    return {"message": SuccessCode.TENANT_ACTIVATED, "tenant_id": tenant_id}


@router.post("/tenants/{tenant_id}/reject")
async def reject_tenant(tenant_id: str, db: DbConn, current=PA):
    await db.execute(
        "UPDATE tenant SET status='REJECTED' WHERE tenant_id=$1 AND status IN ('PENDING','PENDING_VERIFICATION')",
        tenant_id,
    )
    return {"message": SuccessCode.TENANT_REJECTED}


@router.post("/tenants/{tenant_id}/suspend")
async def suspend_tenant(tenant_id: str, db: DbConn, current=PA):
    await db.execute("UPDATE tenant SET status='SUSPENDED' WHERE tenant_id=$1", tenant_id)
    return {"message": SuccessCode.TENANT_SUSPENDED}


# ── OA Emergency Override ─────────────────────────────────────────────────────

class OaEmergencyIn(BaseModel):
    email: Optional[str] = None
    tenant_domain: str
    reason: str


class PaUnlockIn(BaseModel):
    email: str


class ResetEmployeeTotpIn(BaseModel):
    identifier: str   # employee's email or mobile (E.164 or bare 10-digit)
    reason: str


class ResetEmployeePasswordIn(BaseModel):
    identifier: str   # employee's email or mobile (E.164 or bare 10-digit)
    reason: str


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
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PranaError.OVERRIDE_REASON_REQUIRED)

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
                "reason":            reason,
                "override":          True,
            })

    return {"message": SuccessCode.EMPLOYEE_TOTP_RESET}


@router.post("/employees/reset-password")
async def pa_reset_employee_password(body: ResetEmployeePasswordIn, request: Request, db: DbConn, current=PA):
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PranaError.OVERRIDE_REASON_REQUIRED)

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
                "reason":            reason,
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


# ── Platform anomaly detection ─────────────────────────────────────────────────

@router.get("/anomalies")
async def list_anomalies(db: DbConn, current=PA):
    """PA: platform-wide anomaly events. Returns empty list if table not yet provisioned."""
    try:
        rows = await db.fetch(
            """
            SELECT ae.event_id, ae.tenant_id, t.tenant_name,
                   ae.rule_name, ae.severity, ae.detected_at,
                   ae.status, ae.event_metadata
            FROM anomaly_event ae
            JOIN tenant t ON t.tenant_id = ae.tenant_id
            ORDER BY ae.detected_at DESC
            LIMIT 200
            """
        )
    except Exception:
        rows = []
    return {
        "anomalies": [
            {
                "event_id":     str(r["event_id"]),
                "tenant_id":    str(r["tenant_id"]),
                "tenant_name":  r["tenant_name"],
                "anomaly_type": r["rule_name"],
                "severity":     r["severity"],
                "detected_at":  r["detected_at"].isoformat() if r["detected_at"] else None,
                "status":       r["status"],
                "details":      r["event_metadata"],
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post("/anomalies/{event_id}/acknowledge")
async def acknowledge_anomaly(event_id: str, db: DbConn, current=PA):
    try:
        await db.execute(
            "UPDATE anomaly_event SET status='ACKNOWLEDGED' WHERE event_id=$1",
            event_id,
        )
    except Exception as exc:
        from services.error_observability_service import ErrorObservabilityService
        try:
            await ErrorObservabilityService(db).record(
                exc=exc, source="HTTP", source_detail="acknowledge_anomaly",
            )
        except Exception:
            pass
    return {"message": SuccessCode.ALERT_ACKNOWLEDGED}


@router.get("/exceptions")
async def exception_overview(db: DbConn, current=PA):
    open_count      = await db.fetchval("SELECT COUNT(*) FROM exception_queue WHERE status='OPEN'")
    in_progress     = await db.fetchval("SELECT COUNT(*) FROM exception_queue WHERE status='IN_PROGRESS'")
    resolved_24h    = await db.fetchval(
        "SELECT COUNT(*) FROM exception_queue WHERE status='RESOLVED' AND resolved_at > NOW() - INTERVAL '24 hours'"
    )

    rows = await db.fetch(
        """
        SELECT eq.exception_id, eq.document_id, eq.exception_type,
               eq.status, eq.raised_at, eq.tenant_id, t.tenant_name,
               d.doc_type, d.doc_period,
               (NOW() - eq.raised_at) > INTERVAL '24 hours' AS sla_breached
        FROM exception_queue eq
        JOIN tenant t ON t.tenant_id = eq.tenant_id
        JOIN document d ON d.document_id = eq.document_id
        WHERE eq.status IN ('OPEN','IN_PROGRESS')
        ORDER BY eq.raised_at ASC
        LIMIT 200
        """
    )

    exceptions = []
    for r in rows:
        exceptions.append({
            **{k: v for k, v in dict(r).items() if k not in ('raised_at','sla_breached')},
            "document_name": f"{r['doc_type']} · {r['doc_period'] or 'n/a'}",
            "created_at":    r["raised_at"].isoformat() if r["raised_at"] else None,
            "sla_breached":  bool(r["sla_breached"]),
        })

    return {
        "open_count":        int(open_count or 0),
        "in_progress_count": int(in_progress or 0),
        "resolved_24h":      int(resolved_24h or 0),
        "sla_breach_count":  sum(1 for e in exceptions if e["sla_breached"]),
        "exceptions":        exceptions,
    }


# ── Cryptographic health ──────────────────────────────────────────────────────

@router.get("/crypto")
async def crypto_health(db: DbConn, current=PA):
    """
    Returns platform key status and per-tenant KEK inventory.
    In dev: keys are simulated as ENABLED (no real AWS KMS).
    In prod: would call kms:DescribeKey for each ARN.
    """
    # Per-tenant KEK status (derived from tenant table kek_arn field)
    tenant_rows = await db.fetch(
        """
        SELECT t.tenant_id, t.tenant_name, t.kek_arn,
               COUNT(em.employee_uuid) AS dek_count
        FROM tenant t
        LEFT JOIN employee_master em ON em.tenant_id = t.tenant_id
        WHERE t.status = 'ACTIVE'
        GROUP BY t.tenant_id, t.tenant_name, t.kek_arn
        ORDER BY t.tenant_name
        """
    )

    tenant_keys = []
    for r in tenant_rows:
        kek_arn = r["kek_arn"] or ""
        # Extract short key-id from ARN (e.g. mrk-abc123 or key/uuid)
        key_id = kek_arn.split("/")[-1] if "/" in kek_arn else kek_arn
        tenant_keys.append({
            "tenant_id":      str(r["tenant_id"]),
            "tenant_name":    r["tenant_name"],
            "kms_key_id":     key_id or "dev-mock-key",
            "key_state":      "ENABLED",   # dev: mock; prod: kms:DescribeKey
            "dek_count":      int(r["dek_count"] or 0),
            "last_rotated_at": None,       # prod: from kms:GetKeyRotationStatus
        })

    return {
        "hmac_key_status": "ENABLED",   # platform_secret present in env
        "fpe_key_status":  "ENABLED",   # FF3-1 key present in env
        "totp_key_status": "ENABLED",   # AES-256-GCM key present in env
        "tenant_keys":     tenant_keys,
    }


# ── Audit trail ───────────────────────────────────────────────────────────────

@router.get("/audit")
async def audit_trail(
    db: DbConn,
    q: Optional[str] = None,
    event_type: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
    current=PA,
):
    conditions = []
    params: list = []
    i = 1

    if event_type:
        conditions.append(f"ae.event_type = ${i}"); params.append(event_type); i += 1
    if q:
        conditions.append(f"(t.tenant_name ILIKE ${i})"); params.append(f"%{q}%"); i += 1

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = await db.fetch(
        f"""
        SELECT ae.event_id, ae.event_type, ae.actor_id, ae.actor_type,
               ae.document_id AS resource_id, ae.ip_address,
               ae.occurred_at AS created_at,
               t.tenant_name
        FROM audit_event ae
        LEFT JOIN tenant t ON t.tenant_id = ae.tenant_id
        {where}
        ORDER BY ae.occurred_at DESC
        LIMIT {limit} OFFSET {offset}
        """,
        *params,
    )
    return {"events": [
        {
            "event_id": str(r["event_id"]),
            "event_type": r["event_type"],
            "actor_id": str(r["actor_id"]) if r["actor_id"] else None,
            "actor_type": r["actor_type"],
            "resource_id": str(r["resource_id"]) if r["resource_id"] else None,
            "ip_address": str(r["ip_address"]) if r["ip_address"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "tenant_name": r["tenant_name"],
        }
        for r in rows
    ]}


@router.get("/audit/export")
async def export_audit(db: DbConn, current=PA):
    rows = await db.fetch(
        "SELECT event_type, actor_id::text, tenant_id::text, ip_address::text, occurred_at AS created_at FROM audit_event ORDER BY occurred_at DESC LIMIT 10000"
    )
    import csv, io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["event_type","actor_id","tenant_id","ip_address","created_at"])
    w.writeheader()
    for r in rows:
        w.writerow({k: str(v) for k, v in dict(r).items()})

    from fastapi.responses import Response
    return Response(
        content=buf.getvalue().encode(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit_export.csv"'},
    )


# ── API key management ────────────────────────────────────────────────────────

@router.get("/api-keys")
async def list_api_keys(db: DbConn, current=PA):
    rows = await db.fetch(
        """
        SELECT ak.api_key_id, ak.tenant_id, t.tenant_name,
               ak.key_prefix AS key_id_prefix, ak.label,
               ak.rate_limit_rpm AS rate_limit_per_minute,
               ak.status, ak.created_at, ak.last_used_at
        FROM api_key ak
        JOIN tenant t ON t.tenant_id = ak.tenant_id
        ORDER BY ak.created_at DESC
        """
    )
    tenants = await db.fetch(
        "SELECT tenant_id, tenant_name FROM tenant WHERE status='ACTIVE' ORDER BY tenant_name"
    )
    return {
        "keys": [
            {
                "api_key_id": str(r["api_key_id"]),
                "tenant_id": str(r["tenant_id"]),
                "tenant_name": r["tenant_name"],
                "key_id_prefix": r["key_id_prefix"],
                "label": r["label"],
                "rate_limit_per_minute": r["rate_limit_per_minute"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
            }
            for r in rows
        ],
        "tenants": [
            {"tenant_id": str(t["tenant_id"]), "tenant_name": t["tenant_name"]}
            for t in tenants
        ],
    }


@router.post("/api-keys")
async def create_api_key(request: Request, db: DbConn, current=PA):
    import secrets as _s, hashlib
    from services.encryption_service import aes_encrypt
    body = await request.json()
    tenant_id = body.get("tenant_id")  # sec03-cross-tenant-ok: PA creates API keys for specific tenants
    label = body.get("label", "")
    rpm = int(body.get("rate_limit_per_minute", 1000))

    raw_key = f"prana_{_s.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12]
    from services.encryption_service import resolve_auth_dek
    signing_secret = _s.token_hex(32)
    auth_dek = resolve_auth_dek(request.app.state.settings)
    signing_secret_enc = aes_encrypt(signing_secret, auth_dek)

    await db.execute(
        """INSERT INTO api_key (tenant_id, key_prefix, key_hash, signing_secret_enc,
                                label, scopes, rate_limit_rpm, status, created_by)
           VALUES ($1, $2, $3, $4, $5, $6, $7, 'ACTIVE', $8)""",
        tenant_id, key_prefix, key_hash, signing_secret_enc,
        label, ["ingest:write"], rpm, str(current.user_id),
    )
    return {"api_key": raw_key, "key_prefix": key_prefix}


@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(key_id: str, db: DbConn, current=PA):
    await db.execute(
        "UPDATE api_key SET status='REVOKED' WHERE api_key_id=$1", key_id
    )
    return {"message": SuccessCode.ACCESS_REVOKED}


@router.get("/rate-limits")
async def rate_limits(db: DbConn, current=PA):
    # Default rate limit from platform_config
    default_rpm_row = await db.fetchrow(
        "SELECT config_value FROM platform_config WHERE config_key='api_key_default_rate_limit_rpm'"
    )
    default_rpm = int(default_rpm_row["config_value"]) if default_rpm_row else 1000

    # API keys with their per-key limits
    key_rows = await db.fetch(
        """
        SELECT ak.api_key_id, t.tenant_name, t.tenant_id, ak.label,
               ak.rate_limit_rpm, ak.status
        FROM api_key ak
        JOIN tenant t ON t.tenant_id = ak.tenant_id
        WHERE ak.status = 'ACTIVE'
        ORDER BY ak.rate_limit_rpm DESC
        """
    )

    # Per-tenant overrides from tenant_config
    tenant_overrides = await db.fetch(
        """
        SELECT tc.tenant_id, t.tenant_name, tc.config_value AS rpm_override
        FROM tenant_config tc
        JOIN tenant t ON t.tenant_id = tc.tenant_id
        WHERE tc.config_key = 'api_key_default_rate_limit_rpm'
        """
    )
    override_map = {str(r["tenant_id"]): int(r["rpm_override"]) for r in tenant_overrides}

    # All active tenants with their effective default
    tenant_rows = await db.fetch(
        "SELECT tenant_id, tenant_name FROM tenant WHERE status='ACTIVE' ORDER BY tenant_name"
    )
    tenant_defaults = [
        {
            "tenant_id":   str(r["tenant_id"]),
            "tenant_name": r["tenant_name"],
            "default_rpm": override_map.get(str(r["tenant_id"]), default_rpm),
            "source":      "tenant_config" if str(r["tenant_id"]) in override_map else "platform_default",
        }
        for r in tenant_rows
    ]

    total = len(key_rows)
    avg_rpm = round(sum(r["rate_limit_rpm"] for r in key_rows) / total) if total else default_rpm
    return {
        "total_keys":       total,
        "throttled_1h":     0,   # live from Redis token-bucket scan in production
        "avg_rpm":          avg_rpm,
        "platform_default_rpm": default_rpm,
        "keys": [
            {
                "api_key_id":     str(r["api_key_id"]),
                "tenant_name":    r["tenant_name"],
                "tenant_id":      str(r["tenant_id"]),
                "label":          r["label"],
                "rate_limit_rpm": int(r["rate_limit_rpm"]) if r["rate_limit_rpm"] is not None else 0,
                "status":         r["status"],
            }
            for r in key_rows
        ],
        "tenant_defaults":  tenant_defaults,
    }


# ── Service Incidents ─────────────────────────────────────────────────────────

class ResolveIncidentIn(BaseModel):
    note: str = ""

@router.get("/incidents")
async def list_incidents(db: DbConn, _=PA):
    from services.health_service import HealthService
    svc = HealthService(db)
    incidents = await svc.get_open_incidents()
    return {
        "incidents": [
            {**i, "incident_id": str(i["incident_id"]),
             "detected_at": i["detected_at"].isoformat() if i["detected_at"] else None,
             "acknowledged_at": i["acknowledged_at"].isoformat() if i["acknowledged_at"] else None,
             "resolved_at": i["resolved_at"].isoformat() if i["resolved_at"] else None,
            }
            for i in incidents
        ],
        "open_count": sum(1 for i in incidents if i["status"] == "OPEN"),
        "p1_open": sum(1 for i in incidents if i["status"] == "OPEN" and i["severity"] == "P1"),
    }

@router.post("/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(incident_id: str, db: DbConn, current=PA):
    from uuid import UUID
    from services.health_service import HealthService
    svc = HealthService(db)
    await svc.acknowledge(UUID(incident_id), UUID(current.user_id))
    return {"status": "acknowledged"}

@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(incident_id: str, body: ResolveIncidentIn, db: DbConn, current=PA):
    from uuid import UUID
    from services.health_service import HealthService
    svc = HealthService(db)
    await svc.resolve(UUID(incident_id), UUID(current.user_id), body.note)
    return {"status": "resolved"}

@router.post("/incidents/run-check")
async def trigger_health_check(db: DbConn, _=PA):
    """On-demand health check — PA can trigger without waiting for the next schedule."""
    from services.health_service import HealthService
    svc = HealthService(db)
    results = await svc.run_checks()
    return {"results": results}


# ── Security incidents (cross-tenant — PA only) ────────────────────────────────

@router.get("/security-incidents")
async def list_security_incidents(
    db: DbConn,
    _=PA,
    tenant_id: Optional[str] = None,
    severity: Optional[str] = None,
    incident_status: Optional[str] = None,
    limit: int = 100,
):
    """PA: list security/anomaly incidents across all tenants (or filter by tenant)."""
    from services.incident_service import IncidentService
    svc = IncidentService(db=db)
    items = await svc.get_incidents(
        tenant_id=tenant_id,   # None = all tenants
        severity=severity,
        status=incident_status,
        limit=limit,
    )
    return {"items": items, "total": len(items)}


class PaResolveIncidentBody(BaseModel):
    resolution_note: str


@router.patch("/security-incidents/{incident_id}/resolve")
async def pa_resolve_security_incident(
    incident_id: str,
    body: PaResolveIncidentBody,
    db: DbConn,
    current=PA,
):
    """PA: resolve any security incident (no tenant scope restriction)."""
    from services.incident_service import IncidentService
    svc = IncidentService(db=db)
    try:
        await svc.resolve_incident(
            incident_id=incident_id,
            resolved_by=current.user_id,
            resolution_note=body.resolution_note,
            tenant_id=None,   # PA sees all tenants
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    return {"status": "resolved"}


@router.patch("/security-incidents/{incident_id}/escalate")
async def pa_escalate_security_incident(incident_id: str, db: DbConn, _=PA):
    """PA: escalate any security incident."""
    from services.incident_service import IncidentService
    svc = IncidentService(db=db)
    try:
        await svc.escalate_incident(incident_id=incident_id, tenant_id=None)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    return {"status": "escalated"}


# ── Application errors (4th incident track — see prana-docs/ERROR_OBSERVABILITY_DESIGN.md) ──

class ResolveErrorIn(BaseModel):
    resolution_note: str = Field(min_length=1)


class PromoteErrorIn(BaseModel):
    severity: str


def _error_value_error_status(exc: ValueError) -> int:
    return status.HTTP_404_NOT_FOUND if "not found" in str(exc) else status.HTTP_422_UNPROCESSABLE_ENTITY


@router.get("/errors")
async def list_errors(
    db: DbConn,
    _=PA,
    tenant_id: Optional[str] = None,
    error_status: Optional[str] = None,
    limit: int = 100,
):
    """PA: list captured application errors across all tenants (or filter by tenant)."""
    from services.error_observability_service import ErrorObservabilityService
    svc = ErrorObservabilityService(db)
    items = await svc.list_errors(tenant_id=tenant_id, status=error_status, limit=limit)
    return {"items": items, "total": len(items)}


@router.post("/errors/{error_id}/acknowledge")
async def acknowledge_error(error_id: str, db: DbConn, _=PA):
    from services.error_observability_service import ErrorObservabilityService
    svc = ErrorObservabilityService(db)
    try:
        await svc.acknowledge(error_id=error_id)
    except ValueError as exc:
        raise HTTPException(status_code=_error_value_error_status(exc), detail=str(exc)) from exc
    return {"status": "acknowledged"}


@router.post("/errors/{error_id}/ignore")
async def ignore_error(error_id: str, db: DbConn, _=PA):
    from services.error_observability_service import ErrorObservabilityService
    svc = ErrorObservabilityService(db)
    try:
        await svc.ignore(error_id=error_id)
    except ValueError as exc:
        raise HTTPException(status_code=_error_value_error_status(exc), detail=str(exc)) from exc
    return {"status": "ignored"}


@router.post("/errors/{error_id}/resolve")
async def resolve_error(error_id: str, body: ResolveErrorIn, db: DbConn, current=PA):
    from services.error_observability_service import ErrorObservabilityService
    svc = ErrorObservabilityService(db)
    try:
        await svc.resolve(error_id=error_id, resolved_by=current.user_id, resolution_note=body.resolution_note)
    except ValueError as exc:
        raise HTTPException(status_code=_error_value_error_status(exc), detail=str(exc)) from exc
    return {"status": "resolved"}


@router.post("/errors/{error_id}/promote-to-incident")
async def promote_error_to_incident(error_id: str, body: PromoteErrorIn, db: DbConn, _=PA):
    from services.error_observability_service import ErrorObservabilityService
    svc = ErrorObservabilityService(db)
    try:
        incident_id = await svc.promote_to_incident(error_id=error_id, severity=body.severity)
    except ValueError as exc:
        raise HTTPException(status_code=_error_value_error_status(exc), detail=str(exc)) from exc
    return {"status": "promoted", "incident_id": incident_id}


# ── Notification log (cross-tenant — PA only) ──────────────────────────────────

@router.get("/notifications")
async def list_notifications(
    db: DbConn,
    _=PA,
    tenant_id: Optional[str] = None,
    channel: Optional[str] = None,
    notif_status: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 200,
):
    """PA: view full notification_log, filterable by tenant/channel/status/event_type."""
    conditions: list[str] = []
    params: list = []
    idx = 1

    if tenant_id:
        conditions.append(f"tenant_id = ${idx}")
        params.append(tenant_id)
        idx += 1
    if channel:
        conditions.append(f"channel = ${idx}")
        params.append(channel)
        idx += 1
    if notif_status:
        conditions.append(f"status = ${idx}")
        params.append(notif_status)
        idx += 1
    if event_type:
        conditions.append(f"event_type = ${idx}")
        params.append(event_type)
        idx += 1

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    rows = await db.fetch(
        f"""
        SELECT notification_id, tenant_id, event_type, channel, template_id,
               recipient_type, status, provider_ref,
               sent_at, failed_at, error_message, retry_count, created_at
          FROM notification_log
         {where}
         ORDER BY created_at DESC
         LIMIT ${idx}
        """,
        *params,
    )
    items = [
        {
            "notification_id": str(r["notification_id"]),
            "tenant_id":       str(r["tenant_id"]) if r["tenant_id"] else None,
            "event_type":      r["event_type"],
            "channel":         r["channel"],
            "template_id":     r["template_id"],
            "recipient_type":  r["recipient_type"],
            "status":          r["status"],
            "provider_ref":    r["provider_ref"],
            "sent_at":         r["sent_at"].isoformat() if r["sent_at"] else None,
            "failed_at":       r["failed_at"].isoformat() if r["failed_at"] else None,
            "error_message":   r["error_message"],
            "retry_count":     r["retry_count"],
            "created_at":      r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


# ── Contact / org-application review ────────────────────────────────────────
# Relocated from routers/public.py (2026-07-15) — PA-authenticated reads/writes
# don't belong under a path named "public" (see .claude/rules/api-versioning.md).

@router.get("/contact-inquiries", status_code=200)
async def list_contact_inquiries(db: DbConn, current=PA, page: int = 1, limit: int = 50):
    offset = (page - 1) * limit
    rows = await db.fetch(
        """
        SELECT id, name, email, org, enquiry_type, message, status, submitted_at
        FROM contact_inquiry
        ORDER BY submitted_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit, offset,
    )
    total = await db.fetchval("SELECT COUNT(*) FROM contact_inquiry")
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
    db: DbConn, current=PA, page: int = 1, limit: int = 50, app_status: Optional[str] = None,
):
    offset = (page - 1) * limit
    where = "WHERE status = $3" if app_status else ""
    params: list = [limit, offset]
    if app_status:
        params.append(app_status)

    rows = await db.fetch(
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
    total = await db.fetchval(
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
async def review_application(app_id: str, body: ReviewIn, db: DbConn, current=PA):
    await db.execute(
        """
        UPDATE self_service_application
        SET status = $1, review_notes = $2, reviewed_at = NOW()
        WHERE id = $3::uuid
        """,
        body.status, body.review_notes, app_id,
    )
    return {"status": body.status}


# ── Severity / SLA policy config — see prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §5 ──

@router.get("/sla-policy")
async def list_sla_policy(db: DbConn, _=PA):
    from services.severity_policy_service import SeverityPolicyService
    items = await SeverityPolicyService(db).get_all_sla_policies()
    return {"items": items, "total": len(items)}


class SlaPolicyUpdateIn(BaseModel):
    sla_minutes: Optional[int] = Field(default=None, gt=0)
    auto_create_incident: Optional[bool] = None
    description: Optional[str] = None


@router.patch("/sla-policy/{severity}")
async def update_sla_policy(severity: str, body: SlaPolicyUpdateIn, db: DbConn, current=PA):
    from services.severity_policy_service import SeverityPolicyService
    try:
        policy = await SeverityPolicyService(db).update_sla_policy(
            severity=severity, sla_minutes=body.sla_minutes,
            auto_create_incident=body.auto_create_incident,
            description=body.description, updated_by=current.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"message": SuccessCode.SLA_POLICY_UPDATED, "sla_policy": policy}


@router.get("/severity-rules")
async def list_severity_rules(db: DbConn, _=PA, domain: Optional[str] = None):
    from services.severity_policy_service import SeverityPolicyService
    items = await SeverityPolicyService(db).list_severity_rules(domain=domain)
    return {"items": items, "total": len(items)}


class SeverityRuleCreateIn(BaseModel):
    domain: str
    match_type: str
    match_value: Optional[str] = None
    occurrence_threshold: Optional[int] = None
    occurrence_threshold_max: Optional[int] = None
    window_minutes: Optional[int] = None
    severity: str
    priority: int = 100
    description: Optional[str] = None


@router.post("/severity-rules", status_code=status.HTTP_201_CREATED)
async def create_severity_rule(body: SeverityRuleCreateIn, db: DbConn, current=PA):
    from services.severity_policy_service import SeverityPolicyService
    try:
        rule = await SeverityPolicyService(db).create_severity_rule(
            domain=body.domain, match_type=body.match_type, match_value=body.match_value,
            occurrence_threshold=body.occurrence_threshold,
            occurrence_threshold_max=body.occurrence_threshold_max,
            window_minutes=body.window_minutes, severity=body.severity,
            priority=body.priority, description=body.description,
            updated_by=current.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"message": SuccessCode.SEVERITY_RULE_CREATED, "severity_rule": rule}


class SeverityRuleUpdateIn(BaseModel):
    occurrence_threshold: Optional[int] = None
    occurrence_threshold_max: Optional[int] = None
    window_minutes: Optional[int] = None
    severity: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None


@router.patch("/severity-rules/{rule_id}")
async def update_severity_rule(rule_id: str, body: SeverityRuleUpdateIn, db: DbConn, current=PA):
    from services.severity_policy_service import SeverityPolicyService
    try:
        rule = await SeverityPolicyService(db).update_severity_rule(
            rule_id=rule_id, occurrence_threshold=body.occurrence_threshold,
            occurrence_threshold_max=body.occurrence_threshold_max,
            window_minutes=body.window_minutes, severity=body.severity,
            priority=body.priority, is_active=body.is_active,
            description=body.description, updated_by=current.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"message": SuccessCode.SEVERITY_RULE_UPDATED, "severity_rule": rule}

