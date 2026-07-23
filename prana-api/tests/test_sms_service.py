"""Tests for services/sms_service.py.

SMSService now dispatches through a config-driven vendor chain
(sms_vendor_chain) with circuit-breaker failover per vendor — see
prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §4. Real invocation tests
against mocked ConfigService/CircuitBreaker/boto3/httpx, not source inspection.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.sms_service import SMSService
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
        sms_provider=provider,
    )


def _config(chain=None):
    cfg = AsyncMock()
    cfg.get_list = AsyncMock(return_value=chain if chain is not None else ["aws"])
    return cfg


def _breaker(open_vendors=None):
    b = AsyncMock()
    open_set = set(open_vendors or [])
    b.is_open = AsyncMock(side_effect=lambda channel, vendor: vendor in open_set)
    b.record_failure = AsyncMock()
    b.record_success = AsyncMock()
    return b


@pytest.mark.asyncio
async def test_sms_dev_mode_does_not_call_config_or_vendors():
    svc = SMSService(_settings(provider="dev"), _config(), _breaker())
    with patch("services.sms_service.boto3.client") as mock_boto:
        sent, error = await svc.send_otp("+919876543210", "123456")
    mock_boto.assert_not_called()
    assert sent is True
    assert error is None


@pytest.mark.asyncio
async def test_sms_dispatches_via_first_vendor_in_chain_aws():
    config = _config(chain=["aws"])
    svc = SMSService(_settings(provider="aws"), config, _breaker())
    with patch("services.sms_service.boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        sent, error = await svc.send_otp("+919876543210", "123456")

    config.get_list.assert_called_once_with("sms_vendor_chain", None)
    mock_boto.assert_called_once_with("sns", region_name="ap-south-1")
    call_kwargs = mock_client.publish.call_args.kwargs
    assert call_kwargs["PhoneNumber"] == "+919876543210"
    assert "123456" in call_kwargs["Message"]
    assert sent is True


@pytest.mark.asyncio
async def test_sms_uses_sns_endpoint_url_when_set():
    settings = _settings(provider="aws")
    settings.sns_endpoint_url = "http://localhost:4566"
    svc = SMSService(settings, _config(chain=["aws"]), _breaker())
    with patch("services.sms_service.boto3.client") as mock_boto:
        await svc.send_otp("+919876543210", "123456")

    call_kwargs = mock_boto.call_args.kwargs
    assert call_kwargs["endpoint_url"] == "http://localhost:4566"


@pytest.mark.asyncio
async def test_sms_falls_over_to_exotel_after_aws_fails():
    settings = _settings(provider="aws")
    settings.exotel_sid = "SID1"
    settings.exotel_api_key = "key"
    settings.exotel_api_token = "token"
    breaker = _breaker()
    svc = SMSService(settings, _config(chain=["aws", "exotel"]), breaker)

    with patch("services.sms_service.boto3.client") as mock_boto, \
         patch("services.sms_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_client = MagicMock()
        mock_client.publish.side_effect = Exception("SNS unavailable")
        mock_boto.return_value = mock_client

        mock_http = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        sent, error = await svc.send_otp("+919876543210", "123456")

    assert sent is True
    assert error is None
    breaker.record_failure.assert_called_once_with("sms", "aws", None)
    breaker.record_success.assert_called_once_with("sms", "exotel")


@pytest.mark.asyncio
async def test_sms_skips_vendor_with_open_circuit():
    settings = _settings(provider="aws")
    settings.msg91_auth_key = "key"
    settings.msg91_template_id = "tmpl"
    svc = SMSService(settings, _config(chain=["aws", "msg91"]), _breaker(open_vendors=["aws"]))

    with patch("services.sms_service.boto3.client") as mock_boto, \
         patch("services.sms_service.httpx.AsyncClient") as mock_httpx_cls:
        mock_http = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        sent, error = await svc.send_otp("+919876543210", "123456")

    mock_boto.assert_not_called()
    assert sent is True


@pytest.mark.asyncio
async def test_sms_returns_false_when_entire_chain_exhausted():
    svc = SMSService(_settings(provider="aws"), _config(chain=["aws"]), _breaker())
    with patch("services.sms_service.boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_client.publish.side_effect = Exception("SNS down")
        mock_boto.return_value = mock_client
        sent, error = await svc.send_otp("+919876543210", "123456")

    assert sent is False
    assert error is not None


@pytest.mark.asyncio
async def test_sms_returns_false_when_chain_not_configured():
    svc = SMSService(_settings(provider="aws"), _config(chain=[]), _breaker())
    sent, error = await svc.send_otp("+919876543210", "123456")
    assert sent is False
    assert "chain" in error


# ---------------------------------------------------------------------------
# Generic send() — for template-based notifications (VAULT_WELCOME, etc.),
# not OTP. Same vendor-chain/circuit-breaker machinery as send_otp, just an
# arbitrary message body instead of a hardcoded OTP phrase.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sms_generic_send_dev_mode():
    svc = SMSService(_settings(provider="dev"), _config(), _breaker())
    with patch("services.sms_service.boto3.client") as mock_boto:
        sent, error = await svc.send(to="+919876543210", body="Your PRANA vault is ready")
    mock_boto.assert_not_called()
    assert sent is True


@pytest.mark.asyncio
async def test_sms_generic_send_dispatches_body_text_via_chain():
    config = _config(chain=["aws"])
    svc = SMSService(_settings(provider="aws"), config, _breaker())
    with patch("services.sms_service.boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        sent, error = await svc.send(to="+919876543210", body="Your PRANA vault is ready")

    config.get_list.assert_called_once_with("sms_vendor_chain", None)
    call_kwargs = mock_client.publish.call_args.kwargs
    assert call_kwargs["Message"] == "Your PRANA vault is ready"
    assert sent is True


@pytest.mark.asyncio
async def test_sms_generic_send_passes_tenant_id_through():
    config = _config(chain=["aws"])
    svc = SMSService(_settings(provider="aws"), config, _breaker())
    with patch("services.sms_service.boto3.client"):
        await svc.send(to="+919876543210", body="Hi", tenant_id="tenant-001")
    config.get_list.assert_called_once_with("sms_vendor_chain", "tenant-001")


@pytest.mark.asyncio
async def test_sms_otp_value_never_logged(caplog):
    """OTP code must never appear in log records — only in the outbound message body."""
    settings = _settings(provider="aws")
    svc = SMSService(settings, _config(chain=["aws"]), _breaker())
    with patch("services.sms_service.boto3.client") as mock_boto, caplog.at_level("INFO"):
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        await svc.send_otp("+919876543210", "SECRET1")

    assert not any("SECRET1" in rec.message for rec in caplog.records)
