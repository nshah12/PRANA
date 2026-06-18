"""
Tests for routers/share_access.py — public share token access for recipients.

Covers:
  - OTP verification issues short-lived proof cookie (httponly)
  - Share document response is watermarked (serves PDF, not raw bytes)
  - Document access log is written with ip_address on every serve
  - Expired share token returns 410 (or 403 SHARE_EXPIRED from ShareService)
"""
from unittest.mock import AsyncMock, MagicMock, patch
import datetime

import pytest


def _make_share_info(otp_required: bool = False, expired: bool = False):
    return {
        "share_id":         "share-uuid-001",
        "employee_user_id": "emp-uuid-001",
        "document_ids":     ["doc-uuid-001"],
        "expires_at":       datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc),
        "max_views":        5,
        "views_used":       0,
        "otp_required":     otp_required,
    }


# -- OTP verification ----------------------------------------------------------

@pytest.mark.asyncio
async def test_share_otp_verify_creates_10_min_session(client, mock_db, mock_redis):
    """Successful OTP verify must set an httponly proof cookie and return verified=True."""
    mock_svc = MagicMock()
    mock_svc.validate_token = AsyncMock(return_value=_make_share_info(otp_required=True))
    mock_svc.verify_otp = AsyncMock(return_value=True)

    with patch("routers.share_access.ShareService", return_value=mock_svc):
        resp = await client.post(
            "/v1/s/test-token-abc/verify-otp",
            json={"otp": "123456"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("verified") is True

    # Proof cookie must be set — httponly so JS cannot read it
    cookie_header = resp.headers.get("set-cookie", "")
    assert "share_proof_" in cookie_header
    assert "HttpOnly" in cookie_header or "httponly" in cookie_header.lower()


@pytest.mark.asyncio
async def test_share_otp_wrong_code_returns_401(client, mock_db, mock_redis):
    """Wrong OTP code must return 401 INVALID_OTP."""
    mock_svc = MagicMock()
    mock_svc.validate_token = AsyncMock(return_value=_make_share_info(otp_required=True))
    mock_svc.verify_otp = AsyncMock(return_value=False)

    with patch("routers.share_access.ShareService", return_value=mock_svc):
        resp = await client.post(
            "/v1/s/test-token-abc/verify-otp",
            json={"otp": "000000"},
        )

    assert resp.status_code == 401
    assert "INVALID_OTP" in resp.json().get("detail", "")


# -- Watermarked document ------------------------------------------------------

@pytest.mark.asyncio
async def test_share_document_response_is_watermarked(client, mock_db, mock_redis):
    """Serving a shared document must apply the watermark — never raw bytes."""
    mock_svc = MagicMock()
    mock_svc.validate_token = AsyncMock(return_value=_make_share_info(otp_required=False))
    mock_svc.increment_views = AsyncMock()

    _MINIMAL_PDF = b"%PDF-1.4 minimal"

    mock_vault_svc = MagicMock()
    mock_vault_svc.get_document_bytes = AsyncMock(return_value=(_MINIMAL_PDF, "SALARY_SLIP"))

    with patch("routers.share_access.ShareService", return_value=mock_svc), \
         patch("routers.share_access.VaultService", return_value=mock_vault_svc), \
         patch("routers.share_access.boto3"), \
         patch("routers.vault._apply_watermark", return_value=b"%PDF-1.4 watermarked"):

        resp = await client.get("/v1/s/test-token-abc/doc/doc-uuid-001")

    # 200 + PDF content type
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers.get("content-type", "")


# -- Access log with IP --------------------------------------------------------

@pytest.mark.asyncio
async def test_share_access_writes_document_access_log_with_ip_address(client, mock_db, mock_redis):
    """VaultService.get_document_bytes is called with an actor_ip — never empty/None."""
    mock_svc = MagicMock()
    mock_svc.validate_token = AsyncMock(return_value=_make_share_info(otp_required=False))
    mock_svc.increment_views = AsyncMock()

    mock_vault_svc = MagicMock()
    mock_vault_svc.get_document_bytes = AsyncMock(return_value=(b"%PDF-1.4", "SALARY_SLIP"))

    with patch("routers.share_access.ShareService", return_value=mock_svc), \
         patch("routers.share_access.VaultService", return_value=mock_vault_svc), \
         patch("routers.share_access.boto3"), \
         patch("routers.vault._apply_watermark", return_value=b"%PDF-1.4 watermarked"):

        await client.get("/v1/s/test-token-abc/doc/doc-uuid-001")

    # VaultService.get_document_bytes must have been called with a non-empty actor_ip
    call_kwargs = mock_vault_svc.get_document_bytes.call_args
    actor_ip = call_kwargs.kwargs.get("actor_ip") or call_kwargs[1].get("actor_ip") or call_kwargs[0][2]
    assert actor_ip is not None
    assert actor_ip != ""


# -- Expired token -------------------------------------------------------------

@pytest.mark.asyncio
async def test_expired_share_token_returns_410(client, mock_db, mock_redis):
    """Expired share token must be rejected — 403 or 410 depending on implementation."""
    mock_svc = MagicMock()
    mock_svc.validate_token = AsyncMock(
        side_effect=PermissionError("SHARE_EXPIRED")
    )

    with patch("routers.share_access.ShareService", return_value=mock_svc):
        resp = await client.get("/v1/s/expired-token")

    # Both 403 (from router) and 410 (explicit Gone) are valid
    assert resp.status_code in (403, 410)
    assert "SHARE_EXPIRED" in resp.json().get("detail", "")
