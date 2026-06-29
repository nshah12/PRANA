"""
OA-user auth flow (OA-Operator, OA-Admin, CHRO, CFO, Tenant CISO):
  1. POST /auth/org/login   — email + password → {requires_totp: true}
  2. POST /auth/org/totp    — TOTP verify → JWT + httpOnly refresh cookie
  3. POST /auth/org/refresh — silent token refresh
  4. POST /auth/org/logout  — revoke session

force_reset=TRUE → must change password before any other action (checked in step 1).
Lock threshold: 5 failed TOTP attempts (platform config: oa_totp_lock_threshold).
"""
import secrets as _secrets
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr

from dependencies import AuthUser, DbConn
from services.encryption_service import verify_password
from services.otp_service import OTPService
from services.totp_service import TOTPService
from services.session_service import SessionService
from errors import PranaError

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class OALoginIn(BaseModel):
    email: EmailStr
    password: str

class OATOTPIn(BaseModel):
    step_token: str
    code: str            # 6-digit TOTP or backup code

class PasswordResetIn(BaseModel):
    step_token: str      # from login response when force_reset=TRUE
    new_password: str    # min 12 chars enforced here


# ── Helpers ───────────────────────────────────────────────────────────────────

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
        path="/auth/org/refresh",
    )


async def _get_config_int(db, key: str, default: int) -> int:
    row = await db.fetchrow("SELECT config_value FROM platform_config WHERE config_key=$1", key)
    return int(row["config_value"]) if row else default


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/login", status_code=status.HTTP_200_OK)
async def login(body: OALoginIn, request: Request, db: DbConn):
    """Step 1: Email + password. Returns step_token for TOTP step."""
    row = await db.fetchrow(
        """
        SELECT oa_user_id, tenant_id, role, password_hash, temp_password_hash,
               force_reset, totp_configured_at, failed_totp_count, status
        FROM oa_user WHERE email = $1
        """,
        body.email,
    )

    ip = _get_client_ip(request)

    # Use same error for unknown email vs wrong password (no enumeration)
    if not row:
        await _log_attempt(db, "oa_user", None, "PASSWORD", "FAILED", "UNKNOWN_USER", ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.INVALID_CREDENTIALS)

    if row["status"] == "LOCKED":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PranaError.ACCOUNT_LOCKED)
    if row["status"] in ("SUSPENDED", "DEACTIVATED"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PranaError.ACCOUNT_INACTIVE)

    # Check temp_password_hash first (set on account creation), then permanent
    hash_to_check = row["temp_password_hash"] or row["password_hash"]
    if not hash_to_check or not verify_password(body.password, hash_to_check):
        await _log_attempt(db, "oa_user", str(row["oa_user_id"]), "PASSWORD", "FAILED", "WRONG_PASSWORD", ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.INVALID_CREDENTIALS)

    await _log_attempt(db, "oa_user", str(row["oa_user_id"]), "PASSWORD", "SUCCESS", None, ip)

    # force_reset: must change password before proceeding to TOTP
    if row["force_reset"]:
        step_token = _secrets.token_urlsafe(32)
        await request.app.state.redis.setex(
            f"reset:{step_token}", 900,
            f"{row['oa_user_id']}:{row['tenant_id']}:{row['role']}",
        )
        return {"requires_password_reset": True, "step_token": step_token}

    # Issue step token for TOTP
    step_token = _secrets.token_urlsafe(32)
    await request.app.state.redis.setex(
        f"step:{step_token}", 300,
        f"{row['oa_user_id']}:{row['tenant_id']}:{row['role']}",
    )

    return {
        "requires_totp": True,
        "requires_totp_setup": row["totp_configured_at"] is None,
        "step_token": step_token,
    }


@router.post("/password-reset", status_code=status.HTTP_200_OK)
async def password_reset(body: PasswordResetIn, request: Request, db: DbConn):
    """Complete force_reset flow. Clears temp_password_hash, sets new hash, issues TOTP step."""
    raw = await request.app.state.redis.get(f"reset:{body.step_token}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.STEP_TOKEN_EXPIRED)

    if len(body.new_password) < 12:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PranaError.PASSWORD_TOO_SHORT)

    from services.encryption_service import hash_password
    oa_user_id, tenant_id, role = raw.decode().split(":")

    await db.execute(
        """
        UPDATE oa_user
        SET password_hash=$2, temp_password_hash=NULL, force_reset=FALSE
        WHERE oa_user_id=$1
        """,
        oa_user_id, hash_password(body.new_password),
    )
    await request.app.state.redis.delete(f"reset:{body.step_token}")

    step_token = _secrets.token_urlsafe(32)
    await request.app.state.redis.setex(
        f"step:{step_token}", 300,
        f"{oa_user_id}:{tenant_id}:{role}",
    )
    return {"requires_totp": True, "step_token": step_token}


@router.post("/totp", status_code=status.HTTP_200_OK)
async def verify_totp(body: OATOTPIn, request: Request, response: Response, db: DbConn):
    """Step 2: Verify TOTP. Issues JWT + sets httpOnly refresh cookie."""
    redis_client = request.app.state.redis
    raw = await redis_client.get(f"step:{body.step_token}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.STEP_TOKEN_EXPIRED)

    await redis_client.delete(f"step:{body.step_token}")
    oa_user_id, tenant_id, role = raw.decode().split(":")

    row = await db.fetchrow(
        "SELECT totp_secret_enc, failed_totp_count, status FROM oa_user WHERE oa_user_id=$1",
        oa_user_id,
    )
    if not row or not row["totp_secret_enc"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.TOTP_NOT_CONFIGURED)

    if row["status"] == "LOCKED":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PranaError.ACCOUNT_LOCKED)

    totp_svc = TOTPService()
    dev_dek = b"\x00" * 32   # dev placeholder — prod unwraps from KMS
    valid = totp_svc.verify(body.code, row["totp_secret_enc"], dev_dek)

    lock_threshold = await _get_config_int(db, "oa_totp_lock_threshold", 5)
    ip = _get_client_ip(request)

    if not valid:
        new_count = row["failed_totp_count"] + 1
        if new_count >= lock_threshold:
            await db.execute(
                "UPDATE oa_user SET status='LOCKED', failed_totp_count=$2 WHERE oa_user_id=$1",
                oa_user_id, new_count,
            )
            await _log_attempt(db, "oa_user", oa_user_id, "TOTP", "FAILED", "TOTP_LOCKOUT", ip)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PranaError.ACCOUNT_LOCKED)

        await db.execute(
            "UPDATE oa_user SET failed_totp_count=$2 WHERE oa_user_id=$1",
            oa_user_id, new_count,
        )
        await _log_attempt(db, "oa_user", oa_user_id, "TOTP", "FAILED", "WRONG_TOTP", ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.INVALID_TOTP)

    await db.execute(
        "UPDATE oa_user SET failed_totp_count=0, last_login_at=NOW() WHERE oa_user_id=$1",
        oa_user_id,
    )
    await _log_attempt(db, "oa_user", oa_user_id, "TOTP", "SUCCESS", None, ip)

    session_svc = SessionService(db, request.app.state.jwt_service)
    tokens = await session_svc.create(
        user_type="oa_user",
        user_id=oa_user_id,
        tenant_id=tenant_id,
        role=role,
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
    """TOTP first-time setup using step_token (no JWT yet). Returns QR URI + backup codes."""
    import json
    body = await request.json()
    step_token = body.get("step_token")
    if not step_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PranaError.MISSING_STEP_TOKEN)

    raw = await request.app.state.redis.get(f"step:{step_token}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.STEP_TOKEN_EXPIRED)

    oa_user_id, tenant_id, role = raw.decode().split(":")

    row = await db.fetchrow("SELECT email, totp_configured_at FROM oa_user WHERE oa_user_id=$1", oa_user_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.USER_NOT_FOUND)
    if row["totp_configured_at"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PranaError.TOTP_ALREADY_CONFIGURED)

    totp_svc = TOTPService()
    secret = totp_svc.generate_secret()
    prefix = oa_user_id[:4].upper()
    codes = totp_svc.generate_backup_codes(prefix)
    plaintexts = [c[0] for c in codes]
    hashes     = [c[1] for c in codes]

    setup_token = _secrets.token_urlsafe(32)
    # Store tenant_id + role now so confirm doesn't depend on step_token still being alive
    await request.app.state.redis.setex(
        f"totp_setup:{setup_token}", 600,
        json.dumps({"secret": secret, "hashes": hashes, "user_type": "oa_user",
                    "user_id": oa_user_id, "tenant_id": tenant_id, "role": role}),
    )
    # Extend step_token TTL to cover QR scan window
    await request.app.state.redis.expire(f"step:{step_token}", 600)

    provisioning_uri = totp_svc.provisioning_uri(secret, row["email"])
    return {"provisioning_uri": provisioning_uri, "backup_codes": plaintexts, "setup_token": setup_token}


@router.post("/totp-setup/confirm", status_code=status.HTTP_200_OK)
async def totp_setup_confirm(request: Request, response: Response, db: DbConn):
    """Confirm first TOTP code, persist secret, then issue full JWT session."""
    import json
    from services.encryption_service import aes_encrypt
    import pyotp, datetime as _dt

    body = await request.json()
    setup_token = body.get("setup_token")
    code = body.get("code", "")

    raw = await request.app.state.redis.get(f"totp_setup:{setup_token}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.SETUP_TOKEN_EXPIRED)

    data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
    secret     = data["secret"]
    hashes     = data["hashes"]
    oa_user_id = data["user_id"]
    tenant_id  = data["tenant_id"]
    role       = data["role"]

    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.INVALID_CODE)

    await request.app.state.redis.delete(f"totp_setup:{setup_token}")

    dev_dek = b"\x00" * 32
    enc_secret = aes_encrypt(secret, dev_dek)
    now = _dt.datetime.now(tz=_dt.timezone.utc)

    async with db.transaction():
        await db.execute(
            "UPDATE oa_user SET totp_secret_enc=$2, totp_configured_at=$3, failed_totp_count=0 WHERE oa_user_id=$1",
            oa_user_id, enc_secret, now,
        )
        await db.executemany(
            "INSERT INTO backup_code (user_type, user_id, code_hash) VALUES ($1, $2, $3)",
            [("oa_user", oa_user_id, h) for h in hashes],
        )

    ip = _get_client_ip(request)
    session_svc = SessionService(db, request.app.state.jwt_service)
    tokens = await session_svc.create(
        user_type="oa_user", user_id=oa_user_id, tenant_id=tenant_id, role=role,
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
async def logout(current: AuthUser, request: Request, response: Response, db: DbConn):
    session_svc = SessionService(db, request.app.state.jwt_service)
    await session_svc.revoke(current.session_id, reason="LOGOUT")
    response.delete_cookie("prana_refresh", path="/auth/org/refresh")
    return {"message": "Logged out"}


async def _log_attempt(db, user_type, user_id, attempt_type, outcome, reason, ip):
    await db.execute(
        """
        INSERT INTO login_attempt_log
          (user_type, user_id, attempt_type, outcome, failure_reason, ip_address, entry_point)
        VALUES ($1, $2, $3, $4, $5, $6::inet, 'WEB_PORTAL')
        """,
        user_type, user_id, attempt_type, outcome, reason, ip,
    )
