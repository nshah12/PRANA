"""
Portal Admin auth flow:
  1. POST /auth/admin/login   — email + password → {requires_totp: true}
  2. POST /auth/admin/totp    — TOTP verify → JWT + httpOnly refresh cookie
  3. POST /auth/admin/refresh — silent token refresh
  4. POST /auth/admin/logout  — revoke session

PA is STRICTER than OA:
  - Lock threshold: 3 failed TOTP (not 5)
  - Email domain MUST be @prana.in (enforced at DB level + checked here)
  - No self-service password reset — another PA must assist
"""
import secrets as _secrets
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr

from dependencies import AuthUser, DbConn, require_pa
from services.encryption_service import verify_password
from services.totp_service import TOTPService
from services.session_service import SessionService
from errors import PranaError
from messages import SuccessCode, success_response

router = APIRouter()


class PALoginIn(BaseModel):
    email: EmailStr
    password: str

class PATOTPIn(BaseModel):
    step_token: str
    code: str


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    return forwarded.split(",")[0].strip() if forwarded else request.client.host


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key="prana_refresh",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=7 * 86400,
        path="/auth/admin/refresh",
    )


@router.post("/login", status_code=status.HTTP_200_OK)
async def login(body: PALoginIn, request: Request, db: DbConn):
    """Step 1: PA email + password. Domain enforced: must be @prana.in."""
    if not body.email.endswith("@prana.in"):
        # Don't reveal that the domain is wrong — treat as unknown user
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.INVALID_CREDENTIALS)

    row = await db.fetchrow(
        "SELECT pa_id, password_hash, totp_configured_at, failed_totp_count, status "
        "FROM portal_admin WHERE email = $1",
        body.email,
    )

    ip = _get_client_ip(request)

    if not row:
        await _log(db, None, "PASSWORD", "FAILED", "UNKNOWN_USER", ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.INVALID_CREDENTIALS)

    if row["status"] == "LOCKED":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PranaError.ACCOUNT_LOCKED)
    if row["status"] != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PranaError.ACCOUNT_INACTIVE)

    if not verify_password(body.password, row["password_hash"]):
        await _log(db, str(row["pa_id"]), "PASSWORD", "FAILED", "WRONG_PASSWORD", ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.INVALID_CREDENTIALS)

    await _log(db, str(row["pa_id"]), "PASSWORD", "SUCCESS", None, ip)

    step_token = _secrets.token_urlsafe(32)
    await request.app.state.redis.setex(f"pa_step:{step_token}", 300, str(row["pa_id"]))

    return {
        "requires_totp": True,
        "requires_totp_setup": row["totp_configured_at"] is None,
        "step_token": step_token,
    }


@router.post("/totp", status_code=status.HTTP_200_OK)
async def verify_totp(body: PATOTPIn, request: Request, response: Response, db: DbConn):
    """Step 2: PA TOTP verify. Locks after 3 failures (stricter than OA's 5)."""
    redis_client = request.app.state.redis
    raw = await redis_client.get(f"pa_step:{body.step_token}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.STEP_TOKEN_EXPIRED)

    await redis_client.delete(f"pa_step:{body.step_token}")
    pa_id = raw.decode()

    row = await db.fetchrow(
        "SELECT totp_secret_enc, failed_totp_count, status FROM portal_admin WHERE pa_id=$1",
        pa_id,
    )
    if not row or not row["totp_secret_enc"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.TOTP_NOT_CONFIGURED)

    if row["status"] == "LOCKED":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PranaError.ACCOUNT_LOCKED)

    totp_svc = TOTPService()
    dev_dek = b"\x00" * 32
    valid = totp_svc.verify(body.code, row["totp_secret_enc"], dev_dek)

    # PA lock threshold = 3 (from platform_config pa_totp_lock_threshold)
    lock_threshold = await _get_pa_lock_threshold(db)
    ip = _get_client_ip(request)

    if not valid:
        new_count = row["failed_totp_count"] + 1
        if new_count >= lock_threshold:
            await db.execute(
                "UPDATE portal_admin SET status='LOCKED', failed_totp_count=$2 WHERE pa_id=$1",
                pa_id, new_count,
            )
            await _log(db, pa_id, "TOTP", "FAILED", "TOTP_LOCKOUT", ip)
            # PA lockout is not auto-unlocked — requires another PA to unlock
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PranaError.ACCOUNT_LOCKED)

        await db.execute(
            "UPDATE portal_admin SET failed_totp_count=$2 WHERE pa_id=$1",
            pa_id, new_count,
        )
        await _log(db, pa_id, "TOTP", "FAILED", "WRONG_TOTP", ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.INVALID_TOTP)

    await db.execute(
        "UPDATE portal_admin SET failed_totp_count=0, last_login_at=NOW() WHERE pa_id=$1",
        pa_id,
    )
    await _log(db, pa_id, "TOTP", "SUCCESS", None, ip)

    session_svc = SessionService(db, request.app.state.jwt_service)
    tokens = await session_svc.create(
        user_type="portal_admin",
        user_id=pa_id,
        tenant_id=None,
        role="portal_admin",
        ip_address=ip,
        user_agent=request.headers.get("User-Agent", ""),
        max_concurrent=5,
    )

    _set_refresh_cookie(response, tokens["refresh_token"])
    return {
        "access_token": tokens["access_token"],
        "token_type": "bearer",
        "expires_at": tokens["expires_at"],
    }


@router.post("/totp-setup/init", status_code=status.HTTP_200_OK)
async def totp_setup_init(request: Request, db: DbConn):
    """PA TOTP first-time setup via step_token. Returns QR URI + backup codes."""
    import json
    body = await request.json()
    step_token = body.get("step_token")
    if not step_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PranaError.MISSING_STEP_TOKEN)

    raw = await request.app.state.redis.get(f"pa_step:{step_token}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.STEP_TOKEN_EXPIRED)

    pa_id = raw.decode()
    row = await db.fetchrow("SELECT email, totp_configured_at FROM portal_admin WHERE pa_id=$1", pa_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.USER_NOT_FOUND)
    if row["totp_configured_at"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PranaError.TOTP_ALREADY_CONFIGURED)

    totp_svc = TOTPService()
    secret = totp_svc.generate_secret()
    prefix = pa_id[:4].upper()
    codes = totp_svc.generate_backup_codes(prefix)
    plaintexts = [c[0] for c in codes]
    hashes     = [c[1] for c in codes]

    setup_token = _secrets.token_urlsafe(32)
    await request.app.state.redis.setex(
        f"pa_totp_setup:{setup_token}", 600,
        json.dumps({"secret": secret, "hashes": hashes, "pa_id": pa_id}),
    )
    await request.app.state.redis.expire(f"pa_step:{step_token}", 600)

    provisioning_uri = totp_svc.provisioning_uri(secret, row["email"])
    return {"provisioning_uri": provisioning_uri, "backup_codes": plaintexts, "setup_token": setup_token}


@router.post("/totp-setup/confirm", status_code=status.HTTP_200_OK)
async def totp_setup_confirm(request: Request, response: Response, db: DbConn):
    """Confirm PA TOTP first code, persist secret, issue JWT session."""
    import json
    from services.encryption_service import aes_encrypt
    import pyotp, datetime as _dt

    body = await request.json()
    setup_token = body.get("setup_token")
    code = body.get("code", "")

    raw = await request.app.state.redis.get(f"pa_totp_setup:{setup_token}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.SETUP_TOKEN_EXPIRED)

    data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
    secret = data["secret"]
    hashes = data["hashes"]
    pa_id  = data["pa_id"]

    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.INVALID_CODE)

    await request.app.state.redis.delete(f"pa_totp_setup:{setup_token}")

    dev_dek = b"\x00" * 32
    from services.encryption_service import aes_encrypt
    enc_secret = aes_encrypt(secret, dev_dek)
    now = _dt.datetime.now(tz=_dt.timezone.utc)

    async with db.transaction():
        await db.execute(
            "UPDATE portal_admin SET totp_secret_enc=$2, totp_configured_at=$3, failed_totp_count=0 WHERE pa_id=$1",
            pa_id, enc_secret, now,
        )
        await db.executemany(
            "INSERT INTO backup_code (user_type, user_id, code_hash) VALUES ($1, $2, $3)",
            [("portal_admin", pa_id, h) for h in hashes],
        )

    await _log(db, pa_id, "TOTP", "SUCCESS", None, _get_client_ip(request))

    ip = _get_client_ip(request)
    session_svc = SessionService(db, request.app.state.jwt_service)
    tokens = await session_svc.create(
        user_type="portal_admin", user_id=pa_id, tenant_id=None, role="portal_admin",
        ip_address=ip, user_agent=request.headers.get("User-Agent", ""), max_concurrent=5,
    )
    _set_refresh_cookie(response, tokens["refresh_token"])
    return {"access_token": tokens["access_token"], "token_type": "bearer",
            "expires_at": tokens["expires_at"], "totp_configured": True}


@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh(request: Request, response: Response, db: DbConn):
    refresh_token = request.cookies.get("prana_refresh")
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.NO_REFRESH_TOKEN)

    session_svc = SessionService(db, request.app.state.jwt_service)
    tokens = await session_svc.rotate_refresh(
        refresh_token=refresh_token,
        ip_address=_get_client_ip(request),
    )
    if not tokens:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.REFRESH_INVALID)

    _set_refresh_cookie(response, tokens["refresh_token"])
    return {"access_token": tokens["access_token"], "expires_at": tokens["expires_at"]}


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(request: Request, response: Response, db: DbConn, current=Depends(require_pa)):
    session_svc = SessionService(db, request.app.state.jwt_service)
    await session_svc.revoke(current.session_id, reason="LOGOUT")
    response.delete_cookie("prana_refresh", path="/auth/admin/refresh")
    return {"message": SuccessCode.LOGOUT_SUCCESS}


async def _get_pa_lock_threshold(db) -> int:
    row = await db.fetchrow(
        "SELECT config_value FROM platform_config WHERE config_key='pa_totp_lock_threshold'"
    )
    return int(row["config_value"]) if row else 3


async def _log(db, pa_id, attempt_type, outcome, reason, ip):
    await db.execute(
        """
        INSERT INTO login_attempt_log
          (user_type, user_id, attempt_type, outcome, failure_reason, ip_address, entry_point)
        VALUES ('portal_admin', $1, $2, $3, $4, $5::inet, 'ADMIN_PORTAL')
        """,
        pa_id, attempt_type, outcome, reason, ip,
    )
