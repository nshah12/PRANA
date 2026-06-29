"""
TOTP setup flow — same for all user types (employee, oa_user, portal_admin):
  1. POST /totp/setup/init     — generate secret, return QR URI + backup codes (plaintext, shown once)
  2. POST /totp/setup/confirm  — verify first code → marks totp_configured_at, stores enc secret

Called immediately after force_reset password change for OA users.
Employee calls this on first vault access after OTP login.
Until confirmed, vault is inaccessible (totp_configured_at IS NULL).
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from dependencies import AuthUser, DbConn
from services.encryption_service import aes_encrypt
from services.totp_service import TOTPService
from errors import PranaError

router = APIRouter()
_totp_svc = TOTPService()


class TOTPInitOut(BaseModel):
    provisioning_uri: str
    backup_codes: list[str]   # shown ONCE — never returned again
    setup_token: str          # must be passed to /confirm


class TOTPConfirmIn(BaseModel):
    setup_token: str
    code: str                 # first TOTP code from authenticator app


@router.post("/init", response_model=TOTPInitOut)
async def init_totp(current: AuthUser, request: Request, db: DbConn):
    """Generate TOTP secret and backup codes. Secret not saved until /confirm."""
    # Block if already configured — must go through PA/OA-Admin reset to redo
    already = await _get_totp_configured_at(db, current)
    if already:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PranaError.TOTP_ALREADY_CONFIGURED)

    secret = _totp_svc.generate_secret()
    account_label = await _get_account_label(db, current)

    # Backup codes: prefix = first 4 chars of user_id (uppercase)
    prefix = current.user_id[:4].upper()
    codes = _totp_svc.generate_backup_codes(prefix)
    plaintexts = [c[0] for c in codes]
    hashes     = [c[1] for c in codes]

    # Store secret + hashes temporarily in Redis (5 min) — not in DB until confirmed
    import json
    setup_token = __import__("secrets").token_urlsafe(32)
    await request.app.state.redis.setex(
        f"totp_setup:{setup_token}",
        300,
        json.dumps({"secret": secret, "hashes": hashes, "user_type": current.user_type, "user_id": current.user_id}),
    )

    return TOTPInitOut(
        provisioning_uri=_totp_svc.provisioning_uri(secret, account_label),
        backup_codes=plaintexts,
        setup_token=setup_token,
    )


@router.post("/confirm", status_code=status.HTTP_200_OK)
async def confirm_totp(body: TOTPConfirmIn, request: Request, db: DbConn):
    """Verify first TOTP code → persist encrypted secret + backup code hashes."""
    import json

    raw = await request.app.state.redis.get(f"totp_setup:{body.setup_token}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.SETUP_TOKEN_EXPIRED)

    data = json.loads(raw.decode())
    secret = data["secret"]
    hashes = data["hashes"]
    user_type = data["user_type"]
    user_id   = data["user_id"]

    # Verify the first code against the plain secret (not yet encrypted)
    import pyotp
    totp = pyotp.TOTP(secret)
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=PranaError.INVALID_CODE)

    await request.app.state.redis.delete(f"totp_setup:{body.setup_token}")

    # Encrypt secret with DEK before storing
    dev_dek = b"\x00" * 32   # prod: unwrap DEK from KMS
    enc_secret = aes_encrypt(secret, dev_dek)
    now = datetime.now(tz=timezone.utc)

    async with db.transaction():
        await _save_totp_secret(db, user_type, user_id, enc_secret, now)
        await _save_backup_codes(db, user_type, user_id, hashes)

    return {"message": "TOTP configured", "configured_at": now.isoformat()}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_totp_configured_at(db, current: AuthUser):
    if current.user_type == "employee":
        row = await db.fetchrow("SELECT totp_configured_at FROM employee_user WHERE employee_user_id=$1", current.user_id)
    elif current.user_type == "oa_user":
        row = await db.fetchrow("SELECT totp_configured_at FROM oa_user WHERE oa_user_id=$1", current.user_id)
    else:
        row = await db.fetchrow("SELECT totp_configured_at FROM portal_admin WHERE pa_id=$1", current.user_id)
    return row["totp_configured_at"] if row else None


async def _get_account_label(db, current: AuthUser) -> str:
    if current.user_type == "employee":
        row = await db.fetchrow("SELECT mobile FROM employee_user WHERE employee_user_id=$1", current.user_id)
        return row["mobile"] or current.user_id
    elif current.user_type == "oa_user":
        row = await db.fetchrow("SELECT email FROM oa_user WHERE oa_user_id=$1", current.user_id)
        return row["email"]
    else:
        row = await db.fetchrow("SELECT email FROM portal_admin WHERE pa_id=$1", current.user_id)
        return row["email"]


async def _save_totp_secret(db, user_type, user_id, enc_secret, now):
    if user_type == "employee":
        await db.execute(
            "UPDATE employee_user SET totp_secret_enc=$2, totp_configured_at=$3 WHERE employee_user_id=$1",
            user_id, enc_secret, now,
        )
    elif user_type == "oa_user":
        await db.execute(
            "UPDATE oa_user SET totp_secret_enc=$2, totp_configured_at=$3 WHERE oa_user_id=$1",
            user_id, enc_secret, now,
        )
    else:
        await db.execute(
            "UPDATE portal_admin SET totp_secret_enc=$2, totp_configured_at=$3 WHERE pa_id=$1",
            user_id, enc_secret, now,
        )


async def _save_backup_codes(db, user_type, user_id, hashes):
    await db.executemany(
        "INSERT INTO backup_code (user_type, user_id, code_hash) VALUES ($1, $2, $3)",
        [(user_type, user_id, h) for h in hashes],
    )
