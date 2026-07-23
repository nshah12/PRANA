"""
RED tests for prana-api/messages.py — full message taxonomy.

Covers:
  SuccessCode   — typed success outcome codes (returned in response bodies)
  InfoCode      — informational / status-update codes (SSE, polling)
  ValidationCode— form/field validation error codes (frontend form lib + backend 422)
  StatusCode    — pipeline_status display codes
  success_response() helper — standard success response shape
"""
import pytest
from enum import EnumMeta


# ── SuccessCode ───────────────────────────────────────────────────────────────

def test_success_code_exists():
    from messages import SuccessCode
    assert SuccessCode is not None


def test_success_code_is_str_enum():
    from messages import SuccessCode
    assert issubclass(SuccessCode, str)
    assert isinstance(SuccessCode, EnumMeta)


def test_success_code_values_equal_names():
    from messages import SuccessCode
    for m in SuccessCode:
        assert m.value == m.name, f"SuccessCode.{m.name} value mismatch"


def test_success_code_no_duplicates():
    from messages import SuccessCode
    values = [m.value for m in SuccessCode]
    assert len(values) == len(set(values))


@pytest.mark.parametrize("code", [
    # AUTH
    "LOGIN_SUCCESS", "LOGOUT_SUCCESS", "TOTP_SETUP_COMPLETE",
    "PASSWORD_CHANGED", "DEVICE_ENROLLED",
    # DOCUMENT / INGEST
    "DOC_UPLOADED", "DOC_BATCH_UPLOADED", "DOC_SHARED", "SHARE_REVOKED",
    # TENANT
    "TENANT_PROVISIONED", "TENANT_CONFIG_UPDATED",
    "OA_USER_CREATED", "OA_USER_DEACTIVATED",
    # EXCEPTION
    "EXCEPTION_RESOLVED", "EXCEPTION_DISMISSED",
    # ELEVATION
    "ELEVATION_REQUESTED", "ELEVATION_APPROVED", "ELEVATION_REVOKED",
    # DPDP
    "ERASURE_REQUESTED", "EXPORT_REQUESTED", "CORRECTION_REQUESTED",
    "CONSENT_WITHDRAWN", "GRIEVANCE_SUBMITTED",
    # HRMS
    "CONNECTOR_SAVED", "CONNECTOR_TESTED", "SYNC_TRIGGERED",
    # LABOUR LAW
    "OBLIGATION_CREATED", "OBLIGATION_UPDATED",
    # CISO
    "LOCK_APPLIED", "LOCK_REMOVED", "ANOMALY_FLAGGED",
    # SHARE
    "SHARE_OTP_VERIFIED",
    # EMPLOYEE
    "EMPLOYEE_LINKED",
])
def test_success_codes_present(code):
    from messages import SuccessCode
    assert hasattr(SuccessCode, code), f"SuccessCode.{code} missing"


# ── InfoCode ──────────────────────────────────────────────────────────────────

def test_info_code_exists():
    from messages import InfoCode
    assert InfoCode is not None


def test_info_code_is_str_enum():
    from messages import InfoCode
    assert issubclass(InfoCode, str)


def test_info_code_values_equal_names():
    from messages import InfoCode
    for m in InfoCode:
        assert m.value == m.name


@pytest.mark.parametrize("code", [
    # Pipeline progress (SSE events)
    "PIPELINE_QUEUED", "PIPELINE_SCANNING", "PIPELINE_ENCRYPTING",
    "PIPELINE_EXTRACTING", "PIPELINE_RESOLVING", "PIPELINE_ROUTING",
    "PIPELINE_COMPLETE", "PIPELINE_FAILED",
    # Session
    "SESSION_EXPIRING_SOON", "SESSION_EXTENDED",
    # Share
    "SHARE_OTP_SENT", "SHARE_SESSION_ACTIVE", "SHARE_SESSION_EXPIRING",
    # HRMS sync
    "SYNC_IN_PROGRESS", "SYNC_COMPLETE", "SYNC_PARTIAL",
    # System
    "RATE_LIMIT_WARNING",
])
def test_info_codes_present(code):
    from messages import InfoCode
    assert hasattr(InfoCode, code), f"InfoCode.{code} missing"


# ── ValidationCode ────────────────────────────────────────────────────────────

def test_validation_code_exists():
    from messages import ValidationCode
    assert ValidationCode is not None


def test_validation_code_is_str_enum():
    from messages import ValidationCode
    assert issubclass(ValidationCode, str)


def test_validation_code_values_equal_names():
    from messages import ValidationCode
    for m in ValidationCode:
        assert m.value == m.name


@pytest.mark.parametrize("code", [
    # Generic field
    "FIELD_REQUIRED", "FIELD_TOO_SHORT", "FIELD_TOO_LONG", "FIELD_INVALID_FORMAT",
    # Phone
    "PHONE_REQUIRED", "PHONE_INVALID_FORMAT",
    # Email
    "EMAIL_REQUIRED", "EMAIL_INVALID_FORMAT",
    # File
    "FILE_REQUIRED", "FILE_TOO_LARGE", "FILE_TYPE_NOT_ALLOWED",
    # Date
    "DATE_INVALID", "DATE_IN_PAST", "DATE_IN_FUTURE",
    # Password
    "PASSWORDS_DO_NOT_MATCH", "PASSWORD_TOO_WEAK",
    # OTP
    "OTP_EXPIRED", "OTP_ATTEMPTS_EXCEEDED",
    # Form-level
    "FORM_INVALID",
])
def test_validation_codes_present(code):
    from messages import ValidationCode
    assert hasattr(ValidationCode, code), f"ValidationCode.{code} missing"


# ── StatusCode ────────────────────────────────────────────────────────────────

def test_status_code_exists():
    from messages import StatusCode
    assert StatusCode is not None


def test_status_code_is_str_enum():
    from messages import StatusCode
    assert issubclass(StatusCode, str)


def test_status_code_values_equal_names():
    from messages import StatusCode
    for m in StatusCode:
        assert m.value == m.name


@pytest.mark.parametrize("code", [
    "QUEUED", "SCANNING", "ENCRYPTING", "EXTRACTING", "RESOLVING", "ROUTING",
    "ROUTED", "QUARANTINED", "EXCEPTION", "LOW_CONFIDENCE", "UNCLASSIFIED",
    "FAILED", "LEGAL_HOLD",
])
def test_status_codes_present(code):
    from messages import StatusCode
    assert hasattr(StatusCode, code), f"StatusCode.{code} missing"


# ── success_response() helper ─────────────────────────────────────────────────

def test_success_response_helper_exists():
    from messages import success_response
    assert callable(success_response)


def test_success_response_contains_message_key():
    from messages import SuccessCode, success_response
    resp = success_response(SuccessCode.DOC_UPLOADED)
    assert "message" in resp
    assert resp["message"] == "DOC_UPLOADED"


def test_success_response_accepts_extra_fields():
    from messages import SuccessCode, success_response
    resp = success_response(SuccessCode.DOC_UPLOADED, document_id="abc-123", status="QUEUED")
    assert resp["document_id"] == "abc-123"
    assert resp["status"] == "QUEUED"
    assert resp["message"] == "DOC_UPLOADED"


def test_success_response_message_is_string():
    from messages import SuccessCode, success_response
    resp = success_response(SuccessCode.ELEVATION_APPROVED)
    assert isinstance(resp["message"], str)


# ── NotificationTemplate ────────────────────────────────────────────────────
# template_id for outbound notifications (email/SMS/WhatsApp/push/bell), sent via
# NotificationService.notify(). Previously bare string literals scattered across
# notification_service.py/notif_consumer.py with no enum — this closes that gap.
# NOT included in test_no_code_overlap_across_enums below: a notification
# template intentionally shares its name with the SuccessCode/event_type for the
# same underlying event (e.g. ELEVATION_APPROVED is both the API success code and
# the email template id for that event) — different namespace, same event name by
# design, same as how Kafka event_type strings already aren't cross-checked either.

def test_notification_template_exists():
    from messages import NotificationTemplate
    assert NotificationTemplate is not None


def test_notification_template_is_str_enum():
    from messages import NotificationTemplate
    assert issubclass(NotificationTemplate, str)
    assert isinstance(NotificationTemplate, EnumMeta)


def test_notification_template_values_equal_names():
    from messages import NotificationTemplate
    for m in NotificationTemplate:
        assert m.value == m.name, f"NotificationTemplate.{m.name} value mismatch"


def test_notification_template_no_duplicates():
    from messages import NotificationTemplate
    values = [m.value for m in NotificationTemplate]
    assert len(values) == len(set(values))


@pytest.mark.parametrize("code", [
    "ANOMALY_P0_ALERT", "ANOMALY_P1_ALERT", "ANOMALY_P2_ALERT",
    "ACCOUNT_LOCKED", "CROSS_TENANT_UPLOAD_ALERT", "AUDIT_INTEGRITY_MISMATCH", "CSAM_ALERT",
    "DOC_ROUTED", "SHARE_ACCESSED", "VAULT_WELCOME", "VAULT_WELCOME_REJOIN",
    "ERASURE_COMPLETE", "EXPORT_READY",
    "EXCEPTION_ALERT",
    "ELEVATION_APPROVED", "ELEVATION_DENIED",
    "OA_WELCOME", "EMPLOYEE_CREDENTIALS_ISSUED",
    "INCIDENT_CREATED", "INCIDENT_SLA_BREACH",
    "DIGEST_WEEKLY",
    "STORAGE_EXPANSION_REQUESTED", "ONBOARDING_REVIEW_SLA_BREACH",
])
def test_notification_templates_present(code):
    from messages import NotificationTemplate
    assert hasattr(NotificationTemplate, code), f"NotificationTemplate.{code} missing"


def test_every_notification_template_has_a_subject_line():
    """_SUBJECT_MAP in notification_service.py must cover every enum member —
    a template with no subject silently fell back to a generic 'PRANA
    Notification' subject on every email send (this happened for real, for
    CROSS_TENANT_UPLOAD_ALERT and AUDIT_INTEGRITY_MISMATCH, before this test)."""
    from messages import NotificationTemplate
    from services.notification_service import _SUBJECT_MAP
    missing = [m.value for m in NotificationTemplate if m.value not in _SUBJECT_MAP]
    assert not missing, f"No _SUBJECT_MAP entry for: {missing}"


# ── Cross-taxonomy: no overlapping codes between enums ────────────────────────

def test_no_code_overlap_across_enums():
    from messages import SuccessCode, InfoCode, ValidationCode, StatusCode
    from errors import PranaError

    all_sets = [
        {m.value for m in SuccessCode},
        {m.value for m in InfoCode},
        {m.value for m in ValidationCode},
        {m.value for m in StatusCode},
        {m.value for m in PranaError},
    ]
    all_codes = []
    for s in all_sets:
        all_codes.extend(s)

    # Each code should be unique across the whole taxonomy
    assert len(all_codes) == len(set(all_codes)), "Duplicate codes found across taxonomy enums"
