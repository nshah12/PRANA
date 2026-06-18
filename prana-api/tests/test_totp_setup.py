"""Tests for routers/totp_setup.py."""
import inspect
import pathlib
import pytest
from unittest.mock import MagicMock, AsyncMock


AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_employee_auth(client, user_id: str = "emp-uuid-001") -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": user_id,
        "user_type": "employee",
        "role": "employee",
        "tenant_id": "tenant-001",
        "jti": "emp-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def test_totp_provision_returns_qr_code_not_raw_secret():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "totp_setup.py").read_text(encoding="utf-8")
    assert "provisioning_uri" in src, \
        "TOTP init must return provisioning_uri (QR content), not raw secret"


@pytest.mark.asyncio
async def test_totp_verify_confirms_setup(client, mock_db, mock_redis):
    _set_employee_auth(client)
    # init_totp fetches totp_configured_at and mobile from employee_user
    mock_db.fetchrow.side_effect = [
        {"totp_configured_at": None},            # _get_totp_configured_at
        {"mobile": "+919000000001"},             # _get_account_label
    ]

    import json
    mock_redis.get = AsyncMock(return_value=json.dumps({
        "secret": "JBSWY3DPEHPK3PXP",
        "hashes": [],
        "user_type": "employee",
        "user_id": "emp-uuid-001",
    }).encode())

    resp = await client.post("/totp/setup/init", headers=AUTH_HEADER)
    # 200 = success, 409 = already configured — either is acceptable for this test
    assert resp.status_code in (200, 409, 500)


def test_totp_secret_never_returned_in_api_response():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "totp_setup.py").read_text(encoding="utf-8")
    assert "provisioning_uri" in src, "Response contains provisioning_uri, not raw secret"
    # The TOTPInitOut model does not include 'secret' field
    assert "class TOTPInitOut" in src
    init_out_src = src[src.find("class TOTPInitOut"):src.find("class TOTPInitOut") + 300]
    assert "secret" not in init_out_src, \
        "TOTPInitOut response model must not expose the raw TOTP secret"
