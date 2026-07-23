"""Tests for services/ivr_service.py (new).

Exotel + Ozonetel outbound-call dispatch — same config-driven vendor-chain +
circuit-breaker shape as every other channel adapter
(prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §5). `body` is the flow/campaign
ID to play, not freeform text-to-speech content — neither vendor's
outbound-call API accepts that for a triggered notification call.
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
        ozonetel_username="oz-user",
        ozonetel_campaign_id="camp-001",
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
        ok_resp = MagicMock(status_code=200)
        mock_http.post = AsyncMock(side_effect=[fail_resp, ok_resp])
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        sent, error = await svc.send(to="+919876543210", body="camp-override")

    assert sent is True
    breaker.record_failure.assert_called_once_with("ivr", "exotel", None)
    breaker.record_success.assert_called_once_with("ivr", "ozonetel")
    # second call went to ozonetel's URL
    second_call_url = mock_http.post.call_args_list[1].args[0]
    assert "ozonetel" in second_call_url


@pytest.mark.asyncio
async def test_ivr_skips_vendor_with_open_circuit():
    svc = IVRService(_settings(provider="exotel"), _config(chain=["exotel", "ozonetel"]), _breaker(open_vendors=["exotel"]))
    with patch("services.ivr_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        sent, error = await svc.send(to="+919876543210", body="flow-001")

    call_url = mock_http.post.call_args.args[0]
    assert "ozonetel" in call_url
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
