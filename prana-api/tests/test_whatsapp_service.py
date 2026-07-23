"""Tests for services/whatsapp_service.py (new).

WABA (Meta Cloud API) — single-vendor chain for v1
(prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §10), but still goes through
the same config-driven vendor-chain + circuit-breaker shape as every other
channel adapter. Meta restricts messages to pre-approved templates — `body`
is the template name, never freeform text (.claude/rules/integrations.md).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.whatsapp_service import WhatsAppService
from config import Settings


def _settings(provider: str = "dev") -> Settings:
    return Settings(
        app_env="test",
        debug=True,
        db_host="localhost",
        db_port=5433,
        platform_hmac_secret="test_secret_32chars_padding_pad1",
        kafka_bootstrap_servers="localhost:9092",
        redis_url="redis://localhost:6379/15",
        whatsapp_provider=provider,
        whatsapp_waba_token="test-token",
        whatsapp_waba_phone_number_id="1234567890",
        whatsapp_waba_api_version="v20.0",
    )


def _config(chain=None):
    cfg = AsyncMock()
    cfg.get_list = AsyncMock(return_value=chain if chain is not None else ["waba"])
    return cfg


def _breaker(open_vendors=None):
    b = AsyncMock()
    open_set = set(open_vendors or [])
    b.is_open = AsyncMock(side_effect=lambda channel, vendor: vendor in open_set)
    b.record_failure = AsyncMock()
    b.record_success = AsyncMock()
    return b


@pytest.mark.asyncio
async def test_whatsapp_dev_mode_does_not_call_config_or_vendors():
    svc = WhatsAppService(_settings(provider="dev"), _config(), _breaker())
    with patch("services.whatsapp_service.httpx.AsyncClient") as mock_httpx_cls:
        sent, error = await svc.send(to="+919876543210", body="VAULT_WELCOME")
    mock_httpx_cls.assert_not_called()
    assert sent is True
    assert error is None


@pytest.mark.asyncio
async def test_whatsapp_dispatches_via_waba_meta_cloud_api():
    config = _config(chain=["waba"])
    svc = WhatsAppService(_settings(provider="waba"), config, _breaker())

    with patch("services.whatsapp_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        sent, error = await svc.send(to="+919876543210", body="VAULT_WELCOME")

    config.get_list.assert_called_once_with("whatsapp_vendor_chain", None)
    call_args = mock_http.post.call_args
    assert "1234567890" in call_args.args[0]
    assert call_args.kwargs["headers"]["Authorization"] == "Bearer test-token"
    payload = call_args.kwargs["json"]
    assert payload["messaging_product"] == "whatsapp"
    assert payload["type"] == "template"
    assert payload["template"]["name"] == "VAULT_WELCOME"
    assert sent is True
    assert error is None


@pytest.mark.asyncio
async def test_whatsapp_includes_template_params_when_given():
    svc = WhatsAppService(_settings(provider="waba"), _config(chain=["waba"]), _breaker())
    with patch("services.whatsapp_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        await svc.send(to="+919876543210", body="DOC_ROUTED", template_params=["Priya", "Salary Slip"])

    payload = mock_http.post.call_args.kwargs["json"]
    components = payload["template"]["components"]
    assert components[0]["type"] == "body"
    assert components[0]["parameters"] == [
        {"type": "text", "text": "Priya"}, {"type": "text", "text": "Salary Slip"},
    ]


@pytest.mark.asyncio
async def test_whatsapp_failure_recorded_and_falls_through_chain():
    breaker = _breaker()
    svc = WhatsAppService(_settings(provider="waba"), _config(chain=["waba"]), breaker)
    with patch("services.whatsapp_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        mock_resp = MagicMock(status_code=500)
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        sent, error = await svc.send(to="+919876543210", body="VAULT_WELCOME")

    assert sent is False
    breaker.record_failure.assert_called_once_with("whatsapp", "waba", None)


@pytest.mark.asyncio
async def test_whatsapp_skips_vendor_with_open_circuit():
    svc = WhatsAppService(_settings(provider="waba"), _config(chain=["waba"]), _breaker(open_vendors=["waba"]))
    with patch("services.whatsapp_service.httpx.AsyncClient") as mock_httpx_cls:
        sent, error = await svc.send(to="+919876543210", body="VAULT_WELCOME")

    mock_httpx_cls.assert_not_called()
    assert sent is False


@pytest.mark.asyncio
async def test_whatsapp_returns_false_when_chain_not_configured():
    svc = WhatsAppService(_settings(provider="waba"), _config(chain=[]), _breaker())
    sent, error = await svc.send(to="+919876543210", body="VAULT_WELCOME")
    assert sent is False
    assert "chain" in error
