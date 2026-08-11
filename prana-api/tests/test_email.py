"""Tests for lib/email.py — pre-auth SMTP email path (org self-registration OTP,
contact form). Separate from services/email_service.py's SES/vendor-chain path —
used by routers/public.py where no tenant/auth context exists yet.

Previously had zero test coverage (TDD-01 violation — lib/ is not in the exempt
list). Real behavior tests against a mocked smtplib.SMTP, not source inspection.
"""
import email as email_stdlib
from email.header import decode_header
from unittest.mock import MagicMock, patch

import pytest

import lib.email as email_module
from lib.email import send_otp_email, send_contact_confirmation, send_pa_contact_alert


def _decoded_html_body(raw_message: str) -> str:
    """sendmail's raw message is base64-encoded MIME — decode to plain HTML for asserts."""
    msg = email_stdlib.message_from_string(raw_message)
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            return part.get_payload(decode=True).decode("utf-8")
    raise AssertionError("no text/html part found in message")


def _decoded_subject(raw_message: str) -> str:
    msg = email_stdlib.message_from_string(raw_message)
    parts = decode_header(msg["Subject"])
    return "".join(
        (chunk.decode(enc or "utf-8") if isinstance(chunk, bytes) else chunk)
        for chunk, enc in parts
    )


@pytest.fixture(autouse=True)
def _reset_smtp_settings(monkeypatch):
    """Every test starts from dev mode (smtp_host empty) unless it opts in."""
    monkeypatch.setattr(email_module.settings, "smtp_host", "")
    monkeypatch.setattr(email_module.settings, "smtp_port", 587)
    monkeypatch.setattr(email_module.settings, "smtp_user", "")
    monkeypatch.setattr(email_module.settings, "smtp_password", "")
    monkeypatch.setattr(email_module.settings, "smtp_from", "noreply@prana.in")
    monkeypatch.setattr(email_module.settings, "smtp_use_tls", True)


# ── Dev mode (no smtp_host configured) ───────────────────────────────────────

def test_send_otp_email_dev_mode_logs_instead_of_sending():
    with patch("lib.email.smtplib.SMTP") as mock_smtp_cls:
        send_otp_email("employee@example.com", "482913", "NPCI")
    mock_smtp_cls.assert_not_called()


def test_send_pa_contact_alert_dev_mode_is_noop():
    """No smtp_host -> early return, never even attempts to build/send the alert."""
    with patch("lib.email.smtplib.SMTP") as mock_smtp_cls:
        send_pa_contact_alert("Jane Doe", "jane@corp.com", "Corp Inc", "PARTNERSHIP")
    mock_smtp_cls.assert_not_called()


# ── Real SMTP send path ──────────────────────────────────────────────────────

def test_send_otp_email_sends_via_smtp_when_configured(monkeypatch):
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.sendgrid.net")
    with patch("lib.email.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        send_otp_email("employee@example.com", "482913", "NPCI")

    mock_smtp_cls.assert_called_once_with("smtp.sendgrid.net", 587, timeout=10)
    mock_server.sendmail.assert_called_once()
    sender, recipients, raw_message = mock_server.sendmail.call_args.args
    assert sender == "noreply@prana.in"
    assert recipients == ["employee@example.com"]
    body = _decoded_html_body(raw_message)
    assert "482913" in body
    assert "NPCI" in body


def test_send_otp_email_starts_tls_when_configured(monkeypatch):
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.sendgrid.net")
    monkeypatch.setattr(email_module.settings, "smtp_use_tls", True)
    with patch("lib.email.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        send_otp_email("employee@example.com", "482913", "NPCI")

    mock_server.starttls.assert_called_once()


def test_send_otp_email_skips_tls_when_disabled(monkeypatch):
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.sendgrid.net")
    monkeypatch.setattr(email_module.settings, "smtp_use_tls", False)
    with patch("lib.email.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        send_otp_email("employee@example.com", "482913", "NPCI")

    mock_server.starttls.assert_not_called()


def test_send_otp_email_authenticates_when_smtp_user_configured(monkeypatch):
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.sendgrid.net")
    monkeypatch.setattr(email_module.settings, "smtp_user", "apikey")
    monkeypatch.setattr(email_module.settings, "smtp_password", "secret")
    with patch("lib.email.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        send_otp_email("employee@example.com", "482913", "NPCI")

    mock_server.login.assert_called_once_with("apikey", "secret")


def test_send_otp_email_skips_auth_when_no_smtp_user(monkeypatch):
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.sendgrid.net")
    with patch("lib.email.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        send_otp_email("employee@example.com", "482913", "NPCI")

    mock_server.login.assert_not_called()


def test_send_contact_confirmation_sends_correct_subject_and_recipient(monkeypatch):
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.sendgrid.net")
    with patch("lib.email.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        send_contact_confirmation("hr@corp.com", "Priya", "SALES")

    sender, recipients, raw_message = mock_server.sendmail.call_args.args
    assert recipients == ["hr@corp.com"]
    assert _decoded_subject(raw_message) == "We've received your enquiry — PRANA"
    body = _decoded_html_body(raw_message)
    assert "Priya" in body
    assert "SALES" in body


def test_send_pa_contact_alert_sends_to_platform_inbox_when_configured(monkeypatch):
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.sendgrid.net")
    monkeypatch.setattr(email_module.settings, "smtp_from", "ops@prana.in")
    with patch("lib.email.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        send_pa_contact_alert("Jane Doe", "jane@corp.com", "Corp Inc", "PARTNERSHIP")

    sender, recipients, raw_message = mock_server.sendmail.call_args.args
    # PA alert is sent to the platform's own inbox, not the enquirer
    assert recipients == ["ops@prana.in"]
    body = _decoded_html_body(raw_message)
    assert "Jane Doe" in body
    assert "jane@corp.com" in body
    assert "Corp Inc" in body


def test_send_pa_contact_alert_swallows_smtp_errors(monkeypatch):
    """Best-effort alert — a broken PA inbox must never fail the caller's request."""
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.sendgrid.net")
    with patch("lib.email.smtplib.SMTP", side_effect=ConnectionError("smtp down")):
        send_pa_contact_alert("Jane Doe", "jane@corp.com", "Corp Inc", "PARTNERSHIP")  # must not raise
