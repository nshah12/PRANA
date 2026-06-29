"""
Session management.

Employee endpoints (JWT required):
  GET  /auth/sessions/devices         -- list trusted devices for the logged-in employee
  DELETE /auth/sessions/devices/{id}  -- revoke a trusted device

CISO / OA-Admin endpoints:
  POST /auth/sessions/{session_id}/revoke -- force-revoke any session in this tenant
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status

from dependencies import AuthUser, DbConn, require_oa
from errors import PranaError

router = APIRouter()

CISO_OR_ADMIN = Depends(require_oa("ciso", "oa_admin"))


@router.get("/devices", status_code=status.HTTP_200_OK)
async def list_devices(db: DbConn, current: AuthUser, request: Request):
    """Return trusted devices for the logged-in employee."""
    current_jti = getattr(current, "session_id", None)
    rows = await db.fetch(
        """
        SELECT
          td.trusted_device_id      AS id,
          COALESCE(td.label, dc.platform::text, 'Unknown device') AS name,
          COALESCE(dc.platform, 'unknown')  AS platform,
          td.first_seen_at          AS trusted_at
        FROM trusted_device td
        LEFT JOIN device_credential dc
          ON dc.device_fingerprint_hash = td.device_fingerprint_hash
         AND dc.employee_user_id = $1
        WHERE td.user_type = 'employee' AND td.user_id = $1 AND td.revoked = FALSE
        ORDER BY td.last_seen_at DESC
        """,
        current.user_id,
    )
    current_fp = request.headers.get("X-Device-Fingerprint")
    result = []
    for r in rows:
        d = {
            "id": str(r["id"]),
            "name": r["name"],
            "platform": r["platform"],
            "trusted_at": r["trusted_at"].isoformat() if r["trusted_at"] else None,
            "is_current": False,
        }
        result.append(d)
    if result and current_fp:
        td_row = await db.fetchrow(
            "SELECT trusted_device_id FROM trusted_device WHERE user_type='employee' AND user_id=$1 AND device_fingerprint_hash=$2",
            current.user_id, current_fp,
        )
        if td_row:
            for d in result:
                if d["id"] == str(td_row["trusted_device_id"]):
                    d["is_current"] = True
                    break
    return {"devices": result}


@router.delete("/devices/{device_id}", status_code=status.HTTP_200_OK)
async def remove_device(device_id: str, db: DbConn, current: AuthUser):
    """Revoke a trusted device -- prevents biometric login from that device."""
    row = await db.fetchrow(
        "SELECT trusted_device_id FROM trusted_device WHERE trusted_device_id=$1 AND user_id=$2 AND user_type='employee' AND revoked=FALSE",
        device_id, current.user_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.DEVICE_NOT_FOUND)
    await db.execute(
        "UPDATE trusted_device SET revoked=TRUE, revoked_at=NOW() WHERE trusted_device_id=$1",
        device_id,
    )
    return {"message": "Device removed"}


@router.post("/{session_id}/revoke", status_code=status.HTTP_200_OK)
async def revoke_session(
    session_id: str,
    request: Request,
    db: DbConn,
    current=CISO_OR_ADMIN,
):
    row = await db.fetchrow(
        """
        SELECT us.session_id, us.user_id, us.revoked
        FROM user_session us
        JOIN oa_user ou ON ou.oa_user_id = us.user_id AND ou.tenant_id = $2
        WHERE us.session_id = $1
          AND us.user_type IN ('employee', 'oa_user')
        """,
        session_id, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.SESSION_NOT_FOUND)
    if row["revoked"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PranaError.ALREADY_REVOKED)

    async with db.transaction():
        await db.execute(
            "UPDATE user_session SET revoked=TRUE, revoked_reason='FORCE_LOGOUT' WHERE session_id=$1",
            session_id,
        )
        jwt_svc = request.app.state.jwt_service
        await jwt_svc.revoke(session_id)

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.auth_event({
            "event_type": "SESSION_FORCE_REVOKED",
            "actor_id": str(current.user_id),
            "actor_type": "CISO" if current.role == "ciso" else "OA_ADMIN",
            "tenant_id": str(current.tenant_id),
            "revoked_session": session_id,
            "target_user": str(row["user_id"]),
        })

    return {"message": "Session revoked"}
