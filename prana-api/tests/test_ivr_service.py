"""Tests for services/ivr_service.py (new).

Exotel + Ozonetel outbound-call dispatch — same config-driven vendor-chain +
circuit-breaker shape as every other channel adapter
(prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §5).

Ozonetel's shape is verified against real docs.ozonetel.com / KooKoo
documentation (2026-07-24): GET http://in1-cpaas.ozonetel.com/outbound/outbound.php
with api_key, phone_no, outbound_version=2, extra_data (a <response> XML block —
KooKoo's playtext mechanism genuinely does accept freeform TTS text, unlike
Exotel, which only takes a flow/applet reference). Success is reported via
<status>queued</status> in the XML body, not just HTTP 200.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ivr_service import IVRService
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
        ivr_provider=provider,
        exotel_sid="SID1",
        exotel_api_key="key",
        exotel_api_token="token",
        exotel_sender_id="PRANA",
        exotel_ivr_flow_id="flow-001",
        ozonetel_api_key="oz-key",
        ozonetel_caller_id="08040000000",
    )


def _config(chain=None):
    cfg = AsyncMock()
    cfg.get_list = AsyncMock(return_value=chain if chain is not None else ["exotel", "ozonetel"])
    return cfg


def _breaker(open_vendors=None):
    b = AsyncMock()
    open_set = set(open_vendors or [])
    b.is_open = AsyncMock(side_effect=lambda channel, vendor: vendor in open_set)
    b.record_failure = AsyncMock()
    b.record_success = AsyncMock()
    return b


def _ozonetel_resp(status_code=200, body="<response><status>queued</status><message>abc-123</message></response>"):
    resp = MagicMock(status_code=status_code)
    resp.text = body
    return resp


@pytest.mark.asyncio
async def test_ivr_dev_mode_does_not_call_config_or_vendors():
    svc = IVRService(_settings(provider="dev"), _config(), _breaker())
    with patch("services.ivr_service.httpx.AsyncClient") as mock_httpx_cls:
        sent, error = await svc.send(to="+919876543210", body="flow-001")
    mock_httpx_cls.assert_not_called()
    assert sent is True
    assert error is None


@pytest.mark.asyncio
async def test_ivr_dispatches_via_exotel_first():
    config = _config(chain=["exotel", "ozonetel"])
    svc = IVRService(_settings(provider="exotel"), config, _breaker())

    with patch("services.ivr_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        sent, error = await svc.send(to="+919876543210", body="flow-001")

    config.get_list.assert_called_once_with("ivr_vendor_chain", None)
    call_args = mock_http.post.call_args
    assert "SID1" in call_args.args[0]
    assert call_args.kwargs["auth"] == ("key", "token")
    assert sent is True


@pytest.mark.asyncio
async def test_ivr_falls_over_to_ozonetel_after_exotel_fails():
    breaker = _breaker()
    svc = IVRService(_settings(provider="exotel"), _config(chain=["exotel", "ozonetel"]), breaker)

    with patch("services.ivr_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        fail_resp = MagicMock(status_code=500)
        mock_http.post = AsyncMock(return_value=fail_resp)
        mock_http.get = AsyncMock(return_value=_ozonetel_resp())
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        sent, error = await svc.send(to="+919876543210", body="Your PRANA document needs attention")

    assert sent is True
    breaker.record_failure.assert_called_once_with("ivr", "exotel", None)
    breaker.record_success.assert_called_once_with("ivr", "ozonetel")
    ozonetel_call = mock_http.get.call_args
    assert ozonetel_call.args[0] == "http://in1-cpaas.ozonetel.com/outbound/outbound.php"


@pytest.mark.asyncio
async def test_ivr_skips_vendor_with_open_circuit():
    svc = IVRService(_settings(provider="exotel"), _config(chain=["exotel", "ozonetel"]), _breaker(open_vendors=["exotel"]))
    with patch("services.ivr_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_ozonetel_resp())
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        sent, error = await svc.send(to="+919876543210", body="flow-001")

    mock_http.get.assert_called_once()
    assert sent is True


@pytest.mark.asyncio
async def test_ivr_returns_false_when_chain_not_configured():
    svc = IVRService(_settings(provider="exotel"), _config(chain=[]), _breaker())
    sent, error = await svc.send(to="+919876543210", body="flow-001")
    assert sent is False
    assert "chain" in error


@pytest.mark.asyncio
async def test_ivr_falls_back_to_configured_flow_id_when_body_empty():
    """body may be omitted by a caller that just wants the default configured flow."""
    svc = IVRService(_settings(provider="exotel"), _config(chain=["exotel"]), _breaker())
    with patch("services.ivr_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        await svc.send(to="+919876543210", body="")

    call_data = mock_http.post.call_args.kwargs["data"]
    assert "flow-001" in call_data["Url"]


# ── Ozonetel-specific: real, documented API shape ────────────────────────────

@pytest.mark.asyncio
async def test_ozonetel_dispatches_via_get_with_documented_params():
    svc = IVRService(_settings(provider="ozonetel"), _config(chain=["ozonetel"]), _breaker())
    with patch("services.ivr_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_ozonetel_resp())
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        sent, error = await svc.send(to="+919876543210", body="Your PRANA document needs attention")

    call = mock_http.get.call_args
    assert call.args[0] == "http://in1-cpaas.ozonetel.com/outbound/outbound.php"
    params = call.kwargs["params"]
    assert params["api_key"] == "oz-key"
    assert params["phone_no"] == "919876543210"
    assert params["outbound_version"] == "2"
    assert params["caller_id"] == "08040000000"
    assert "Your PRANA document needs attention" in params["extra_data"]
    assert "<playtext>" in params["extra_data"]
    assert sent is True
    assert error is None


@pytest.mark.asyncio
async def test_ozonetel_http_200_with_xml_error_status_is_treated_as_failure():
    """KooKoo can return HTTP 200 with <status>error</status> in the body —
    checking only the HTTP status code would silently treat this as success."""
    breaker = _breaker()
    svc = IVRService(_settings(provider="ozonetel"), _config(chain=["ozonetel"]), breaker)
    with patch("services.ivr_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_ozonetel_resp(
            status_code=200,
            body="<response><status>error</status><message>Invalid api_key</message></response>",
        ))
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        sent, error = await svc.send(to="+919876543210", body="Hello")

    assert sent is False
    breaker.record_failure.assert_called_once_with("ivr", "ozonetel", None)


@pytest.mark.asyncio
async def test_ozonetel_omits_caller_id_when_not_configured():
    settings = _settings(provider="ozonetel")
    settings.ozonetel_caller_id = ""
    svc = IVRService(settings, _config(chain=["ozonetel"]), _breaker())
    with patch("services.ivr_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_ozonetel_resp())
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        await svc.send(to="+919876543210", body="Hello")

    params = mock_http.get.call_args.kwargs["params"]
    assert "caller_id" not in params
