"""Tests for services/email_service.py.

EmailService now dispatches through a config-driven vendor chain
(email_vendor_chain) with circuit-breaker failover per vendor — see
prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §4. Real invocation tests
against mocked ConfigService/CircuitBreaker/boto3/smtplib, not source
inspection.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.email_service import EmailService
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
        email_provider=provider,
    )


def _config(chain=None):
    cfg = AsyncMock()
    cfg.get_list = AsyncMock(return_value=chain if chain is not None else ["ses"])
    return cfg


def _breaker(open_vendors=None):
    b = AsyncMock()
    open_set = set(open_vendors or [])
    b.is_open = AsyncMock(side_effect=lambda channel, vendor: vendor in open_set)
    b.record_failure = AsyncMock()
    b.record_success = AsyncMock()
    return b


@pytest.mark.asyncio
async def test_email_dev_mode_does_not_call_ses_or_config():
    svc = EmailService(_settings(provider="dev"), _config(), _breaker())
    with patch("services.email_service.boto3.client") as mock_boto:
        sent, error = await svc.send_email(to="a@b.com", subject="Hi", body="Body")
    mock_boto.assert_not_called()
    assert sent is True
    assert error is None


@pytest.mark.asyncio
async def test_email_dispatches_via_first_vendor_in_chain():
    config = _config(chain=["ses"])
    svc = EmailService(_settings(provider="ses"), config, _breaker())
    with patch("services.email_service.boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        sent, error = await svc.send_email(
            to="employee@example.com", subject="Your PRANA vault is ready", body="Body text"
        )

    config.get_list.assert_called_once_with("email_vendor_chain", None)
    mock_boto.assert_called_once_with("ses", region_name="ap-south-1")
    call_kwargs = mock_client.send_email.call_args.kwargs
    assert call_kwargs["Destination"] == {"ToAddresses": ["employee@example.com"]}
    assert sent is True
    assert error is None


@pytest.mark.asyncio
async def test_email_uses_endpoint_url_when_set():
    settings = _settings(provider="ses")
    settings.ses_endpoint_url = "http://localhost:4566"
    svc = EmailService(settings, _config(chain=["ses"]), _breaker())
    with patch("services.email_service.boto3.client") as mock_boto:
        await svc.send_email(to="a@b.com", subject="Hi", body="Body")

    call_kwargs = mock_boto.call_args.kwargs
    assert call_kwargs["endpoint_url"] == "http://localhost:4566"


@pytest.mark.asyncio
async def test_email_falls_over_to_second_vendor_after_first_fails():
    """ses fails -> smtp (next in chain) is tried and succeeds."""
    settings = _settings(provider="ses")
    settings.smtp_host = "smtp.sendgrid.net"
    breaker = _breaker()
    svc = EmailService(settings, _config(chain=["ses", "smtp"]), breaker)

    with patch("services.email_service.boto3.client") as mock_boto, \
         patch("services.email_service.smtplib.SMTP") as mock_smtp_cls:
        mock_client = MagicMock()
        mock_client.send_email.side_effect = Exception("SES unavailable")
        mock_boto.return_value = mock_client
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        sent, error = await svc.send_email(to="a@b.com", subject="Hi", body="Body text")

    assert sent is True
    assert error is None
    breaker.record_failure.assert_called_once_with("email", "ses", None)
    breaker.record_success.assert_called_once_with("email", "smtp")
    mock_server.sendmail.assert_called_once()


@pytest.mark.asyncio
async def test_email_skips_vendor_with_open_circuit():
    """ses circuit is open -> goes straight to smtp, ses never dialed."""
    settings = _settings(provider="ses")
    settings.smtp_host = "smtp.sendgrid.net"
    svc = EmailService(settings, _config(chain=["ses", "smtp"]), _breaker(open_vendors=["ses"]))

    with patch("services.email_service.boto3.client") as mock_boto, \
         patch("services.email_service.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server
        sent, error = await svc.send_email(to="a@b.com", subject="Hi", body="Body")

    mock_boto.assert_not_called()
    mock_smtp_cls.assert_called_once()
    assert sent is True


@pytest.mark.asyncio
async def test_email_returns_false_when_entire_chain_exhausted():
    settings = _settings(provider="ses")
    breaker = _breaker()
    svc = EmailService(settings, _config(chain=["ses"]), breaker)

    with patch("services.email_service.boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_client.send_email.side_effect = Exception("SES down")
        mock_boto.return_value = mock_client
        sent, error = await svc.send_email(to="a@b.com", subject="Hi", body="Body")

    assert sent is False
    assert error is not None
    breaker.record_failure.assert_called_once_with("email", "ses", None)


@pytest.mark.asyncio
async def test_email_returns_false_when_chain_not_configured():
    svc = EmailService(_settings(provider="ses"), _config(chain=[]), _breaker())
    sent, error = await svc.send_email(to="a@b.com", subject="Hi", body="Body")
    assert sent is False
    assert "chain" in error


@pytest.mark.asyncio
async def test_email_passes_tenant_id_through_to_chain_lookup():
    config = _config(chain=["ses"])
    svc = EmailService(_settings(provider="ses"), config, _breaker())
    with patch("services.email_service.boto3.client"):
        await svc.send_email(to="a@b.com", subject="Hi", body="Body", tenant_id="tenant-001")
    config.get_list.assert_called_once_with("email_vendor_chain", "tenant-001")


@pytest.mark.asyncio
async def test_email_unknown_vendor_in_chain_recorded_as_failure_not_raised():
    breaker = _breaker()
    svc = EmailService(_settings(provider="ses"), _config(chain=["carrier_pigeon"]), breaker)
    sent, error = await svc.send_email(to="a@b.com", subject="Hi", body="Body")
    assert sent is False
    breaker.record_failure.assert_called_once_with("email", "carrier_pigeon", None)
