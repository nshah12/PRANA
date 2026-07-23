"""Tests for services/email_service.py."""
import inspect
import pytest
from unittest.mock import MagicMock, patch

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


def test_email_provider_read_from_settings_not_hardcoded():
    src = inspect.getsource(EmailService.__init__)
    assert "email_provider" in src, "EmailService must read provider from settings.email_provider"


def test_email_dev_mode_does_not_call_ses():
    svc = EmailService(_settings(provider="dev"))
    with patch("services.email_service.boto3.client") as mock_boto:
        sent, error = svc.send_email(to="a@b.com", subject="Hi", body="Body")
    mock_boto.assert_not_called()
    assert sent is True
    assert error is None


def test_email_provider_ses_dispatches_via_boto3():
    svc = EmailService(_settings(provider="ses"))
    with patch("services.email_service.boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        sent, error = svc.send_email(to="employee@example.com", subject="Your PRANA vault is ready", body="Body text")

    mock_boto.assert_called_once_with("ses", region_name="ap-south-1")
    mock_client.send_email.assert_called_once()
    call_kwargs = mock_client.send_email.call_args.kwargs
    assert call_kwargs["Destination"] == {"ToAddresses": ["employee@example.com"]}
    assert call_kwargs["Message"]["Subject"]["Data"] == "Your PRANA vault is ready"
    assert call_kwargs["Message"]["Body"]["Text"]["Data"] == "Body text"
    assert sent is True
    assert error is None


def test_email_provider_ses_uses_endpoint_url_when_set():
    """LocalStack dev override — same pattern as SMSService's sns_endpoint_url."""
    settings = _settings(provider="ses")
    settings.ses_endpoint_url = "http://localhost:4566"
    svc = EmailService(settings)
    with patch("services.email_service.boto3.client") as mock_boto:
        svc.send_email(to="a@b.com", subject="Hi", body="Body")

    call_kwargs = mock_boto.call_args.kwargs
    assert call_kwargs["endpoint_url"] == "http://localhost:4566"


def test_email_provider_ses_failure_does_not_raise():
    svc = EmailService(_settings(provider="ses"))
    with patch("services.email_service.boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_client.send_email.side_effect = Exception("SES unavailable")
        mock_boto.return_value = mock_client
        sent, error = svc.send_email(to="a@b.com", subject="Hi", body="Body")

    assert sent is False
    assert error == "SES unavailable"


def test_email_provider_smtp_dispatches_via_smtplib():
    settings = _settings(provider="smtp")
    settings.smtp_host = "smtp.sendgrid.net"
    settings.smtp_port = 587
    settings.smtp_user = "apikey"
    settings.smtp_password = "secret"
    settings.smtp_from = "noreply@prana.in"
    svc = EmailService(settings)

    with patch("services.email_service.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server
        sent, error = svc.send_email(to="employee@example.com", subject="Hi", body="Body text")

    mock_smtp_cls.assert_called_once_with("smtp.sendgrid.net", 587, timeout=10)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("apikey", "secret")
    mock_server.sendmail.assert_called_once()
    args = mock_server.sendmail.call_args.args
    assert args[0] == "noreply@prana.in"
    assert args[1] == ["employee@example.com"]
    assert "Body text" in args[2]
    assert sent is True
    assert error is None


def test_email_provider_smtp_skips_login_when_no_user_configured():
    settings = _settings(provider="smtp")
    settings.smtp_host = "localhost"
    settings.smtp_user = ""
    svc = EmailService(settings)

    with patch("services.email_service.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server
        svc.send_email(to="a@b.com", subject="Hi", body="Body")

    mock_server.login.assert_not_called()


def test_email_provider_smtp_failure_does_not_raise():
    settings = _settings(provider="smtp")
    settings.smtp_host = "smtp.sendgrid.net"
    svc = EmailService(settings)
    with patch("services.email_service.smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.side_effect = Exception("connection refused")
        sent, error = svc.send_email(to="a@b.com", subject="Hi", body="Body")

    assert sent is False
    assert error == "connection refused"


def test_email_unknown_provider_returns_false_without_raising():
    svc = EmailService(_settings(provider="mailgun"))
    sent, error = svc.send_email(to="a@b.com", subject="Hi", body="Body")
    assert sent is False
    assert error is not None
