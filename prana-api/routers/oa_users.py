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
GET  /org/elevations/{id}/status         — SSE stream: real-time elevation status (OA-Operator/Admin)
"""
import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from messages import SuccessCode, success_response
from pydantic import BaseModel, EmailStr

from dependencies import DbConn, require_oa
from errors import PranaError
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

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.oa_user_event({
            "event_type": "OA_USER_CREATED",
            "tenant_id":  str(current.tenant_id),
            "oa_user_id": result["oa_user_id"],
            "email":      str(body.email),
            "role":       body.role,
            "login_url":  "https://prana.in/org/login",
            "created_by": str(current.user_id),
        })

    return {"oa_user_id": result["oa_user_id"], "message": SuccessCode.OA_USER_CREATED}


@router.post("/users/{oa_user_id}/deactivate", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def deactivate_user(oa_user_id: str, db: DbConn, current=Depends(require_oa("oa_admin"))):
    svc = OAUserService(db)
    try:
        await svc.deactivate(oa_user_id, current.tenant_id, current.user_id)
    except ValueError as e:
        code = str(e)
        status_code = status.HTTP_409_CONFLICT if code == "MIN_ADMIN_CONSTRAINT" else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=code)
    return {"message": SuccessCode.OA_USER_DEACTIVATED}


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
    return {"message": SuccessCode.ROLE_UPDATED}


@router.post("/users/{oa_user_id}/unlock", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def unlock_user(oa_user_id: str, db: DbConn, current=Depends(require_oa("oa_admin"))):
    svc = OAUserService(db)
    await svc.unlock(oa_user_id, current.tenant_id, current.user_id)
    return {"message": SuccessCode.LOCK_REMOVED}


@router.post("/users/{oa_user_id}/resend-welcome", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def resend_welcome_email(
    oa_user_id: str,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_admin")),
):
    """Re-trigger the OA_WELCOME email for a user whose original email bounced —
    via NotifConsumer/EmailConsumer, never sent directly from the HTTP handler."""
    row = await db.fetchrow(
        "SELECT oa_user_id, email FROM oa_user WHERE oa_user_id = $1 AND tenant_id = $2",
        oa_user_id, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.USER_NOT_FOUND)

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.oa_user_event({
            "event_type": "OA_WELCOME_RESENT",
            "tenant_id":  str(current.tenant_id),
            "oa_user_id": str(row["oa_user_id"]),
            "email":      row["email"],
            "login_url":  "https://prana.in/org/login",
            "resent_by":  str(current.user_id),
        })

    return {"message": SuccessCode.OA_WELCOME_EMAIL_RESENT}


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
async def approve_elevation(elevation_id: str, request: Request, db: DbConn, current=Depends(require_oa("oa_admin"))):
    svc = ElevationService(db)
    try:
        result = await svc.approve(elevation_id, current.user_id, current.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    _publish_elevation_sse(request, elevation_id, "ACTIVE", result.get("expires_at"))
    return result


@router.post("/elevations/{elevation_id}/deny", status_code=status.HTTP_200_OK, dependencies=[OAAdmin])
async def deny_elevation(elevation_id: str, request: Request, db: DbConn, current=Depends(require_oa("oa_admin"))):
    svc = ElevationService(db)
    try:
        await svc.deny(elevation_id, current.user_id, current.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    _publish_elevation_sse(request, elevation_id, "DENIED")
    return {"message": SuccessCode.ELEVATION_DENIED}


@router.post("/elevations/{elevation_id}/end-early", status_code=status.HTTP_200_OK, dependencies=[OAOperator])
async def end_elevation_early(
    elevation_id: str,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_operator", "oa_admin")),
):
    svc = ElevationService(db)
    await svc.end_early(elevation_id, current.user_id, current.tenant_id)
    _publish_elevation_sse(request, elevation_id, "ENDED_EARLY")
    return {"message": SuccessCode.ELEVATION_ENDED}


# ── SSE elevation status stream (Redis Pub/Sub) ───────────────────────────────

_ELEVATION_TERMINAL = {"ACTIVE", "DENIED", "ENDED_EARLY", "ENDED"}


def _publish_elevation_sse(request: Request, elevation_id: str, new_status: str, expires_at=None) -> None:
    """Fire-and-forget Redis publish so approve/deny can notify waiting SSE clients."""
    redis = getattr(request.app.state, "redis", None)
    if not redis:
        return
    payload = json.dumps({"elevation_id": elevation_id, "status": new_status, "expires_at": expires_at})
    try:
        # NOTE: this only catches a synchronous create_task() failure (e.g. no
        # running loop). The redis.publish() coroutine itself runs later, in the
        # background — a failure there is NOT caught here at all; it goes to
        # asyncio's default unhandled-task-exception handler. Recording that
        # properly needs this to await the publish directly instead of
        # fire-and-forget, which is a bigger change than this pass covers —
        # flagged as a known gap rather than silently left unaddressed.
        asyncio.get_event_loop().create_task(redis.publish(f"sse:elevation:{elevation_id}", payload))
    except Exception:
        pass  # SSE notification failure must never block the approve/deny response


@router.get("/elevations/{elevation_id}/status")
async def elevation_status_stream(
    elevation_id: str,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_operator", "oa_admin")),
):
    """
    Server-Sent Events: streams elevation status changes in real time.
    OA-Operator opens this after requesting elevation — receives ACTIVE or DENIED
    the moment the admin acts, without polling.

    Publisher: approve/deny/end-early handlers via _publish_elevation_sse().
    Closes on terminal state (ACTIVE/DENIED/ENDED_EARLY/ENDED) or 10-minute timeout.
    """
    tenant_id    = current.tenant_id
    redis_client = request.app.state.redis

    row = await db.fetchrow(
        "SELECT status FROM elevation_request WHERE elevation_id=$1 AND tenant_id=$2",
        elevation_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.ELEVATION_NOT_FOUND)

    initial_status = row["status"]

    async def _generate() -> AsyncGenerator[str, None]:
        yield _sse_elev({"elevation_id": elevation_id, "status": initial_status})

        if initial_status in _ELEVATION_TERMINAL:
            return

        channel = f"sse:elevation:{elevation_id}"
        pubsub  = redis_client.pubsub()
        await pubsub.subscribe(channel)
        try:
            deadline = asyncio.get_event_loop().time() + 600   # 10 min max wait
            async for message in pubsub.listen():
                if await request.is_disconnected():
                    break
                if asyncio.get_event_loop().time() > deadline:
                    break
                if message["type"] != "message":
                    continue
                data = json.loads(message["data"])
                yield _sse_elev(data)
                if data.get("status") in _ELEVATION_TERMINAL:
                    break
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return StreamingResponse(_generate(), media_type="text/event-stream")


def _sse_elev(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"
