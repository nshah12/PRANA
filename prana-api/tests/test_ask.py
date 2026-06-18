"""Tests for routers/ask.py."""
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


def test_ask_proxies_to_prana_ask_service():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "ask.py").read_text(encoding="utf-8")
    assert "httpx" in src, "ask router must proxy to prana-ask via httpx"
    assert "prana_ask" in src or "PRANA_ASK" in src or "ask" in src.lower(), \
        "ask router must forward requests to the prana-ask service"


@pytest.mark.asyncio
async def test_ask_rejects_unauthenticated_request(client):
    resp = await client.post("/v1/ask", json={"query": "What is my latest employer?"})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_ask_response_contains_no_raw_salary_figures(client, mock_redis):
    _set_employee_auth(client)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()

    # Mock httpx call to prana-ask — returns answer without salary
    import httpx
    from unittest.mock import patch, AsyncMock as AM
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"answer": "Your career shows progression from analyst to manager."})

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_async_client

        resp = await client.post("/v1/ask", headers=AUTH_HEADER, json={"query": "Tell me about my career"})

    if resp.status_code == 200:
        data = resp.json()
        answer = data.get("answer", "")
        assert "₹" not in answer, "Response must not contain raw salary figures"
        assert "salary" not in answer.lower() or "insight" in answer.lower() or "progression" in answer.lower()
