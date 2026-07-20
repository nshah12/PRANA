import hashlib
import hmac
import time
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


# ── HRMS API-key auth + rate limiting ──────────────────────────────────────────
# integrations.md: X-PRANA-Key-ID + X-PRANA-Signature (HMAC-SHA256 of the raw
# body, using the tenant's per-key signing secret). tenant_id always comes from
# the resolved api_key row — never the request body.

class ApiKeyContext:
    def __init__(self, api_key_id: str, tenant_id: str, rate_limit_rpm: int):
        self.api_key_id = api_key_id
        self.tenant_id = tenant_id
        self.rate_limit_rpm = rate_limit_rpm


async def verify_api_key_and_rate_limit(
    request: Request,
    db: Annotated[asyncpg.Connection, Depends(get_db)],
) -> ApiKeyContext:
    key_id = request.headers.get("X-PRANA-Key-ID")
    signature = request.headers.get("X-PRANA-Signature")
    if not key_id or not signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MISSING_API_KEY_HEADERS")

    row = await db.fetchrow(
        """
        SELECT ak.api_key_id, ak.tenant_id, ak.signing_secret_enc, ak.rate_limit_rpm,
               ak.status, t.kek_arn
        FROM api_key ak
        JOIN tenant t ON t.tenant_id = ak.tenant_id
        WHERE ak.key_hash = $1
        """,
        hashlib.sha256(key_id.encode()).hexdigest(),
    )
    if not row or row["status"] != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_API_KEY")

    kms = request.app.state.kms_service
    signing_secret = kms.unwrap_dek(row["signing_secret_enc"], row["kek_arn"])
    body = await request.body()
    expected_sig = hmac.new(signing_secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_SIGNATURE")

    api_key_id = str(row["api_key_id"])
    tenant_id = str(row["tenant_id"])
    rate_limit_rpm = int(row["rate_limit_rpm"] or 1000)

    redis = request.app.state.redis
    window = int(time.time() // 60)
    window_key = f"ratelimit:{api_key_id}:{window}"
    count = await redis.incr(window_key)
    if count == 1:
        await redis.expire(window_key, 60)

    if count > rate_limit_rpm:
        await redis.incr("ratelimit:hits:1h")
        await redis.expire("ratelimit:hits:1h", 3600)
        await redis.incr("ratelimit:hits:24h")
        await redis.expire("ratelimit:hits:24h", 86400)
        kafka = getattr(request.app.state, "kafka_producer", None)
        if kafka:
            import uuid, datetime
            await kafka.publish("prana.audit.events", {
                "event_type": "INGEST_RATE_LIMITED",
                "event_id": str(uuid.uuid4()),
                "occurred_at": datetime.datetime.utcnow().isoformat(),
                "api_key_id": api_key_id,
                "tenant_id": tenant_id,
                "actor_type": "HRMS_API",
            }, key=tenant_id)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="RATE_LIMIT_EXCEEDED")

    await db.execute("UPDATE api_key SET last_used_at = NOW() WHERE api_key_id = $1", api_key_id)
    return ApiKeyContext(api_key_id=api_key_id, tenant_id=tenant_id, rate_limit_rpm=rate_limit_rpm)


ApiKeyAuth = Annotated[ApiKeyContext, Depends(verify_api_key_and_rate_limit)]
