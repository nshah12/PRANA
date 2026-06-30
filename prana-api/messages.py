"""
PRANA API — full message taxonomy.

Companion to errors.py. Together they cover every code the backend emits:
  errors.py   → PranaError      — HTTP error detail codes (4xx / 5xx)
  messages.py → SuccessCode     — success outcome codes  (2xx response bodies)
              → InfoCode        — informational / progress codes (SSE, polling)
              → ValidationCode  — form/field validation codes (422 bodies + frontend)
              → StatusCode      — pipeline_status display labels

Design rules (same as errors.py):
  - Values == names (code-as-string pattern)
  - Backend emits the code string — NEVER a human-readable English sentence
  - Frontend owns the locale JSON that maps code → display string
  - Adding a language = adding one JSON file, zero Python changes
  - No duplicate codes across any enum in the taxonomy

Usage:
    from messages import SuccessCode, success_response
    return success_response(SuccessCode.DOC_UPLOADED, document_id=doc_id, status="QUEUED")
    # → {"message": "DOC_UPLOADED", "document_id": "...", "status": "QUEUED"}

Locale files:
    prana-portal/src/i18n/en.json   — Portal (React)
    prana-mobile/i18n/en.json       — Mobile (React Native / Expo)
"""
from enum import StrEnum


class SuccessCode(StrEnum):
    # ── AUTH ──────────────────────────────────────────────────────────────────
    LOGIN_SUCCESS          = "LOGIN_SUCCESS"
    LOGOUT_SUCCESS         = "LOGOUT_SUCCESS"
    TOTP_SETUP_COMPLETE    = "TOTP_SETUP_COMPLETE"
    PASSWORD_CHANGED       = "PASSWORD_CHANGED"
    DEVICE_ENROLLED        = "DEVICE_ENROLLED"

    # ── DOCUMENT / INGEST ─────────────────────────────────────────────────────
    DOC_UPLOADED           = "DOC_UPLOADED"
    DOC_BATCH_UPLOADED     = "DOC_BATCH_UPLOADED"
    DOC_SHARED             = "DOC_SHARED"
    SHARE_REVOKED          = "SHARE_REVOKED"
    SHARE_OTP_VERIFIED     = "SHARE_OTP_VERIFIED"

    # ── TENANT / OA USERS ─────────────────────────────────────────────────────
    TENANT_PROVISIONED     = "TENANT_PROVISIONED"
    TENANT_CONFIG_UPDATED  = "TENANT_CONFIG_UPDATED"
    OA_USER_CREATED        = "OA_USER_CREATED"
    OA_USER_DEACTIVATED    = "OA_USER_DEACTIVATED"

    # ── EMPLOYEE ──────────────────────────────────────────────────────────────
    EMPLOYEE_LINKED        = "EMPLOYEE_LINKED"

    # ── EXCEPTION QUEUE ───────────────────────────────────────────────────────
    EXCEPTION_RESOLVED     = "EXCEPTION_RESOLVED"
    EXCEPTION_DISMISSED    = "EXCEPTION_DISMISSED"

    # ── ELEVATION ─────────────────────────────────────────────────────────────
    ELEVATION_REQUESTED    = "ELEVATION_REQUESTED"
    ELEVATION_APPROVED     = "ELEVATION_APPROVED"
    ELEVATION_REVOKED      = "ELEVATION_REVOKED"

    # ── DPDP / COMPLIANCE ─────────────────────────────────────────────────────
    ERASURE_REQUESTED      = "ERASURE_REQUESTED"
    ERASURE_CANCELLED      = "ERASURE_CANCELLED"
    EXPORT_REQUESTED       = "EXPORT_REQUESTED"
    CORRECTION_REQUESTED   = "CORRECTION_REQUESTED"
    CONSENT_WITHDRAWN      = "CONSENT_WITHDRAWN"
    CONSENT_GRANTED        = "CONSENT_GRANTED"
    GRIEVANCE_SUBMITTED    = "GRIEVANCE_SUBMITTED"

    # ── HRMS / INTEGRATIONS ───────────────────────────────────────────────────
    CONNECTOR_SAVED        = "CONNECTOR_SAVED"
    CONNECTOR_TESTED       = "CONNECTOR_TESTED"
    SYNC_TRIGGERED         = "SYNC_TRIGGERED"

    # ── LABOUR LAW / STATUTORY ────────────────────────────────────────────────
    OBLIGATION_CREATED     = "OBLIGATION_CREATED"
    OBLIGATION_UPDATED     = "OBLIGATION_UPDATED"

    # ── CISO / SECURITY OPS ───────────────────────────────────────────────────
    LOCK_APPLIED           = "LOCK_APPLIED"
    LOCK_REMOVED           = "LOCK_REMOVED"
    ANOMALY_FLAGGED        = "ANOMALY_FLAGGED"
    ANOMALY_UPDATED        = "ANOMALY_UPDATED"
    ANOMALY_ACKNOWLEDGED   = "ANOMALY_ACKNOWLEDGED"
    DIGEST_SETTINGS_SAVED  = "DIGEST_SETTINGS_SAVED"
    TEST_DIGEST_QUEUED     = "TEST_DIGEST_QUEUED"
    ACCESS_REVOKED         = "ACCESS_REVOKED"
    ALERT_ACKNOWLEDGED     = "ALERT_ACKNOWLEDGED"

    # ── OA USERS / SESSIONS ────────────────────────────────────────────────────
    ROLE_UPDATED           = "ROLE_UPDATED"
    DEVICE_REMOVED         = "DEVICE_REMOVED"
    SESSION_REVOKED        = "SESSION_REVOKED"

    # ── EMPLOYEE ──────────────────────────────────────────────────────────────
    EMPLOYEE_UPDATED       = "EMPLOYEE_UPDATED"
    MARKED_AS_ALUMNI       = "MARKED_AS_ALUMNI"

    # ── ELEVATION ─────────────────────────────────────────────────────────────
    ELEVATION_ENDED        = "ELEVATION_ENDED"
    ELEVATION_DENIED       = "ELEVATION_DENIED"

    # ── SETTINGS / PROFILE ────────────────────────────────────────────────────
    SETTINGS_UPDATED       = "SETTINGS_UPDATED"
    PROFILE_UPDATED        = "PROFILE_UPDATED"

    # ── TENANT / PA ADMIN ─────────────────────────────────────────────────────
    TENANT_UPDATED         = "TENANT_UPDATED"
    TENANT_ACTIVATED       = "TENANT_ACTIVATED"
    TENANT_REJECTED        = "TENANT_REJECTED"
    TENANT_SUSPENDED       = "TENANT_SUSPENDED"
    EMERGENCY_ACCOUNT_CREATED  = "EMERGENCY_ACCOUNT_CREATED"
    ACCOUNT_SUSPENDED          = "ACCOUNT_SUSPENDED"
    ADMIN_PASSWORD_RESET       = "ADMIN_PASSWORD_RESET"
    STORAGE_REQUEST_APPROVED   = "STORAGE_REQUEST_APPROVED"
    STORAGE_REQUEST_REJECTED   = "STORAGE_REQUEST_REJECTED"
    STORAGE_REQUEST_HELD       = "STORAGE_REQUEST_HELD"


class InfoCode(StrEnum):
    # ── Pipeline progress (emitted via SSE / Kafka prana.pipeline.events) ─────
    PIPELINE_QUEUED        = "PIPELINE_QUEUED"
    PIPELINE_SCANNING      = "PIPELINE_SCANNING"
    PIPELINE_ENCRYPTING    = "PIPELINE_ENCRYPTING"
    PIPELINE_EXTRACTING    = "PIPELINE_EXTRACTING"
    PIPELINE_RESOLVING     = "PIPELINE_RESOLVING"
    PIPELINE_ROUTING       = "PIPELINE_ROUTING"
    PIPELINE_COMPLETE      = "PIPELINE_COMPLETE"
    PIPELINE_FAILED        = "PIPELINE_FAILED"

    # ── Session ───────────────────────────────────────────────────────────────
    SESSION_EXPIRING_SOON  = "SESSION_EXPIRING_SOON"   # warn user N minutes before expiry
    SESSION_EXTENDED       = "SESSION_EXTENDED"

    # ── Share access ──────────────────────────────────────────────────────────
    SHARE_OTP_SENT         = "SHARE_OTP_SENT"
    SHARE_SESSION_ACTIVE   = "SHARE_SESSION_ACTIVE"
    SHARE_SESSION_EXPIRING = "SHARE_SESSION_EXPIRING"

    # ── HRMS sync ─────────────────────────────────────────────────────────────
    SYNC_IN_PROGRESS       = "SYNC_IN_PROGRESS"
    SYNC_COMPLETE          = "SYNC_COMPLETE"
    SYNC_PARTIAL           = "SYNC_PARTIAL"            # some records failed, some succeeded

    # ── System ────────────────────────────────────────────────────────────────
    RATE_LIMIT_WARNING     = "RATE_LIMIT_WARNING"      # approaching rate limit


class ValidationCode(StrEnum):
    # ── Generic field ─────────────────────────────────────────────────────────
    FIELD_REQUIRED         = "FIELD_REQUIRED"
    FIELD_TOO_SHORT        = "FIELD_TOO_SHORT"
    FIELD_TOO_LONG         = "FIELD_TOO_LONG"
    FIELD_INVALID_FORMAT   = "FIELD_INVALID_FORMAT"

    # ── Phone ─────────────────────────────────────────────────────────────────
    PHONE_REQUIRED         = "PHONE_REQUIRED"
    PHONE_INVALID_FORMAT   = "PHONE_INVALID_FORMAT"    # must be E.164 +91XXXXXXXXXX

    # ── Email ─────────────────────────────────────────────────────────────────
    EMAIL_REQUIRED         = "EMAIL_REQUIRED"
    EMAIL_INVALID_FORMAT   = "EMAIL_INVALID_FORMAT"

    # ── File upload ───────────────────────────────────────────────────────────
    FILE_REQUIRED          = "FILE_REQUIRED"
    FILE_TOO_LARGE         = "FILE_TOO_LARGE"
    FILE_TYPE_NOT_ALLOWED  = "FILE_TYPE_NOT_ALLOWED"

    # ── Date / time ───────────────────────────────────────────────────────────
    DATE_INVALID           = "DATE_INVALID"
    DATE_IN_PAST           = "DATE_IN_PAST"
    DATE_IN_FUTURE         = "DATE_IN_FUTURE"

    # ── Password ──────────────────────────────────────────────────────────────
    PASSWORDS_DO_NOT_MATCH = "PASSWORDS_DO_NOT_MATCH"
    PASSWORD_TOO_WEAK      = "PASSWORD_TOO_WEAK"

    # ── OTP ───────────────────────────────────────────────────────────────────
    OTP_EXPIRED            = "OTP_EXPIRED"
    OTP_ATTEMPTS_EXCEEDED  = "OTP_ATTEMPTS_EXCEEDED"

    # ── Form-level ────────────────────────────────────────────────────────────
    FORM_INVALID           = "FORM_INVALID"            # generic — one or more fields invalid


class StatusCode(StrEnum):
    """
    Pipeline document status display codes.
    These match the pipeline_status column values in the document table.
    Frontend maps them to display strings + progress indicators via i18n.
    """
    QUEUED          = "QUEUED"
    SCANNING        = "SCANNING"
    ENCRYPTING      = "ENCRYPTING"
    EXTRACTING      = "EXTRACTING"
    RESOLVING       = "RESOLVING"
    ROUTING         = "ROUTING"
    ROUTED          = "ROUTED"           # terminal — success
    QUARANTINED     = "QUARANTINED"      # terminal — virus / NSFW / CSAM
    EXCEPTION       = "EXCEPTION"        # waiting for OA-Admin resolution
    LOW_CONFIDENCE  = "LOW_CONFIDENCE"   # extraction confidence < 0.75
    UNCLASSIFIED    = "UNCLASSIFIED"     # doc_type could not be auto-detected
    FAILED          = "FAILED"           # terminal — non-retryable error
    LEGAL_HOLD      = "LEGAL_HOLD"       # terminal — routing blocked by legal hold


def success_response(code: SuccessCode, **kwargs) -> dict:
    """
    Build a standard success response body.

    The message key carries the typed code string — never a hardcoded English
    sentence. Frontend maps it to the locale string via i18n/en.json.

    Usage:
        return success_response(SuccessCode.DOC_UPLOADED, document_id=doc_id)
        # → {"message": "DOC_UPLOADED", "document_id": "..."}
    """
    return {"message": code.value, **kwargs}
