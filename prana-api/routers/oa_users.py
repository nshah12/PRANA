"""
OA user management + elevation — OA-Admin only (except elevation request which is OA-Operator).

GET  /org/users                          — list users for this tenant
POST /org/users                          — create OA user
POST /org/users/{id}/deactivate          — deactivate (min-1-admin guard)
POST /org/users/{id}/change-role         — change role (min-1-admin guard)
POST /org/users/{id}/unlock              — unlock locked account
GET  /org/elevations                     — list pending elevations (OA-Admin)
POST /org/elevations                     — request elevation (OA-Operator)
POST /org/elevations/{id}/approve        — approve (OA-Admin)
POST /org/elevations/{id}/deny           — deny (OA-Admin)
POST /org/elevations/{id}/end-early      — end early (OA-Operator who requested)
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr

from dependencies import DbConn, require_oa
from services.oa_user_service import OAUserService
from services.elevation_service import ElevationService

router = APIRouter()

OAAdmin    = Depends(require_oa("oa_admin"))
OAOperator = Depends(require_oa("oa_operator", "oa_admin"))


class CreateOAUserIn(BaseModel):
    email: EmailStr
    role: str   # oa_operator | oa_admin | chro | cfo | ciso


class ChangeRoleIn(BaseModel):
    role: str


class ElevationRequestIn(BaseModel):
    reason: str
    duration_hours: int   # 2 | 4 | 8


# ── OA User endpoints ─────────────────────────────────────────────────────────

@router.get("/users", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def list_users(db: DbConn, current=Depends(require_oa("oa_admin"))):
    svc = OAUserService(db)
    users = await svc.list_for_tenant(current.tenant_id)
    return {"users": users}


@router.post("/users", status_code=status.HTTP_201_CREATED, dependencies=[OAAdmin])
async def create_user(
    body: CreateOAUserIn,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_admin")),
):
    svc = OAUserService(db)
    try:
        result = await svc.create(
            tenant_id=current.tenant_id,
            email=str(body.email),
            role=body.role,
            created_by=current.user_id,
        )
    except ValueError as e:
        code = str(e)
        if code == "EMAIL_DOMAIN_MISMATCH":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=code)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code)

    # Publish welcome email event → NotifConsumer dispatches via SES
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        import datetime, uuid as _uuid
        await kafka.publish("prana.notifications", {
            "event_type":    "OA_USER_CREATED",
            "event_id":      str(_uuid.uuid4()),
            "occurred_at":   datetime.datetime.utcnow().isoformat(),
            "tenant_id":     current.tenant_id,
            "oa_user_id":    result["oa_user_id"],
            "email":         str(body.email),
            "role":          body.role,
            "temp_password": result.get("temp_password"),
            "login_url":     "https://prana.in/org/login",
            "created_by":    current.user_id,
        }, key=current.tenant_id)

    return {"oa_user_id": result["oa_user_id"], "message": "User created — temp password sent via email"}


@router.post("/users/{oa_user_id}/deactivate", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def deactivate_user(oa_user_id: str, db: DbConn, current=Depends(require_oa("oa_admin"))):
    svc = OAUserService(db)
    try:
        await svc.deactivate(oa_user_id, current.tenant_id, current.user_id)
    except ValueError as e:
        code = str(e)
        status_code = status.HTTP_409_CONFLICT if code == "MIN_ADMIN_CONSTRAINT" else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=code)
    return {"message": "User deactivated"}


@router.post("/users/{oa_user_id}/change-role", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def change_role(
    oa_user_id: str,
    body: ChangeRoleIn,
    db: DbConn,
    current=Depends(require_oa("oa_admin")),
):
    svc = OAUserService(db)
    try:
        await svc.change_role(oa_user_id, body.role, current.tenant_id, current.user_id)
    except ValueError as e:
        code = str(e)
        status_code = status.HTTP_409_CONFLICT if code == "MIN_ADMIN_CONSTRAINT" else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=code)
    return {"message": "Role updated"}


@router.post("/users/{oa_user_id}/unlock", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def unlock_user(oa_user_id: str, db: DbConn, current=Depends(require_oa("oa_admin"))):
    svc = OAUserService(db)
    await svc.unlock(oa_user_id, current.tenant_id, current.user_id)
    return {"message": "Account unlocked"}


# ── Badge counts (sidebar) ────────────────────────────────────────────────────

@router.get("/exceptions/count", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def exception_count(db: DbConn, current=Depends(require_oa("oa_admin"))):
    n = await db.fetchval(
        "SELECT COUNT(*) FROM exception_queue WHERE tenant_id=$1 AND status='OPEN'",
        current.tenant_id,
    )
    return {"count": n or 0}


@router.get("/elevations/pending-count", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def elevation_pending_count(db: DbConn, current=Depends(require_oa("oa_admin"))):
    n = await db.fetchval(
        "SELECT COUNT(*) FROM elevation_request WHERE tenant_id=$1 AND status='PENDING'",
        current.tenant_id,
    )
    return {"count": n or 0}


# ── Elevation endpoints ───────────────────────────────────────────────────────

@router.get("/elevations", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def list_elevations(db: DbConn, current=Depends(require_oa("oa_admin"))):
    svc = ElevationService(db)
    return await svc.list_pending(current.tenant_id)


@router.post("/elevations", status_code=status.HTTP_201_CREATED, dependencies=[OAOperator])
async def request_elevation(
    body: ElevationRequestIn,
    db: DbConn,
    current=Depends(require_oa("oa_operator", "oa_admin")),
):
    svc = ElevationService(db)
    try:
        result = await svc.request(
            requestor_id=current.user_id,
            tenant_id=current.tenant_id,
            reason=body.reason,
            duration_hours=body.duration_hours,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return result


@router.post("/elevations/{elevation_id}/approve", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def approve_elevation(elevation_id: str, db: DbConn, current=Depends(require_oa("oa_admin"))):
    svc = ElevationService(db)
    try:
        result = await svc.approve(elevation_id, current.user_id, current.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return result


@router.post("/elevations/{elevation_id}/deny", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def deny_elevation(elevation_id: str, db: DbConn, current=Depends(require_oa("oa_admin"))):
    svc = ElevationService(db)
    try:
        await svc.deny(elevation_id, current.user_id, current.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return {"message": "Denied"}


@router.post("/elevations/{elevation_id}/end-early", status_code=status.HTTP_200_OK, dependencies=[OAOperator])
async def end_elevation_early(
    elevation_id: str,
    db: DbConn,
    current=Depends(require_oa("oa_operator", "oa_admin")),
):
    svc = ElevationService(db)
    await svc.end_early(elevation_id, current.user_id, current.tenant_id)
    return {"message": "Elevation ended"}
