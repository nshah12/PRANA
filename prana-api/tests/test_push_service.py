"""Tests for services/push_service.py (new) — real Expo push dispatch.

Expo is the only realistic provider for an Expo SDK 56 app (no FCM/APNs
credentials anywhere in this codebase) — single-vendor chain for v1, but
still goes through the same config-driven vendor-chain + circuit-breaker
shape as every other Communication Hub channel adapter (same reasoning as
services/whatsapp_service.py).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.push_service import PushService
from config import Settings


def _settings(provider: str = "dev") -> Settings:
    return Settings(
        app_env="test", debug=True, db_host="localhost", db_port=5433,
        platform_hmac_secret="test_secret_32chars_padding_pad1",
        kafka_bootstrap_servers="localhost:9092", redis_url="redis://localhost:6379/15",
        push_provider=provider,
    )


def _config(chain=None):
    cfg = AsyncMock()
    cfg.get_list = AsyncMock(return_value=chain if chain is not None else ["expo"])
    return cfg


def _breaker(open_vendors=None):
    b = AsyncMock()
    open_set = set(open_vendors or [])
    b.is_open = AsyncMock(side_effect=lambda channel, vendor: vendor in open_set)
    b.record_failure = AsyncMock()
    b.record_success = AsyncMock()
    return b


@pytest.mark.asyncio
async def test_push_dev_mode_does_not_call_config_or_vendors():
    svc = PushService(_settings(provider="dev"), _config(), _breaker())
    with patch("services.push_service.httpx.AsyncClient") as mock_httpx_cls:
        sent, error = await svc.send(to="ExponentPushToken[abc]", title="PRANA", body="Your document is ready")
    mock_httpx_cls.assert_not_called()
    assert sent is True
    assert error is None


@pytest.mark.asyncio
async def test_push_dispatches_via_expo_push_api():
    config = _config(chain=["expo"])
    svc = PushService(_settings(provider="expo"), config, _breaker())

    with patch("services.push_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json = MagicMock(return_value={"data": {"status": "ok", "id": "receipt-1"}})
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        sent, error = await svc.send(to="ExponentPushToken[abc]", title="PRANA", body="Your document is ready")

    config.get_list.assert_called_once_with("push_vendor_chain", None)
    call_args = mock_http.post.call_args
    assert call_args.args[0] == "https://exp.host/--/api/v2/push/send"
    payload = call_args.kwargs["json"]
    assert payload["to"] == "ExponentPushToken[abc]"
    assert payload["title"] == "PRANA"
    assert payload["body"] == "Your document is ready"
    assert sent is True
    assert error is None


@pytest.mark.asyncio
async def test_push_includes_data_payload_when_given():
    svc = PushService(_settings(provider="expo"), _config(chain=["expo"]), _breaker())
    with patch("services.push_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json = MagicMock(return_value={"data": {"status": "ok"}})
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        await svc.send(to="ExponentPushToken[abc]", title="PRANA", body="msg", data={"document_id": "doc-1"})

    payload = mock_http.post.call_args.kwargs["json"]
    assert payload["data"] == {"document_id": "doc-1"}


@pytest.mark.asyncio
async def test_push_http_failure_recorded():
    breaker = _breaker()
    svc = PushService(_settings(provider="expo"), _config(chain=["expo"]), breaker)
    with patch("services.push_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        mock_resp = MagicMock(status_code=500)
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        sent, error = await svc.send(to="ExponentPushToken[abc]", title="PRANA", body="msg")

    assert sent is False
    breaker.record_failure.assert_called_once_with("push", "expo", None)


@pytest.mark.asyncio
async def test_push_expo_device_not_registered_error_surfaces_in_error_message():
    """PushConsumer needs to detect this specific error to clear the dead
    token from device_credential — the error string must carry it through."""
    svc = PushService(_settings(provider="expo"), _config(chain=["expo"]), _breaker())
    with patch("services.push_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json = MagicMock(return_value={
            "data": {"status": "error", "message": "not registered", "details": {"error": "DeviceNotRegistered"}},
        })
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        sent, error = await svc.send(to="ExponentPushToken[dead]", title="PRANA", body="msg")

    assert sent is False
    assert error == "DeviceNotRegistered"


@pytest.mark.asyncio
async def test_push_skips_vendor_with_open_circuit():
    breaker = _breaker(open_vendors=["expo"])
    svc = PushService(_settings(provider="expo"), _config(chain=["expo"]), breaker)
    with patch("services.push_service.httpx.AsyncClient") as mock_httpx_cls:
        sent, error = await svc.send(to="ExponentPushToken[abc]", title="PRANA", body="msg")
    mock_httpx_cls.assert_not_called()
    assert sent is False


@pytest.mark.asyncio
async def test_push_no_vendor_chain_configured():
    svc = PushService(_settings(provider="expo"), _config(chain=[]), _breaker())
    sent, error = await svc.send(to="ExponentPushToken[abc]", title="PRANA", body="msg")
    assert sent is False
    assert "no push vendor chain" in error
