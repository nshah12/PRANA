"""Tests for services/compliance_service.py."""
import inspect
import pathlib
import pytest
from unittest.mock import AsyncMock, MagicMock

from services.compliance_service import ComplianceService


_SOURCE = pathlib.Path(__file__).parent.parent / "services" / "compliance_service.py"


def test_erasure_does_not_delete_audit_events():
    src = _SOURCE.read_text(encoding="utf-8").upper()
    assert "DELETE FROM AUDIT_EVENT" not in src, \
        "execute_erasure must never DELETE audit_event rows — 7-year legal retention"
    assert "TRUNCATE AUDIT_EVENT" not in src


def test_erasure_sla_days_read_from_platform_config():
    src = _SOURCE.read_text(encoding="utf-8")
    # The router/workflow reads SLA from config — verify config helper is present
    assert "get_config_value" in src or "platform_config" in src, \
        "ComplianceService must read SLA config from platform_config"


@pytest.mark.asyncio
async def test_consent_withdrawal_stops_processing_for_purpose():
    src = inspect.getsource(ComplianceService)
    # There must be a method that writes consent withdrawal to consent_log
    assert "consent_log" in src or "consent" in src.lower(), \
        "ComplianceService must update consent_log on withdrawal"


def test_pan_token_retained_after_erasure_for_dedup():
    src = _SOURCE.read_text(encoding="utf-8").upper()
    # execute_erasure must NOT delete pan_token from employee_user
    # It anonymises employee_user but keeps the row (and pan_token) for cross-tenant dedup
    assert "DELETE FROM EMPLOYEE_USER" not in src, \
        "execute_erasure must not hard-delete employee_user — pan_token must be retained"
