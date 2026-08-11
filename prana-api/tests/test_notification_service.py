"""
Tests for services/notification_service.py.

The NotificationService class (notify()/notify_anomaly(), an inline dispatch
path with stubbed SMS/WhatsApp/push) was removed 2026-08-10 — dead code, its
one real caller was NotificationDeliveryWorkflow (also removed that day, see
workflows/CLAUDE.md). What remains here are the shared constants/enums/helpers
the real Communication Hub per-channel consumers (EmailConsumer, SMSConsumer,
WhatsAppConsumer, PushConsumer) actually import and call.

Covers:
  - Channel / RecipientType enum values
  - _check_template_data — the privacy guard (PAN/salary keys) every real
    per-channel consumer now calls before dispatch
  - _build_email_body — the plaintext body EmailConsumer renders
"""
import pytest

from services.notification_service import (
    Channel, RecipientType, _check_template_data, _build_email_body,
)


def test_channel_enum_values():
    assert Channel.EMAIL == "EMAIL"
    assert Channel.SMS == "SMS"
    assert Channel.WHATSAPP == "WHATSAPP"
    assert Channel.PUSH == "PUSH"
    assert Channel.PORTAL_BELL == "PORTAL_BELL"


def test_recipient_type_enum_values():
    assert RecipientType.OA_USER == "OA_USER"
    assert RecipientType.EMPLOYEE == "EMPLOYEE"
    assert RecipientType.PORTAL_ADMIN == "PORTAL_ADMIN"


# ── _check_template_data — privacy guard ─────────────────────────────────────

def test_check_template_data_allows_clean_data():
    _check_template_data({"rule_name": "BULK_ACCESS", "severity": "P1"})  # must not raise


def test_check_template_data_rejects_pan():
    with pytest.raises(ValueError, match="PAN"):
        _check_template_data({"pan": "ABCDE1234F", "rule_name": "BULK_ACCESS"})


def test_check_template_data_rejects_enc_pan():
    with pytest.raises(ValueError, match="PAN"):
        _check_template_data({"enc_pan": b"encrypted-bytes"})


def test_check_template_data_rejects_nik():
    with pytest.raises(ValueError, match="PAN"):
        _check_template_data({"nik": "some-nik-value"})


def test_check_template_data_rejects_salary_keys():
    for key in ("gross_salary", "net_salary", "basic_salary", "ctc", "salary"):
        with pytest.raises(ValueError, match="salary"):
            _check_template_data({key: 150000, "doc_type": "SALARY_SLIP"})


def test_check_template_data_is_case_insensitive():
    with pytest.raises(ValueError, match="PAN"):
        _check_template_data({"PAN": "ABCDE1234F"})


# ── _build_email_body ────────────────────────────────────────────────────────

def test_build_email_body_includes_template_data_values():
    body = _build_email_body("DOC_ROUTED", {"doc_type": "SALARY_SLIP", "tenant": "NPCI"})
    assert "doc_type: SALARY_SLIP" in body
    assert "tenant: NPCI" in body


def test_build_email_body_includes_platform_signature():
    body = _build_email_body("DOC_ROUTED", {})
    assert "PRANA Platform" in body
    assert "noreply@prana.in" in body


def test_notification_service_has_no_dispatch_class():
    """NotificationService (and notify()/notify_anomaly()) removed 2026-08-10 —
    dead code, superseded by the real per-channel consumers. Guards against
    silent reintroduction of the parallel dispatch path.
    """
    import services.notification_service as notification_service_module

    assert not hasattr(notification_service_module, "NotificationService")
