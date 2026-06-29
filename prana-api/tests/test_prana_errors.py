"""
RED tests for prana-api/errors.py — PranaError taxonomy + prana_error() helper.

Coverage:
  - All 9 domain groups are present
  - Every code used in existing routers is in the enum
  - prana_error() returns correct HTTP shape
  - No duplicate values in the enum
  - StrEnum values equal their names (code-as-string pattern)
"""
import json
import pytest
from enum import EnumMeta


# ── Taxonomy existence ────────────────────────────────────────────────────────

def test_prana_error_exists():
    from errors import PranaError
    assert PranaError is not None


def test_prana_error_is_str_enum():
    from errors import PranaError
    from enum import StrEnum
    assert issubclass(PranaError, str)
    assert isinstance(PranaError, EnumMeta)


def test_prana_error_values_equal_names():
    """Every code's .value must equal its .name (code-as-string pattern like PipelineError)."""
    from errors import PranaError
    for member in PranaError:
        assert member.value == member.name, (
            f"PranaError.{member.name} has value '{member.value}' — must equal name"
        )


def test_no_duplicate_values():
    from errors import PranaError
    values = [m.value for m in PranaError]
    assert len(values) == len(set(values)), "PranaError has duplicate values"


# ── AUTH domain ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", [
    "INVALID_CREDENTIALS",
    "ACCOUNT_LOCKED",
    "ACCOUNT_INACTIVE",
    "ACCOUNT_NOT_ACTIVE",
    "INVALID_TOTP",
    "INVALID_TOTP_CODE",
    "TOTP_NOT_CONFIGURED",
    "TOTP_ALREADY_CONFIGURED",
    "TOTP_INIT_REQUIRED",
    "STEP_TOKEN_EXPIRED",
    "INVALID_STEP",
    "MISSING_STEP_TOKEN",
    "SETUP_TOKEN_EXPIRED",
    "INVALID_CODE",
    "NO_REFRESH_TOKEN",
    "REFRESH_INVALID",
    "USER_NOT_FOUND",
    "PASSWORD_TOO_SHORT",
    "DEVICE_NOT_ENROLLED",
    "DEVICE_NOT_FOUND",
    "INVALID_PLATFORM",
    "SESSION_NOT_FOUND",
    "ALREADY_REVOKED",
])
def test_auth_codes_present(code):
    from errors import PranaError
    assert hasattr(PranaError, code), f"PranaError.{code} missing — used in auth routers"


# ── ACCESS domain ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", [
    "MISSING_AUTH",
    "OA_ADMIN_REQUIRED",
    "OA_ADMIN_ROLE_REQUIRED",
    "PORTAL_ADMIN_REQUIRED",
    "INTERNAL_TOKEN_REQUIRED",
    "INTERNAL_ONLY",
    "ELEVATION_REQUIRED",
    "INSUFFICIENT_ROLE",
])
def test_access_codes_present(code):
    from errors import PranaError
    assert hasattr(PranaError, code), f"PranaError.{code} missing — used in access control"


# ── TENANT domain ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", [
    "TENANT_NOT_FOUND",
    "ALREADY_ACTIVATED",
    "OVERRIDE_REASON_REQUIRED",
    "MISSING_OA_ADMIN_EMAIL",
    "TENANT_KEK_NOT_FOUND",
    "AT_LEAST_ONE_CHANNEL_REQUIRED",
    "CONFIG_CREATE_FAILED",
])
def test_tenant_codes_present(code):
    from errors import PranaError
    assert hasattr(PranaError, code), f"PranaError.{code} missing — used in tenant routers"


# ── DOCUMENT / INGEST domain ──────────────────────────────────────────────────

@pytest.mark.parametrize("code", [
    "DOCUMENT_NOT_FOUND",
    "UNSUPPORTED_FILE_TYPE",
    "EMPTY_FILE",
    "ARCHIVE_MUST_BE_ZIP",
    "INVALID_ZIP",
    "REPORT_NOT_FOUND",
    "ANOMALY_NOT_FOUND",
    "ACCESS_LOG_NOT_FOUND",
])
def test_document_codes_present(code):
    from errors import PranaError
    assert hasattr(PranaError, code), f"PranaError.{code} missing — used in ingest/vault"


# ── SHARE domain ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", [
    "SHARE_NOT_FOUND",
    "SHARE_NOT_ACTIVE",
    "OTP_NOT_REQUIRED",
    "INVALID_OTP",
    "OTP_REQUIRED",
    "DOCUMENT_NOT_IN_SHARE",
])
def test_share_codes_present(code):
    from errors import PranaError
    assert hasattr(PranaError, code), f"PranaError.{code} missing — used in share routers"


# ── EXCEPTION / PIPELINE domain ───────────────────────────────────────────────

@pytest.mark.parametrize("code", [
    "EXCEPTION_NOT_FOUND",
    "ALREADY_RESOLVED",
    "EXCEPTION_NOT_OPEN",
    "EMPLOYEE_NOT_FOUND",
])
def test_exception_codes_present(code):
    from errors import PranaError
    assert hasattr(PranaError, code), f"PranaError.{code} missing — used in exception routers"


# ── ELEVATION domain ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", [
    "INVALID_DURATION",
    "REASON_REQUIRED",
    "ELEVATION_ALREADY_ACTIVE",
    "ELEVATION_NOT_FOUND",
    "ELEVATION_NOT_PENDING",
    "ELEVATION_NOT_ACTIVE",
    "NOT_YOUR_ELEVATION",
    "WORKFLOW_UNAVAILABLE",
])
def test_elevation_codes_present(code):
    from errors import PranaError
    assert hasattr(PranaError, code), f"PranaError.{code} missing — used in elevation router"


# ── DPDP domain ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", [
    "INVALID_PURPOSE",
    "ERASURE_ALREADY_PENDING",
    "NO_PENDING_ERASURE",
    "NOT_FOUND",
])
def test_dpdp_codes_present(code):
    from errors import PranaError
    assert hasattr(PranaError, code), f"PranaError.{code} missing — used in dpdp/compliance"


# ── HRMS / LABOUR LAW domain ──────────────────────────────────────────────────

@pytest.mark.parametrize("code", [
    "CONNECTOR_CONFIG_NOT_FOUND",
    "CONNECTOR_NOT_FOUND",
    "LOCK_NOT_FOUND",
    "ALREADY_UNLOCKED",
    "INVALID_ACT",
    "INVALID_STATUS",
    "NO_FIELDS_TO_UPDATE",
])
def test_ops_codes_present(code):
    from errors import PranaError
    assert hasattr(PranaError, code), f"PranaError.{code} missing — used in ops routers"


# ── prana_error() helper ──────────────────────────────────────────────────────

def test_prana_error_helper_exists():
    from errors import prana_error
    assert callable(prana_error)


def test_prana_error_helper_returns_http_exception():
    from fastapi import HTTPException
    from errors import PranaError, prana_error

    exc = prana_error(PranaError.INVALID_TOTP, status_code=401)
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 401


def test_prana_error_helper_detail_is_code_string():
    """detail must be the error code string so frontend can i18n."""
    from errors import PranaError, prana_error

    exc = prana_error(PranaError.TENANT_NOT_FOUND, status_code=404)
    assert exc.detail == "TENANT_NOT_FOUND"


def test_prana_error_helper_accepts_message():
    """Optional human-readable message carried in headers or detail dict."""
    from errors import PranaError, prana_error

    exc = prana_error(
        PranaError.INVALID_TOTP,
        status_code=401,
        message="TOTP code expired",
    )
    # detail stays as the code string (for i18n); message in headers
    assert exc.detail == "INVALID_TOTP"
    assert exc.headers is not None
    assert exc.headers.get("X-Error-Message") == "TOTP code expired"


def test_prana_error_code_is_usable_as_string():
    """PranaError codes must be usable directly as HTTPException detail strings."""
    from fastapi import HTTPException
    from errors import PranaError

    exc = HTTPException(status_code=403, detail=PranaError.ELEVATION_REQUIRED)
    # Should serialize correctly to JSON (StrEnum behaves as str)
    assert str(exc.detail) == "ELEVATION_REQUIRED"
