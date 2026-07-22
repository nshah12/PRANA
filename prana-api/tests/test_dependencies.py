"""Tests for dependencies.py — auth dependency functions (CurrentUser, _decode_bearer,
require_employee, require_oa, require_pa)."""
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from dependencies import CurrentUser, _decode_bearer, require_employee, require_oa, require_pa


def _make_request(jwt_service):
    request = MagicMock()
    request.app.state.jwt_service = jwt_service
    return request


def _make_creds(token: str = "raw.jwt.token"):
    creds = MagicMock()
    creds.credentials = token
    return creds


@pytest.mark.asyncio
async def test_decode_bearer_missing_credentials_raises_401():
    request = _make_request(MagicMock())
    with pytest.raises(HTTPException) as exc:
        await _decode_bearer(request, None)
    assert exc.value.status_code == 401
    assert exc.value.detail == "MISSING_TOKEN"


@pytest.mark.asyncio
async def test_decode_bearer_expired_token_raises_401():
    jwt_svc = MagicMock()
    jwt_svc.decode = MagicMock(side_effect=pyjwt.ExpiredSignatureError())
    request = _make_request(jwt_svc)
    with pytest.raises(HTTPException) as exc:
        await _decode_bearer(request, _make_creds())
    assert exc.value.status_code == 401
    assert exc.value.detail == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_decode_bearer_invalid_token_raises_401():
    jwt_svc = MagicMock()
    jwt_svc.decode = MagicMock(side_effect=pyjwt.InvalidTokenError())
    request = _make_request(jwt_svc)
    with pytest.raises(HTTPException) as exc:
        await _decode_bearer(request, _make_creds())
    assert exc.value.status_code == 401
    assert exc.value.detail == "TOKEN_INVALID"


@pytest.mark.asyncio
async def test_decode_bearer_revoked_session_raises_401():
    jwt_svc = MagicMock()
    jwt_svc.decode = MagicMock(return_value={"sub": "u-1", "user_type": "employee", "jti": "session-1"})
    jwt_svc.is_revoked = AsyncMock(return_value=True)
    request = _make_request(jwt_svc)
    with pytest.raises(HTTPException) as exc:
        await _decode_bearer(request, _make_creds())
    assert exc.value.status_code == 401
    assert exc.value.detail == "SESSION_REVOKED"


@pytest.mark.asyncio
async def test_decode_bearer_valid_token_returns_current_user():
    jwt_svc = MagicMock()
    jwt_svc.decode = MagicMock(return_value={
        "sub": "u-1", "user_type": "oa_user", "tenant_id": "t-1", "role": "oa_admin", "jti": "session-1",
    })
    jwt_svc.is_revoked = AsyncMock(return_value=False)
    request = _make_request(jwt_svc)
    current = await _decode_bearer(request, _make_creds())
    assert isinstance(current, CurrentUser)
    assert current.user_id == "u-1"
    assert current.user_type == "oa_user"
    assert current.tenant_id == "t-1"
    assert current.role == "oa_admin"
    assert current.session_id == "session-1"


def _current(user_type: str, role: str | None = None) -> CurrentUser:
    return CurrentUser({"sub": "u-1", "user_type": user_type, "role": role, "jti": "s-1"})


def test_require_employee_wrong_user_type_raises_403():
    with pytest.raises(HTTPException) as exc:
        require_employee(_current("oa_user"))
    assert exc.value.status_code == 403
    assert exc.value.detail == "EMPLOYEE_ONLY"


def test_require_employee_correct_type_returns_current():
    current = _current("employee")
    assert require_employee(current) is current


def test_require_oa_wrong_user_type_raises_403():
    with pytest.raises(HTTPException) as exc:
        require_oa("oa_admin")(_current("employee"))
    assert exc.value.status_code == 403
    assert exc.value.detail == "OA_ONLY"


def test_require_oa_insufficient_role_raises_403():
    with pytest.raises(HTTPException) as exc:
        require_oa("oa_admin", "ciso")(_current("oa_user", role="oa_operator"))
    assert exc.value.status_code == 403
    assert exc.value.detail == "INSUFFICIENT_ROLE"


def test_require_oa_correct_role_returns_current():
    current = _current("oa_user", role="ciso")
    assert require_oa("oa_admin", "ciso")(current) is current


def test_require_oa_no_roles_specified_allows_any_oa_role():
    current = _current("oa_user", role="oa_operator")
    assert require_oa()(current) is current


def test_require_pa_wrong_user_type_raises_403():
    with pytest.raises(HTTPException) as exc:
        require_pa(_current("oa_user"))
    assert exc.value.status_code == 403
    assert exc.value.detail == "PA_ONLY"


def test_require_pa_correct_type_returns_current():
    current = _current("portal_admin")
    assert require_pa(current) is current
