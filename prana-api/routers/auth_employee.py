"""
Employee auth flow — password + TOTP (portal) / password + biometric or TOTP (mobile).

  POST /auth/employee/login                    — identifier + password → step_token
  POST /auth/employee/totp                     — step_token + TOTP code → JWT
  POST /auth/employee/biometric                — step_token + device_id → JWT  (mobile, OS-trusted)
  POST /auth/employee/setup/password           — change temp password (force_reset=TRUE)
  POST /auth/employee/setup/totp/init          — get TOTP provisioning URI
  POST /auth/employee/setup/totp/confirm       — confirm TOTP code, mark configured
  POST /auth/employee/setup/consent            — accept DPDP consent → JWT
  POST /auth/employee/device/register          — register mobile device
  POST /auth/employee/device/{id}/biometric    — enroll biometric on device
  DELETE /auth/employee/device/{id}            — deregister device
  POST /auth/employee/refresh                  — silent refresh from httpOnly cookie
  POST /auth/employee/logout                   — revoke session

Cross-org intelligence: pan_token is the identity anchor.
If employee_user exists + status=ACTIVE → existing PRANA member, no activation needed.
"""
import json
import secrets
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from dependencies import AuthUser, DbConn, Employee
from services.password_service import verify_password, hash_password, needs_rehash
from services.totp_service import TOTPService
from services.session_service import SessionService
from services.encryption_service import aes_encrypt, aes_decrypt
from errors import PranaError

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class LoginIn(BaseModel):
    identifier: str       # email OR mobile (E.164 or 10-digit)
    password: str
    device_id: Optional[str] = None   # mobile only — triggers biometric check

class TOTPVerifyIn(BaseModel):
    step_token: str
    code: str             # 6-digit TOTP or 8-char backup code

class BiometricIn(BaseModel):
    step_token: str
    device_id: str        # UUID of registered device

class PasswordChangeIn(BaseModel):
    step_token: str
    new_password: str

class TOTPInitIn(BaseModel):
    step_token: str

class TOTPConfirmIn(BaseModel):
    step_token: str
    code: str

class ConsentIn(BaseModel):
    step_token: str

class DeviceRegisterIn(BaseModel):
    platform: str              # ANDROID | IOS
    public_key: str            # WebAuthn/FIDO2 public key — required by device_credential schema
    device_fingerprint: Optional[str] = None
    push_token: Optional[str] = None

class RefreshIn(BaseModel):
    pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    return forwarded.split(",")[0].strip() if forwarded else request.client.host


def _set_refresh_cookie(response: Response, refresh_token: str, max_age: int) -> None:
    from config import get_settings
    is_dev = get_settings().app_env == "development"
    response.set_cookie(
        key="prana_refresh",
        value=refresh_token,
        httponly=True,
        secure=not is_dev,   # False in dev (HTTP localhost), True in prod (HTTPS)
        samesite="lax" if is_dev else "strict",
        max_age=max_age,
        # In dev, use "/" so Vite proxy (/api/auth/employee/refresh) still sends the cookie.
        # In prod, scope to the exact path for security.
        path="/" if is_dev else "/auth/employee/refresh",
    )


def _normalise_identifier(raw: str) -> tuple[str, str]:
    """Return (column_name, value) for a mobile or email identifier."""
    raw = raw.strip()
    if "@" in raw:
        return "email", raw.lower()
    # Strip country code if present; store as E.164
    digits = raw.replace("+91", "").replace(" ", "").replace("-", "")
    if len(digits) == 10 and digits[0] in "6789":
        return "mobile", f"+91{digits}"
    return "mobile", raw   # pass through, DB will reject


async def _make_step_token(redis, user_id: str, pan_token: str, next_step: str, ttl: int = 300) -> str:
    token = secrets.token_urlsafe(32)
    payload = json.dumps({"user_id": user_id, "pan_token": pan_token, "next": next_step})
    await redis.setex(f"step:{token}", ttl, payload)
    return token


async def _consume_step_token(redis, token: str, expected_next: str) -> dict:
    raw = await redis.get(f"step:{token}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.STEP_TOKEN_EXPIRED)
    data = json.loads(raw)
    if data.get("next") != expected_next:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PranaError.INVALID_STEP)
    await redis.delete(f"step:{token}")
    return data


async def _peek_step_token(redis, token: str, expected_next: str) -> dict:
    """Read without deleting — caller issues a new step token before this one is consumed."""
    raw = await redis.get(f"step:{token}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.STEP_TOKEN_EXPIRED)
    data = json.loads(raw)
    if data.get("next") != expected_next:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PranaError.INVALID_STEP)
    return data


async def _issue_jwt(request: Request, response: Response, db, user_id: str, ip: str) -> dict:
    jwt_ttl = 60
    refresh_ttl = 7
    try:
        rows = await db.fetch(
            "SELECT config_key, config_value FROM platform_config WHERE config_key IN ('jwt_ttl_minutes','refresh_token_ttl_days')"
        )
        for r in (rows or []):
            if r["config_key"] == "jwt_ttl_minutes":
                jwt_ttl = int(r["config_value"])
            elif r["config_key"] == "refresh_token_ttl_days":
                refresh_ttl = int(r["config_value"])
    except Exception:
        pass  # use defaults if config unavailable

    session_svc = SessionService(db, request.app.state.jwt_service)
    tokens = await session_svc.create(
        user_type="employee",
        user_id=user_id,
        tenant_id=None,
        role=None,
        ip_address=ip,
        user_agent=request.headers.get("User-Agent", ""),
        jwt_ttl_minutes=jwt_ttl,
        refresh_ttl_days=refresh_ttl,
        max_concurrent=5,
    )
    await db.execute(
        "UPDATE employee_user SET last_login_at=NOW() WHERE employee_user_id=$1",
        user_id,
    )
    _set_refresh_cookie(response, tokens["refresh_token"], max_age=7 * 86400)
    return {
        "access_token": tokens["access_token"],
        "token_type": "bearer",
        "expires_at": tokens["expires_at"],
    }


async def _get_totp_lock_threshold(db) -> int:
    row = await db.fetchrow("SELECT config_value FROM platform_config WHERE config_key='oa_totp_lock_threshold'")
    return int(row["config_value"]) if row else 5


# ── Step 1: Password login ────────────────────────────────────────────────────

@router.post("/login", status_code=status.HTTP_200_OK)
async def login(body: LoginIn, request: Request, db: DbConn):
    """
    Factor 1: identifier + password.
    Returns step_token with `next` field telling the client what to do next:
      force_password  — must change temp password first
      totp_setup      — first login, TOTP not configured yet
      consent         — consent not accepted yet
      totp            — proceed to TOTP (portal + mobile fallback)
      biometric       — proceed to biometric (mobile, if enrolled)
    """
    col, value = _normalise_identifier(body.identifier)
    _COLS = "employee_user_id, pan_token, password_hash, status, force_reset, totp_configured_at, consent_status, failed_totp_count"
    if col == "email":
        row = await db.fetchrow(
            "SELECT employee_user_id, pan_token, password_hash, status, force_reset, totp_configured_at, consent_status, failed_totp_count FROM employee_user WHERE email = $1",
            value,
        )
    else:
        row = await db.fetchrow(
            "SELECT employee_user_id, pan_token, password_hash, status, force_reset, totp_configured_at, consent_status, failed_totp_count FROM employee_user WHERE mobile = $1",
            value,
        )

    # Constant-time guard: always hash compare even if user not found
    dummy_hash = "$argon2id$v=19$m=65536,t=2,p=2$AAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    candidate_hash = row["password_hash"] if row else dummy_hash

    valid = verify_password(body.password, candidate_hash)

    if not row or not valid:
        if row:
            await db.execute(
                "INSERT INTO login_attempt_log (user_type,user_id,attempt_type,outcome,failure_reason,ip_address,entry_point) "
                "VALUES ('employee',$1,'PASSWORD','FAILED','WRONG_PASSWORD',$2::inet,'PORTAL')",
                row["employee_user_id"], _get_client_ip(request),
            )
            kafka = getattr(request.app.state, "kafka_producer", None)
            if kafka:
                await kafka.auth_event({
                    "event_type": "USER_LOGIN_FAILED",
                    "user_id":    str(row["employee_user_id"]),
                    "user_type":  "employee",
                    "reason":     "WRONG_PASSWORD",
                    "ip_address": _get_client_ip(request),
                })
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.INVALID_CREDENTIALS)

    if row["status"] == "LOCKED":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PranaError.ACCOUNT_LOCKED)
    if row["status"] in ("SUSPENDED", "PENDING_ACTIVATION"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PranaError.ACCOUNT_NOT_ACTIVE)

    user_id = str(row["employee_user_id"])
    pan_token = row["pan_token"]
    redis = request.app.state.redis

    # Rehash in background if params changed
    if needs_rehash(candidate_hash):
        new_hash = hash_password(body.password)
        await db.execute("UPDATE employee_user SET password_hash=$2 WHERE employee_user_id=$1", user_id, new_hash)

    await db.execute(
        "INSERT INTO login_attempt_log (user_type,user_id,attempt_type,outcome,ip_address,entry_point) "
        "VALUES ('employee',$1,'PASSWORD','SUCCESS',$2::inet,'PORTAL')",
        user_id, _get_client_ip(request),
    )

    # Determine next step in priority order
    if row["force_reset"]:
        token = await _make_step_token(redis, user_id, pan_token, "force_password")
        return {"next": "force_password", "step_token": token}

    if row["totp_configured_at"] is None:
        token = await _make_step_token(redis, user_id, pan_token, "totp_setup")
        return {"next": "totp_setup", "step_token": token}

    if row["consent_status"] == "PENDING":
        token = await _make_step_token(redis, user_id, pan_token, "consent")
        return {"next": "consent", "step_token": token}

    # Check biometric eligibility (mobile only — device_id supplied in request)
    if body.device_id:
        device = await db.fetchrow(
            "SELECT device_credential_id FROM device_credential WHERE device_fingerprint_hash=$1 "
            "AND employee_user_id=$2 AND biometric_enrolled=TRUE AND revoked=FALSE",
            body.device_id, user_id,
        )
        if device:
            token = await _make_step_token(redis, user_id, pan_token, "biometric")
            return {"next": "biometric", "step_token": token}

    token = await _make_step_token(redis, user_id, pan_token, "totp")
    return {"next": "totp", "step_token": token}


# ── Step 2a: TOTP verification ────────────────────────────────────────────────

@router.post("/totp", status_code=status.HTTP_200_OK)
async def verify_totp(body: TOTPVerifyIn, request: Request, response: Response, db: DbConn):
    """Factor 2: TOTP code. Issues JWT on success."""
    redis = request.app.state.redis
    data = await _consume_step_token(redis, body.step_token, "totp")
    user_id = data["user_id"]

    row = await db.fetchrow(
        "SELECT totp_secret_enc, failed_totp_count, status FROM employee_user WHERE employee_user_id=$1",
        user_id,
    )
    if not row or not row["totp_secret_enc"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.TOTP_NOT_CONFIGURED)
    if row["status"] == "LOCKED":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PranaError.ACCOUNT_LOCKED)

    totp_svc = TOTPService()
    dev_dek = b"\x00" * 32  # DEV: placeholder. Prod: unwrap from KMS.
    valid = totp_svc.verify(body.code, row["totp_secret_enc"], dev_dek)

    lock_threshold = await _get_totp_lock_threshold(db)

    if not valid:
        new_count = row["failed_totp_count"] + 1
        if new_count >= lock_threshold:
            await db.execute(
                "UPDATE employee_user SET status='LOCKED', failed_totp_count=$2 WHERE employee_user_id=$1",
                user_id, new_count,
            )
            kafka = getattr(request.app.state, "kafka_producer", None)
            if kafka:
                await kafka.auth_event({
                    "event_type": "TOTP_FAILED",
                    "user_id":    user_id,
                    "user_type":  "employee",
                    "fail_count": new_count,
                    "locked":     True,
                    "ip_address": _get_client_ip(request),
                })
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PranaError.ACCOUNT_LOCKED)
        await db.execute(
            "UPDATE employee_user SET failed_totp_count=$2 WHERE employee_user_id=$1",
            user_id, new_count,
        )
        kafka = getattr(request.app.state, "kafka_producer", None)
        if kafka:
            await kafka.auth_event({
                "event_type": "TOTP_FAILED",
                "user_id":    user_id,
                "user_type":  "employee",
                "fail_count": new_count,
                "locked":     False,
                "ip_address": _get_client_ip(request),
            })
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.INVALID_TOTP)

    await db.execute(
        "UPDATE employee_user SET failed_totp_count=0 WHERE employee_user_id=$1", user_id,
    )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.auth_event({
            "event_type": "SESSION_CREATED",
            "user_id":    user_id,
            "user_type":  "employee",
            "ip_address": _get_client_ip(request),
        })
    return await _issue_jwt(request, response, db, user_id, _get_client_ip(request))


# ── Step 2b: Biometric (mobile, trust-based) ──────────────────────────────────

@router.post("/biometric", status_code=status.HTTP_200_OK)
async def verify_biometric(body: BiometricIn, request: Request, response: Response, db: DbConn):
    """
    Mobile biometric auth. OS has already verified fingerprint — we trust it.
    Validate that the device is still enrolled and not revoked, then issue JWT.
    """
    redis = request.app.state.redis
    data = await _consume_step_token(redis, body.step_token, "biometric")
    user_id = data["user_id"]

    device = await db.fetchrow(
        "SELECT device_credential_id FROM device_credential WHERE device_fingerprint_hash=$1 "
        "AND employee_user_id=$2 AND biometric_enrolled=TRUE AND revoked=FALSE",
        body.device_id, user_id,
    )
    if not device:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.DEVICE_NOT_ENROLLED)

    await db.execute(
        "UPDATE device_credential SET last_used_at=NOW() WHERE device_fingerprint_hash=$1", body.device_id,
    )
    return await _issue_jwt(request, response, db, user_id, _get_client_ip(request))


# ── Setup: Force password change ──────────────────────────────────────────────

@router.post("/setup/password", status_code=status.HTTP_200_OK)
async def setup_password(body: PasswordChangeIn, request: Request, db: DbConn):
    """
    Forced on first login when force_reset=TRUE (temp password assigned at activation).
    After success, reissues step_token pointing to next required step (totp_setup or consent or totp).
    """
    redis = request.app.state.redis
    data = await _peek_step_token(redis, body.step_token, "force_password")
    user_id = data["user_id"]
    pan_token = data["pan_token"]

    if len(body.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PranaError.PASSWORD_TOO_SHORT)

    new_hash = hash_password(body.new_password)
    await db.execute(
        "UPDATE employee_user SET password_hash=$2, force_reset=FALSE WHERE employee_user_id=$1",
        user_id, new_hash,
    )

    # Determine next forced step
    row = await db.fetchrow(
        "SELECT totp_configured_at, consent_status FROM employee_user WHERE employee_user_id=$1", user_id,
    )
    if row["totp_configured_at"] is None:
        next_step = "totp_setup"
    elif row["consent_status"] == "PENDING":
        next_step = "consent"
    else:
        next_step = "totp"

    token = await _make_step_token(redis, user_id, pan_token, next_step)
    return {"next": next_step, "step_token": token}


# ── Setup: TOTP init ──────────────────────────────────────────────────────────

@router.post("/setup/totp/init", status_code=status.HTTP_200_OK)
async def setup_totp_init(body: TOTPInitIn, request: Request, db: DbConn):
    """
    Returns TOTP provisioning URI for QR code display.
    Does NOT delete the step_token — confirm endpoint consumes it.
    """
    redis = request.app.state.redis
    raw = await redis.get(f"step:{body.step_token}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.STEP_TOKEN_EXPIRED)
    data = json.loads(raw)
    if data.get("next") != "totp_setup":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PranaError.INVALID_STEP)

    totp_svc = TOTPService()
    dev_dek = b"\x00" * 32  # DEV placeholder

    # Generate new secret only if not already staged in a previous init call
    existing = await db.fetchval(
        "SELECT totp_secret_enc FROM employee_user WHERE employee_user_id=$1", data["user_id"],
    )
    row = await db.fetchrow(
        "SELECT email, mobile FROM employee_user WHERE employee_user_id=$1", data["user_id"],
    )
    account_label = row["email"] or row["mobile"] or data["user_id"]

    if existing and existing.startswith("STAGED:"):
        # Re-use the previously staged secret (idempotent re-init)
        encrypted = existing[7:]
        secret_b32 = aes_decrypt(encrypted, dev_dek)
    else:
        secret_b32 = totp_svc.generate_secret()
        encrypted = aes_encrypt(secret_b32, dev_dek)
        # Stage the encrypted secret temporarily (not yet confirmed)
        await db.execute(
            "UPDATE employee_user SET totp_secret_enc=$2 WHERE employee_user_id=$1",
            data["user_id"], f"STAGED:{encrypted}",
        )

    uri = totp_svc.provisioning_uri(secret_b32, account_label, issuer="PRANA")
    return {"provisioning_uri": uri, "secret_key": secret_b32}


# ── Setup: TOTP confirm ───────────────────────────────────────────────────────

@router.post("/setup/totp/confirm", status_code=status.HTTP_200_OK)
async def setup_totp_confirm(body: TOTPConfirmIn, request: Request, db: DbConn):
    """Verify the first TOTP code, mark TOTP as configured, advance to next step."""
    redis = request.app.state.redis
    data = await _peek_step_token(redis, body.step_token, "totp_setup")
    user_id = data["user_id"]
    pan_token = data["pan_token"]

    row = await db.fetchrow(
        "SELECT totp_secret_enc, consent_status FROM employee_user WHERE employee_user_id=$1", user_id,
    )
    if not row or not row["totp_secret_enc"] or not row["totp_secret_enc"].startswith("STAGED:"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PranaError.TOTP_INIT_REQUIRED)

    encrypted = row["totp_secret_enc"][7:]
    totp_svc = TOTPService()
    dev_dek = b"\x00" * 32

    valid = totp_svc.verify(body.code, encrypted, dev_dek)
    if not valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.INVALID_TOTP_CODE)

    # Confirm: remove STAGED prefix, set totp_configured_at
    await db.execute(
        "UPDATE employee_user SET totp_secret_enc=$2, totp_configured_at=NOW() WHERE employee_user_id=$1",
        user_id, encrypted,
    )

    next_step = "consent" if row["consent_status"] == "PENDING" else "totp"
    token = await _make_step_token(redis, user_id, pan_token, next_step)
    return {"next": next_step, "step_token": token}


# ── Setup: Consent ────────────────────────────────────────────────────────────

@router.post("/setup/consent", status_code=status.HTTP_200_OK)
async def setup_consent(body: ConsentIn, request: Request, response: Response, db: DbConn):
    """Employee accepts DPDP consent. Final setup step — issues JWT."""
    redis = request.app.state.redis
    data = await _consume_step_token(redis, body.step_token, "consent")
    user_id = data["user_id"]

    await db.execute(
        "UPDATE employee_user SET consent_status='GRANTED', activated_at=COALESCE(activated_at, NOW()) "
        "WHERE employee_user_id=$1",
        user_id,
    )
    return await _issue_jwt(request, response, db, user_id, _get_client_ip(request))


# ── Device management ─────────────────────────────────────────────────────────

@router.post("/device/register", status_code=status.HTTP_201_CREATED)
async def register_device(body: DeviceRegisterIn, request: Request, db: DbConn,
                           current: Employee):
    """Register a mobile device. Returns device_id for subsequent biometric enrollment."""
    if body.platform not in ("ANDROID", "IOS"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PranaError.INVALID_PLATFORM)

    device_id = await db.fetchval(
        """
        INSERT INTO device_credential
          (employee_user_id, platform, device_fingerprint_hash, push_token, public_key)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (public_key) DO UPDATE SET last_used_at=NOW()
        RETURNING device_credential_id
        """,
        current.user_id, body.platform, body.device_fingerprint,
        body.push_token, body.public_key,
    )
    return {"device_id": str(device_id)}


@router.post("/device/{device_id}/biometric", status_code=status.HTTP_200_OK)
async def enroll_biometric(device_id: UUID, request: Request, db: DbConn,
                            current: Employee):
    """Mark device as biometric-enrolled. Employee must already be authenticated."""
    updated = await db.fetchval(
        """
        UPDATE device_credential SET biometric_enrolled=TRUE
        WHERE device_credential_id=$1 AND employee_user_id=$2 AND revoked=FALSE
        RETURNING device_credential_id
        """,
        device_id, current.user_id,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.DEVICE_NOT_FOUND)
    return {"enrolled": True}


@router.delete("/device/{device_id}", status_code=status.HTTP_200_OK)
async def deregister_device(device_id: UUID, request: Request, db: DbConn,
                             current: Employee):
    """Revoke a device — biometric login from it will stop working immediately."""
    await db.execute(
        "UPDATE device_credential SET revoked=TRUE WHERE device_credential_id=$1 AND employee_user_id=$2",
        device_id, current.user_id,
    )
    return {"revoked": True}


# ── Refresh & logout ──────────────────────────────────────────────────────────

@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh(request: Request, response: Response, db: DbConn):
    """Silent token refresh — reads refresh token from httpOnly cookie only."""
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

    _set_refresh_cookie(response, tokens["refresh_token"], max_age=7 * 86400)
    return {"access_token": tokens["access_token"], "expires_at": tokens["expires_at"]}


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(request: Request, response: Response, db: DbConn,
                 current: Employee):
    session_svc = SessionService(db, request.app.state.jwt_service)
    await session_svc.revoke(current.session_id, reason="LOGOUT")
    response.delete_cookie("prana_refresh", path="/auth/employee/refresh")
    return {"message": "Logged out"}
