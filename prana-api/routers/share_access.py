"""
Public C-Share access — no employee auth, just a share token.

GET  /s/{token}            — validate token; if OTP required, redirect to OTP gate
POST /s/{token}/verify-otp — verify OTP, issue a short-lived bearer cookie
GET  /s/{token}/doc/{doc_id} — serve watermarked document to recipient
"""
import io
from typing import Optional

import boto3
from fastapi import APIRouter, Cookie, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.share_service import ShareService
from services.vault_service import VaultService

router = APIRouter()


def _share_svc(request: Request) -> ShareService:
    return ShareService(
        db=request.state.db,   # injected via middleware or Depends — see note below
        redis=request.app.state.redis,
        settings=request.app.state.settings,
    )


# ── Share info ────────────────────────────────────────────────────────────────

@router.get("/{token}")
async def get_share_info(token: str, request: Request):
    """
    Returns share metadata (doc types, expiry, OTP required) without serving the document.
    Mobile/web landing page calls this first.
    """
    async with request.app.state.db_pool.acquire() as db:
        svc = ShareService(db=db, redis=request.app.state.redis, settings=request.app.state.settings)
        try:
            info = await svc.validate_token(token)
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return {
        "share_id": str(info["share_id"]),
        "document_count": len(info["document_ids"]),
        "expires_at": info["expires_at"].isoformat() if info["expires_at"] else None,
        "max_views": info["max_views"],
        "views_used": info["views_used"],
        "otp_required": info["otp_required"],
    }


# ── OTP verification ──────────────────────────────────────────────────────────

class OTPVerifyIn(BaseModel):
    otp: str


@router.post("/{token}/verify-otp", status_code=status.HTTP_200_OK)
async def verify_share_otp(token: str, body: OTPVerifyIn, request: Request):
    async with request.app.state.db_pool.acquire() as db:
        svc = ShareService(db=db, redis=request.app.state.redis, settings=request.app.state.settings)
        try:
            info = await svc.validate_token(token)
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        if not info["otp_required"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP_NOT_REQUIRED")

        ok = await svc.verify_otp(token, body.otp)
        if not ok:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_OTP")

    # Issue short-lived proof cookie so subsequent doc requests don't need OTP again
    redis = request.app.state.redis
    import secrets, json
    proof = secrets.token_hex(32)
    await redis.setex(f"share_otp_proof:{token}", 1800, proof)   # 30 min

    from fastapi.responses import JSONResponse
    response = JSONResponse({"verified": True})
    response.set_cookie(
        key=f"share_proof_{token[:8]}",
        value=proof,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=1800,
    )
    return response


# ── Serve document ────────────────────────────────────────────────────────────

@router.get("/{token}/doc/{document_id}")
async def serve_shared_document(
    token: str,
    document_id: str,
    request: Request,
):
    async with request.app.state.db_pool.acquire() as db:
        share_svc = ShareService(db=db, redis=request.app.state.redis, settings=request.app.state.settings)

        try:
            info = await share_svc.validate_token(token)
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        # Check OTP gate if required
        if info["otp_required"]:
            proof_cookie = request.cookies.get(f"share_proof_{token[:8]}")
            stored_proof = await request.app.state.redis.get(f"share_otp_proof:{token}")
            if not proof_cookie or not stored_proof or proof_cookie != stored_proof.decode():
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OTP_REQUIRED")

        # Ensure document_id is in this share
        shared_ids = [str(d) for d in info["document_ids"]]
        if str(document_id) not in shared_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="DOCUMENT_NOT_IN_SHARE")

        settings = request.app.state.settings
        s3 = boto3.client("s3", region_name=settings.s3_region)
        vault_svc = VaultService(
            db=db,
            kms=request.app.state.kms_service,
            s3_client=s3,
            documents_bucket=settings.s3_bucket_documents,
        )

        try:
            plaintext, doc_type = await vault_svc.get_document_bytes(
                document_id=document_id,
                employee_user_id=str(info["employee_user_id"]),
                actor_ip=request.client.host if request.client else "0.0.0.0",
                session_id=f"share:{token[:8]}",
                access_type="SHARE_VIEW",
            )
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

        await share_svc.increment_views(token)

    from routers.vault import _apply_watermark
    watermarked = _apply_watermark(plaintext, str(info["employee_user_id"]))

    return StreamingResponse(
        io.BytesIO(watermarked),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{document_id}.pdf"'},
    )
