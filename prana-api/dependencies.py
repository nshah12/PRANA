from typing import Annotated, Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import asyncpg
import jwt as pyjwt

from db import get_db
from services.jwt_service import JWTService

_bearer = HTTPBearer(auto_error=False)


class CurrentUser:
    """Decoded JWT claims attached to every authenticated request."""
    def __init__(self, payload: dict):
        self.user_id: str        = payload["sub"]
        self.user_type: str      = payload["user_type"]
        self.tenant_id: Optional[str] = payload.get("tenant_id")
        self.role: Optional[str] = payload.get("role")
        self.session_id: str     = payload["jti"]


async def _decode_bearer(
    request: Request,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)],
) -> CurrentUser:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MISSING_TOKEN")

    jwt_svc: JWTService = request.app.state.jwt_service
    try:
        payload = jwt_svc.decode(credentials.credentials)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="TOKEN_EXPIRED")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="TOKEN_INVALID")

    if await jwt_svc.is_revoked(payload["jti"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="SESSION_REVOKED")

    return CurrentUser(payload)


# ── Auth dependencies ──────────────────────────────────────────────────────────

AuthUser = Annotated[CurrentUser, Depends(_decode_bearer)]


def require_employee(current: AuthUser) -> CurrentUser:
    if current.user_type != "employee":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="EMPLOYEE_ONLY")
    return current


def require_oa(*roles: str):
    """Factory: require OA user with one of the given roles."""
    def _check(current: AuthUser) -> CurrentUser:
        if current.user_type != "oa_user":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="OA_ONLY")
        if roles and current.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="INSUFFICIENT_ROLE")
        return current
    return _check


def require_pa(current: AuthUser) -> CurrentUser:
    if current.user_type != "portal_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="PA_ONLY")
    return current


# Convenience type aliases used in route signatures
Employee    = Annotated[CurrentUser, Depends(require_employee)]
PortalAdmin = Annotated[CurrentUser, Depends(require_pa)]
DbConn      = Annotated[asyncpg.Connection, Depends(get_db)]
