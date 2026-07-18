"""
Employee master management — OA-Operator / OA-Admin.

GET  /employees               — search employees for this tenant
POST /employees               — create single employee (NIK in body, dropped after pan_token computed)
GET  /employees/{uuid}        — get employee detail
PATCH /employees/{uuid}       — update profile fields
POST /employees/{uuid}/alumni — mark as alumni (set dol)
GET  /employees/{uuid}/history — field change history
"""
import csv
import io
from datetime import date
from messages import SuccessCode, success_response
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

from dependencies import DbConn, require_oa
from services.employee_service import EmployeeService
from services.elevation_service import ElevationService
from services.encryption_service import compute_mobile_token, resolve_platform_auth_kek_arn
from errors import PranaError

_BULK_IMPORT_REQUIRED_COLUMNS = {"nik", "full_name", "doj"}
_BULK_IMPORT_MAX_ROWS = 500

router = APIRouter()

OAUser     = Depends(require_oa("oa_operator", "oa_admin", "chro", "cfo", "ciso"))
OAOperator = Depends(require_oa("oa_operator", "oa_admin"))
OAAdmin    = Depends(require_oa("oa_admin"))


class CreateEmployeeIn(BaseModel):
    nik: str                   # cleartext PAN — used once, dropped immediately
    emp_id_org: Optional[str] = None
    full_name: str
    designation: Optional[str] = None
    department: Optional[str] = None
    grade: Optional[str] = None
    location: Optional[str] = None
    employment_type: str = "PERMANENT"
    cost_centre: Optional[str] = None
    uan: Optional[str] = None
    doj: date
    mobile: Optional[str] = None   # E.164 — employee's login handle, if known at push time
    email: Optional[str] = None    # secondary login handle, if known at push time


class UpdateEmployeeIn(BaseModel):
    designation: Optional[str] = None
    department: Optional[str] = None
    grade: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    cost_centre: Optional[str] = None
    reporting_manager: Optional[str] = None


class AlumniIn(BaseModel):
    dol: date


class ResetTotpIn(BaseModel):
    identifier: str   # employee's email or mobile (E.164 or bare 10-digit)


class ResetPasswordIn(BaseModel):
    identifier: str   # employee's email or mobile (E.164 or bare 10-digit)


def _normalise_identifier(raw: str) -> tuple[str, str]:
    """Return (column_name, value) for a mobile or email identifier."""
    raw = raw.strip()
    if "@" in raw:
        return "email", raw.lower()
    digits = raw.replace("+91", "").replace(" ", "").replace("-", "")
    if len(digits) == 10 and digits[0] in "6789":
        return "mobile", f"+91{digits}"
    return "mobile", raw   # pass through, DB will reject


def _svc(request: Request, db: DbConn) -> EmployeeService:
    return EmployeeService(
        db=db,
        kms=request.app.state.kms_service,
        platform_hmac_secret=request.app.state.settings.platform_hmac_secret,
    )


async def _publish_credentials_issued(kafka, *, employee_user_id: str, tenant_id: str) -> None:
    """Fires only when EmployeeService.create() actually generated a temp password
    (i.e. the employer supplied mobile/email at push time). Never puts the plaintext
    temp password in the event: same privacy call NotifConsumer._handle_welcome
    already makes for OA's temp password."""
    if not kafka:
        return
    await kafka.employee_credentials_issued({
        "event_type": "EMPLOYEE_CREDENTIALS_ISSUED",
        "recipient_id": employee_user_id,
        "template_id": "EMPLOYEE_CREDENTIALS_ISSUED",
        "tenant_id": tenant_id,
        "payload": {},
    })


@router.get("", status_code=status.HTTP_200_OK, dependencies=[OAOperator])
async def search_employees(
    request: Request,
    db: DbConn,
    name: Optional[str] = None,
    emp_id_org: Optional[str] = None,
    active_only: bool = True,
    limit: int = 50,
    # tenant_id always from JWT — never from query params
    current=Depends(require_oa("oa_operator","oa_admin","chro","cfo","ciso")),
):
    return await _svc(request, db).search(
        current.tenant_id,
        name=name,
        emp_id_org=emp_id_org,
        active_only=active_only,
        limit=min(limit, 200),
    )


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[OAOperator])
async def create_employee(
    body: CreateEmployeeIn,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_operator","oa_admin")),
):
    tenant = await db.fetchrow(
        "SELECT kek_arn FROM tenant WHERE tenant_id=$1", current.tenant_id
    )
    result = await _svc(request, db).create(
        nik=body.nik,
        tenant_id=current.tenant_id,
        emp_id_org=body.emp_id_org,
        full_name=body.full_name,
        designation=body.designation,
        department=body.department,
        grade=body.grade,
        location=body.location,
        employment_type=body.employment_type,
        cost_centre=body.cost_centre,
        uan=body.uan,
        doj=body.doj,
        created_by=current.user_id,
        kek_arn=tenant["kek_arn"],
        mobile=body.mobile,
        email=body.email,
        auth_kek_arn=resolve_platform_auth_kek_arn(request.app.state.settings),
    )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.employee_event({
            "event_type":      "EMPLOYEE_ONBOARDED",
            "tenant_id":       str(current.tenant_id),
            "employee_uuid":   result.get("employee_uuid", ""),
            "emp_id_org":      body.emp_id_org,
            "employment_type": body.employment_type,
            "created_by":      current.user_id,
        })
        if result.get("temp_password"):
            await _publish_credentials_issued(
                kafka, employee_user_id=result["employee_user_id"], tenant_id=str(current.tenant_id),
            )
    return result


@router.post("/import", status_code=status.HTTP_200_OK, dependencies=[OAOperator])
async def bulk_import_employees(
    request: Request,
    db: DbConn,
    file: UploadFile = File(...),
    current=Depends(require_oa("oa_operator", "oa_admin")),
):
    """
    Bulk-onboard employees from a CSV (columns: nik, full_name, doj required;
    emp_id_org, designation, department, grade, location, employment_type,
    cost_centre, uan optional). Each row reuses EmployeeService.create() — a
    single bad row is recorded as a per-row error, not an aborted batch.
    """
    raw = await file.read()
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = {c.strip() for c in (reader.fieldnames or [])}
    if not _BULK_IMPORT_REQUIRED_COLUMNS.issubset(fieldnames):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PranaError.CSV_MISSING_REQUIRED_COLUMNS)

    rows = list(reader)
    if len(rows) > _BULK_IMPORT_MAX_ROWS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PranaError.CSV_TOO_MANY_ROWS)

    tenant = await db.fetchrow("SELECT kek_arn FROM tenant WHERE tenant_id=$1", current.tenant_id)
    svc = _svc(request, db)
    kafka = getattr(request.app.state, "kafka_producer", None)
    auth_kek_arn = resolve_platform_auth_kek_arn(request.app.state.settings)

    created = 0
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):   # row 1 is the header
        nik = (row.get("nik") or "").strip()
        full_name = (row.get("full_name") or "").strip()
        doj_raw = (row.get("doj") or "").strip()
        if not nik or not full_name or not doj_raw:
            errors.append({"row": i, "error": PranaError.CSV_MISSING_REQUIRED_FIELD})
            continue
        try:
            doj = date.fromisoformat(doj_raw)
        except ValueError:
            errors.append({"row": i, "error": PranaError.CSV_INVALID_DATE_FORMAT})
            continue

        try:
            result = await svc.create(
                nik=nik,
                tenant_id=current.tenant_id,
                emp_id_org=(row.get("emp_id_org") or "").strip() or None,
                full_name=full_name,
                designation=(row.get("designation") or "").strip() or None,
                department=(row.get("department") or "").strip() or None,
                grade=(row.get("grade") or "").strip() or None,
                location=(row.get("location") or "").strip() or None,
                employment_type=(row.get("employment_type") or "").strip() or "PERMANENT",
                cost_centre=(row.get("cost_centre") or "").strip() or None,
                uan=(row.get("uan") or "").strip() or None,
                doj=doj,
                created_by=current.user_id,
                kek_arn=tenant["kek_arn"],
                mobile=(row.get("mobile") or "").strip() or None,
                email=(row.get("email") or "").strip() or None,
                auth_kek_arn=auth_kek_arn,
            )
        except Exception:
            errors.append({"row": i, "error": PranaError.EMPLOYEE_CREATE_FAILED})
            continue

        created += 1
        if kafka:
            await kafka.employee_event({
                "event_type":      "EMPLOYEE_ONBOARDED",
                "tenant_id":       str(current.tenant_id),
                "employee_uuid":   result.get("employee_uuid", ""),
                "emp_id_org":      row.get("emp_id_org"),
                "employment_type": (row.get("employment_type") or "").strip() or "PERMANENT",
                "created_by":      current.user_id,
            })
            if result.get("temp_password"):
                await _publish_credentials_issued(
                    kafka, employee_user_id=result["employee_user_id"], tenant_id=str(current.tenant_id),
                )

    return {
        "message":  SuccessCode.EMPLOYEE_BULK_IMPORT_COMPLETE,
        "total":    len(rows),
        "created":  created,
        "failed":   len(errors),
        "errors":   errors,
    }


@router.get("/{employee_uuid}", status_code=status.HTTP_200_OK, dependencies=[OAOperator])
async def get_employee(
    employee_uuid: str,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_operator","oa_admin","chro","cfo","ciso")),
):
    emp = await _svc(request, db).get(employee_uuid, current.tenant_id)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EMPLOYEE_NOT_FOUND)
    return emp


@router.patch("/{employee_uuid}", status_code=status.HTTP_200_OK, dependencies=[OAOperator])
async def update_employee(
    employee_uuid: str,
    body: UpdateEmployeeIn,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_operator","oa_admin")),
):
    # Elevation check: operators need active elevation for profile changes
    elevation_id = None
    if current.role == "oa_operator":
        elev_svc = ElevationService(db)
        elev = await elev_svc.get_active(current.user_id)
        if not elev:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PranaError.ELEVATION_REQUIRED)
        elevation_id = elev["elevation_id"]

    try:
        await _svc(request, db).update(
            employee_uuid=employee_uuid,
            tenant_id=current.tenant_id,
            fields=body.model_dump(exclude_none=True),
            changed_by=current.user_id,
            changed_by_role=current.role,
            elevation_id=elevation_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.employee_event({
            "event_type":     "EMPLOYEE_PROFILE_UPDATED",
            "tenant_id":      str(current.tenant_id),
            "employee_uuid":  employee_uuid,
            "changed_by":     current.user_id,
            "changed_fields": list(body.model_dump(exclude_none=True).keys()),
        })
    return {"message": SuccessCode.ANOMALY_UPDATED}


@router.post("/{employee_uuid}/alumni", status_code=status.HTTP_200_OK)
async def mark_alumni(
    employee_uuid: str,
    body: AlumniIn,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_admin")),
):
    tenant = await db.fetchrow(
        "SELECT push_window_months FROM tenant WHERE tenant_id=$1", current.tenant_id
    )
    try:
        await _svc(request, db).mark_alumni(
            employee_uuid=employee_uuid,
            dol=body.dol,
            tenant_id=current.tenant_id,
            push_window_months=tenant["push_window_months"],
            changed_by=current.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.employee_event({
            "event_type":    "EMPLOYEE_EXITED",
            "tenant_id":     str(current.tenant_id),
            "employee_uuid": employee_uuid,
            "dol":           body.dol.isoformat(),
            "changed_by":    current.user_id,
        })
    return {"message": SuccessCode.MARKED_AS_ALUMNI}


@router.post("/reset-totp", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def reset_employee_totp(
    body: ResetTotpIn,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_admin")),
):
    """
    OA-Admin self-service: reset an employee's TOTP so QR-scan setup appears on
    next login. Looked up by email or mobile, scoped to the caller's own tenant.
    Publishes EMPLOYEE_TOTP_RESET → AuditConsumer (audit_event + Immudb dual-write,
    CISO visibility).
    """
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

    # Tenant scoping: an employee_user may exist platform-wide (shared identity across
    # employers) — only reset if this employee is actually in the caller's own tenant.
    master = await db.fetchrow(
        "SELECT employee_uuid FROM employee_master WHERE employee_user_id = $1 AND tenant_id = $2",
        employee_user_id, current.tenant_id,
    )
    if not master:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EMPLOYEE_NOT_FOUND)

    await db.execute(
        "UPDATE employee_user SET totp_secret_enc = NULL, totp_configured_at = NULL WHERE employee_user_id = $1",
        employee_user_id,
    )

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.employee_event({
            "event_type":        "EMPLOYEE_TOTP_RESET",
            "tenant_id":         str(current.tenant_id),
            "actor_id":          str(current.user_id),
            "actor_type":        "OA_ADMIN",
            "employee_user_id":  employee_user_id,
            "employee_uuid":     str(master["employee_uuid"]),
        })

    return {"message": SuccessCode.EMPLOYEE_TOTP_RESET}


@router.post("/reset-password", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def reset_employee_password(
    body: ResetPasswordIn,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_admin")),
):
    """
    OA-Admin self-service: force-reset an employee's password to a generated
    temp password (force_reset=TRUE so they must set a new one on next login).
    Looked up by email or mobile, scoped to the caller's own tenant.
    """
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

    master = await db.fetchrow(
        "SELECT employee_uuid FROM employee_master WHERE employee_user_id = $1 AND tenant_id = $2",
        employee_user_id, current.tenant_id,
    )
    if not master:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EMPLOYEE_NOT_FOUND)

    import secrets, string
    from services.password_service import hash_password
    temp_password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))

    await db.execute(
        "UPDATE employee_user SET password_hash = $2, force_reset = TRUE WHERE employee_user_id = $1",
        employee_user_id, hash_password(temp_password),
    )

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.employee_event({
            "event_type":        "EMPLOYEE_PASSWORD_RESET",
            "tenant_id":         str(current.tenant_id),
            "actor_id":          str(current.user_id),
            "actor_type":        "OA_ADMIN",
            "employee_user_id":  employee_user_id,
            "employee_uuid":     str(master["employee_uuid"]),
        })

    return {"message": SuccessCode.EMPLOYEE_PASSWORD_RESET, "temp_password": temp_password}


@router.post("/{employee_uuid}/reactivate", status_code=status.HTTP_200_OK)
async def reactivate_employee(
    employee_uuid: str,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_admin")),
):
    """Un-mark alumni — reverse of mark_alumni. Employee must currently be ALUMNI."""
    try:
        await _svc(request, db).reactivate(
            employee_uuid=employee_uuid,
            tenant_id=current.tenant_id,
            changed_by=current.user_id,
        )
    except ValueError as e:
        msg = str(e)
        if msg == "EMPLOYEE_NOT_FOUND":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EMPLOYEE_NOT_FOUND)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PranaError.EMPLOYEE_NOT_ALUMNI)

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.employee_event({
            "event_type":    "EMPLOYEE_REJOINED",
            "tenant_id":     str(current.tenant_id),
            "employee_uuid": employee_uuid,
            "changed_by":    current.user_id,
        })
    return {"message": SuccessCode.EMPLOYEE_REACTIVATED}


@router.post("/{employee_uuid}/revoke-sessions", status_code=status.HTTP_200_OK)
async def revoke_employee_sessions(
    employee_uuid: str,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_admin", "ciso")),
):
    """Sign an employee out of every device — revokes all their active sessions."""
    row = await db.fetchrow(
        "SELECT employee_user_id FROM employee_master WHERE employee_uuid = $1 AND tenant_id = $2",
        employee_uuid, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EMPLOYEE_NOT_FOUND)

    employee_user_id = str(row["employee_user_id"])

    session_rows = await db.fetch(
        "SELECT session_id FROM user_session WHERE user_type='employee' AND user_id=$1 AND revoked=FALSE",
        employee_user_id,
    )
    session_ids = [str(r["session_id"]) for r in session_rows]

    if session_ids:
        await db.execute(
            "UPDATE user_session SET revoked=TRUE, revoked_reason='FORCE_LOGOUT' WHERE user_type='employee' AND user_id=$1 AND revoked=FALSE",
            employee_user_id,
        )
        jwt_svc = request.app.state.jwt_service
        for sid in session_ids:
            await jwt_svc.revoke(sid)

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.employee_event({
            "event_type":        "EMPLOYEE_SESSIONS_REVOKED",
            "tenant_id":         str(current.tenant_id),
            "actor_id":          str(current.user_id),
            "actor_type":        "CISO" if current.role == "ciso" else "OA_ADMIN",
            "employee_user_id":  employee_user_id,
            "employee_uuid":     employee_uuid,
            "revoked_count":     len(session_ids),
        })

    return {"message": SuccessCode.EMPLOYEE_SESSIONS_REVOKED, "revoked_count": len(session_ids)}


@router.post("/{employee_uuid}/revoke-shares", status_code=status.HTTP_200_OK)
async def revoke_employee_shares(
    employee_uuid: str,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_admin", "ciso")),
):
    """Revoke every active document share link for this employee in one action."""
    row = await db.fetchrow(
        "SELECT employee_user_id FROM employee_master WHERE employee_uuid = $1 AND tenant_id = $2",
        employee_uuid, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EMPLOYEE_NOT_FOUND)

    employee_user_id = str(row["employee_user_id"])

    revoked_rows = await db.fetch(
        """
        UPDATE share_token
        SET status='REVOKED', revoked_at=NOW()
        WHERE employee_user_id = $1 AND tenant_id = $2 AND status = 'ACTIVE'
        RETURNING token_id
        """,
        employee_user_id, current.tenant_id,
    )
    revoked_count = len(revoked_rows)

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.employee_event({
            "event_type":        "EMPLOYEE_SHARES_REVOKED",
            "tenant_id":         str(current.tenant_id),
            "actor_id":          str(current.user_id),
            "actor_type":        "CISO" if current.role == "ciso" else "OA_ADMIN",
            "employee_user_id":  employee_user_id,
            "employee_uuid":     employee_uuid,
            "revoked_count":     revoked_count,
        })

    return {"message": SuccessCode.EMPLOYEE_SHARES_REVOKED, "revoked_count": revoked_count}


@router.get("/{employee_uuid}/history", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def get_history(
    employee_uuid: str,
    db: DbConn,
    current=Depends(require_oa("oa_admin")),
):
    rows = await db.fetch(
        """
        SELECT field_name, old_value, new_value, change_reason,
               changed_by_role, change_source, changed_at
        FROM employee_master_history
        WHERE employee_uuid=$1 AND tenant_id=$2
        ORDER BY changed_at DESC
        LIMIT 500
        """,
        employee_uuid, current.tenant_id,
    )
    return {"history": [
        {
            "field_name": r["field_name"],
            "old_value": r["old_value"],
            "new_value": r["new_value"],
            "change_reason": r["change_reason"],
            "changed_by_role": r["changed_by_role"],
            "change_source": r["change_source"],
            "changed_at": r["changed_at"].isoformat() if r["changed_at"] else None,
        }
        for r in rows
    ], "total": len(rows)}
