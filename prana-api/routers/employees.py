"""
Employee master management — OA-Operator / OA-Admin.

GET  /employees               — search employees for this tenant
POST /employees               — create single employee (NIK in body, dropped after pan_token computed)
GET  /employees/{uuid}        — get employee detail
PATCH /employees/{uuid}       — update profile fields
POST /employees/{uuid}/alumni — mark as alumni (set dol)
GET  /employees/{uuid}/history — field change history
"""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from dependencies import DbConn, require_oa
from services.employee_service import EmployeeService
from services.elevation_service import ElevationService

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


def _svc(request: Request, db: DbConn) -> EmployeeService:
    return EmployeeService(
        db=db,
        kms=request.app.state.kms_service,
        platform_hmac_secret=request.app.state.settings.platform_hmac_secret,
    )


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
    return result


@router.get("/{employee_uuid}", status_code=status.HTTP_200_OK, dependencies=[OAOperator])
async def get_employee(
    employee_uuid: str,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_operator","oa_admin","chro","cfo","ciso")),
):
    emp = await _svc(request, db).get(employee_uuid, current.tenant_id)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EMPLOYEE_NOT_FOUND")
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
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ELEVATION_REQUIRED")
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
    return {"message": "Updated"}


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
    return {"message": "Marked as alumni"}


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
