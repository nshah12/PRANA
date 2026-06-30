"""
PRANA API — centralised error taxonomy.

Every HTTPException detail string used anywhere in prana-api must be a member of
PranaError. This gives:
  - Type safety: typos caught at import time, not at runtime
  - Single source of truth: one place to find every error code
  - Audit log: error_code column carries PranaError values (see migration 029)
  - Frontend i18n: codes are stable strings; UI maps them to locale text
  - HTTP shape: use prana_error() helper for consistent responses

Naming convention:
  - Values == names (code-as-string pattern, matches PipelineError in prana-ai)
  - Codes are grouped by domain but live in a flat enum (no sub-enums needed)
  - New codes: add here first, THEN use in the router/service

prana-ai pipeline errors: prana-ai/pipeline/errors.py (separate deployment)
prana-ask errors:         prana-ask/errors.py (separate deployment)
"""
from enum import StrEnum

from fastapi import HTTPException


class PranaError(StrEnum):
    # ── AUTH — login, TOTP, sessions, tokens ─────────────────────────────────
    INVALID_CREDENTIALS       = "INVALID_CREDENTIALS"
    ACCOUNT_LOCKED            = "ACCOUNT_LOCKED"
    ACCOUNT_INACTIVE          = "ACCOUNT_INACTIVE"        # OA / PA users
    ACCOUNT_NOT_ACTIVE        = "ACCOUNT_NOT_ACTIVE"      # employee variant (kept for compat)
    INVALID_TOTP              = "INVALID_TOTP"            # OA / PA
    INVALID_TOTP_CODE         = "INVALID_TOTP_CODE"       # employee variant (kept for compat)
    TOTP_NOT_CONFIGURED       = "TOTP_NOT_CONFIGURED"
    TOTP_ALREADY_CONFIGURED   = "TOTP_ALREADY_CONFIGURED"
    TOTP_INIT_REQUIRED        = "TOTP_INIT_REQUIRED"
    STEP_TOKEN_EXPIRED        = "STEP_TOKEN_EXPIRED"
    INVALID_STEP              = "INVALID_STEP"
    MISSING_STEP_TOKEN        = "MISSING_STEP_TOKEN"
    SETUP_TOKEN_EXPIRED       = "SETUP_TOKEN_EXPIRED"
    INVALID_CODE              = "INVALID_CODE"
    NO_REFRESH_TOKEN          = "NO_REFRESH_TOKEN"
    REFRESH_INVALID           = "REFRESH_INVALID"
    USER_NOT_FOUND            = "USER_NOT_FOUND"
    PASSWORD_TOO_SHORT        = "PASSWORD_TOO_SHORT"
    DEVICE_NOT_ENROLLED       = "DEVICE_NOT_ENROLLED"
    DEVICE_NOT_FOUND          = "DEVICE_NOT_FOUND"
    INVALID_PLATFORM          = "INVALID_PLATFORM"
    SESSION_NOT_FOUND         = "SESSION_NOT_FOUND"
    ALREADY_REVOKED           = "ALREADY_REVOKED"

    # ── ACCESS — role / permission guards ─────────────────────────────────────
    MISSING_AUTH              = "MISSING_AUTH"
    OA_ADMIN_REQUIRED         = "OA_ADMIN_REQUIRED"
    OA_ADMIN_ROLE_REQUIRED    = "OA_ADMIN_ROLE_REQUIRED"  # legacy alias
    PORTAL_ADMIN_REQUIRED     = "PORTAL_ADMIN_REQUIRED"
    INTERNAL_TOKEN_REQUIRED   = "INTERNAL_TOKEN_REQUIRED"
    INTERNAL_ONLY             = "INTERNAL_ONLY"
    ELEVATION_REQUIRED        = "ELEVATION_REQUIRED"
    INSUFFICIENT_ROLE         = "INSUFFICIENT_ROLE"        # generic fallback

    # ── TENANT — provisioning, config, onboarding ─────────────────────────────
    TENANT_NOT_FOUND              = "TENANT_NOT_FOUND"
    ALREADY_ACTIVATED             = "ALREADY_ACTIVATED"
    OVERRIDE_REASON_REQUIRED      = "OVERRIDE_REASON_REQUIRED"
    MISSING_OA_ADMIN_EMAIL        = "MISSING_OA_ADMIN_EMAIL"
    TENANT_KEK_NOT_FOUND          = "TENANT_KEK_NOT_FOUND"
    AT_LEAST_ONE_CHANNEL_REQUIRED = "AT_LEAST_ONE_CHANNEL_REQUIRED"
    CONFIG_CREATE_FAILED          = "CONFIG_CREATE_FAILED"

    # ── DOCUMENT / INGEST — upload, vault, access log ─────────────────────────
    DOCUMENT_NOT_FOUND        = "DOCUMENT_NOT_FOUND"
    UNSUPPORTED_FILE_TYPE     = "UNSUPPORTED_FILE_TYPE"
    EMPTY_FILE                = "EMPTY_FILE"
    ARCHIVE_MUST_BE_ZIP       = "ARCHIVE_MUST_BE_ZIP"
    INVALID_ZIP               = "INVALID_ZIP"
    REPORT_NOT_FOUND          = "REPORT_NOT_FOUND"
    ANOMALY_NOT_FOUND         = "ANOMALY_NOT_FOUND"
    ACCESS_LOG_NOT_FOUND      = "ACCESS_LOG_NOT_FOUND"

    # ── SHARE — share tokens, OTP, access ─────────────────────────────────────
    SHARE_NOT_FOUND           = "SHARE_NOT_FOUND"
    SHARE_NOT_ACTIVE          = "SHARE_NOT_ACTIVE"
    OTP_NOT_REQUIRED          = "OTP_NOT_REQUIRED"
    INVALID_OTP               = "INVALID_OTP"
    OTP_REQUIRED              = "OTP_REQUIRED"
    DOCUMENT_NOT_IN_SHARE     = "DOCUMENT_NOT_IN_SHARE"

    # ── EXCEPTION / PIPELINE — identity exception queue ───────────────────────
    EXCEPTION_NOT_FOUND       = "EXCEPTION_NOT_FOUND"
    ALREADY_RESOLVED          = "ALREADY_RESOLVED"
    EXCEPTION_NOT_OPEN        = "EXCEPTION_NOT_OPEN"
    EMPLOYEE_NOT_FOUND        = "EMPLOYEE_NOT_FOUND"

    # ── ELEVATION — temporary privilege escalation ────────────────────────────
    INVALID_DURATION          = "INVALID_DURATION"
    REASON_REQUIRED           = "REASON_REQUIRED"
    ELEVATION_ALREADY_ACTIVE  = "ELEVATION_ALREADY_ACTIVE"
    ELEVATION_NOT_FOUND       = "ELEVATION_NOT_FOUND"
    ELEVATION_NOT_PENDING     = "ELEVATION_NOT_PENDING"
    ELEVATION_NOT_ACTIVE      = "ELEVATION_NOT_ACTIVE"
    NOT_YOUR_ELEVATION        = "NOT_YOUR_ELEVATION"
    WORKFLOW_UNAVAILABLE      = "WORKFLOW_UNAVAILABLE"

    # ── DPDP / COMPLIANCE — data rights, consent, erasure ────────────────────
    INVALID_PURPOSE           = "INVALID_PURPOSE"
    ERASURE_ALREADY_PENDING   = "ERASURE_ALREADY_PENDING"
    NO_PENDING_ERASURE        = "NO_PENDING_ERASURE"
    NOT_FOUND                 = "NOT_FOUND"               # generic (use specific codes where possible)

    # ── CISO / SECURITY OPS — locks, audit, anomalies ─────────────────────────
    LOCK_NOT_FOUND            = "LOCK_NOT_FOUND"
    ALREADY_UNLOCKED          = "ALREADY_UNLOCKED"

    # ── AUTH — registration / OTP (public portal) ─────────────────────────────
    OTP_RATE_LIMITED             = "OTP_RATE_LIMITED"
    OTP_ALREADY_USED             = "OTP_ALREADY_USED"
    REGISTRATION_OTP_EXPIRED     = "REGISTRATION_OTP_EXPIRED"
    REGISTRATION_CODE_INVALID    = "REGISTRATION_CODE_INVALID"
    EMAIL_VERIFICATION_REQUIRED  = "EMAIL_VERIFICATION_REQUIRED"
    VERIFICATION_SESSION_EXPIRED = "VERIFICATION_SESSION_EXPIRED"
    DPA_REQUIRED                 = "DPA_REQUIRED"

    # ── TENANT SETTINGS ───────────────────────────────────────────────────────
    NO_TENANT_OVERRIDE        = "NO_TENANT_OVERRIDE"
    CHANNEL_NOT_PERMITTED     = "CHANNEL_NOT_PERMITTED"
    INVALID_DATE_RANGE        = "INVALID_DATE_RANGE"

    # ── HRMS / INTEGRATIONS ───────────────────────────────────────────────────
    CONNECTOR_CONFIG_NOT_FOUND = "CONNECTOR_CONFIG_NOT_FOUND"
    CONNECTOR_NOT_FOUND        = "CONNECTOR_NOT_FOUND"
    WEBHOOK_SIG_MISSING        = "WEBHOOK_SIG_MISSING"
    WEBHOOK_SIG_MISMATCH       = "WEBHOOK_SIG_MISMATCH"

    # ── MOBILE / DEVICE — errors returned by API for device/biometric flows ──
    DEVICE_LIMIT_REACHED       = "DEVICE_LIMIT_REACHED"
    PUSH_REQUEST_NOT_FOUND     = "PUSH_REQUEST_NOT_FOUND"
    PUSH_REQUEST_STATUS_INVALID = "PUSH_REQUEST_STATUS_INVALID"
    PUSH_APPROVAL_FAILED       = "PUSH_APPROVAL_FAILED"
    CONSENT_RECORD_FAILED      = "CONSENT_RECORD_FAILED"
    UPLOAD_FAILED              = "UPLOAD_FAILED"

    # ── INFRASTRUCTURE — service unavailability (503 responses) ──────────────
    INFRA_DB_UNAVAILABLE       = "INFRA_DB_UNAVAILABLE"
    INFRA_REDIS_UNAVAILABLE    = "INFRA_REDIS_UNAVAILABLE"
    INFRA_KAFKA_UNAVAILABLE    = "INFRA_KAFKA_UNAVAILABLE"
    INFRA_S3_UNAVAILABLE       = "INFRA_S3_UNAVAILABLE"
    INFRA_KMS_UNAVAILABLE      = "INFRA_KMS_UNAVAILABLE"
    INFRA_TEMPORAL_UNAVAILABLE = "INFRA_TEMPORAL_UNAVAILABLE"
    INFRA_SERVICE_UNAVAILABLE  = "INFRA_SERVICE_UNAVAILABLE"  # generic fallback

    # ── LABOUR LAW / STATUTORY ────────────────────────────────────────────────
    INVALID_ACT               = "INVALID_ACT"
    INVALID_STATUS            = "INVALID_STATUS"
    NO_FIELDS_TO_UPDATE       = "NO_FIELDS_TO_UPDATE"


def prana_error(
    code: PranaError,
    *,
    status_code: int,
    message: str | None = None,
) -> HTTPException:
    """
    Build an HTTPException with the PRANA standard error shape.

    detail = code string (stable, i18n-able by frontend)
    X-Error-Message header = optional human-readable message (debug / logs)

    Usage:
        raise prana_error(PranaError.INVALID_TOTP, status_code=401)
        raise prana_error(PranaError.TENANT_NOT_FOUND, status_code=404,
                          message=f"tenant {tid} does not exist")
    """
    headers = {"X-Error-Message": message} if message else None
    return HTTPException(status_code=status_code, detail=code.value, headers=headers)
