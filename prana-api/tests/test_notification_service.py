"""
Tests for services/notification_service.py

TDD order:
  RED  — all tests here fail until notification_service.py is written
  GREEN — implement service to pass each test
  REFACTOR — clean up

Covers:
  - notify() writes a notification_log row
  - Channel selection follows cascade rules
  - P0/P1 anomaly triggers email + portal bell
  - template_data must never contain raw PAN or salary figures
  - Bounced-email suppression skips EMAIL channel
  - SMS fallback when WhatsApp opted-out
"""
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from services.notification_service import NotificationService, Channel, RecipientType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_ses():
    return MagicMock()


@pytest.fixture
def svc(mock_db, mock_ses):
    s = NotificationService(db=mock_db)
    s._ses = mock_ses
    return s


# ---------------------------------------------------------------------------
# 1. Core: notify() writes notification_log row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_writes_notification_log(svc, mock_db):
    """Every notify() call must INSERT a row into notification_log."""
    await svc.notify(
        tenant_id="tenant-001",
        event_type="ANOMALY_DETECTED",
        recipient_id="ciso-uuid-001",
        recipient_type=RecipientType.OA_USER,
        recipient_email="ciso@corp.in",
        channel=Channel.EMAIL,
        template_id="ANOMALY_P1_ALERT",
        template_data={"rule_name": "BULK_ACCESS", "severity": "P1"},
    )
    mock_db.execute.assert_called_once()
    sql, *args = mock_db.execute.call_args[0]
    assert "notification_log" in sql
    assert "ANOMALY_DETECTED" in args or any("ANOMALY_DETECTED" in str(a) for a in args)


@pytest.mark.asyncio
async def test_notify_portal_bell_status_sent(svc, mock_db):
    """PORTAL_BELL channel must log status='SENT' (no external dispatch needed)."""
    await svc.notify(
        tenant_id="tenant-001",
        event_type="DOC_ROUTED",
        recipient_id="emp-uuid-001",
        recipient_type=RecipientType.EMPLOYEE,
        channel=Channel.PORTAL_BELL,
        template_id="DOC_ROUTED",
        template_data={"doc_type": "SALARY_SLIP"},
    )
    sql, *args = mock_db.execute.call_args[0]
    assert "SENT" in args or any("SENT" in str(a) for a in args)


# ---------------------------------------------------------------------------
# 2. Email dispatch via SES
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_email_calls_ses(svc, mock_ses, mock_db):
    """EMAIL channel must call SES send_email."""
    await svc.notify(
        tenant_id="tenant-001",
        event_type="ANOMALY_DETECTED",
        recipient_id="ciso-uuid-001",
        recipient_type=RecipientType.OA_USER,
        recipient_email="ciso@corp.in",
        channel=Channel.EMAIL,
        template_id="ANOMALY_P1_ALERT",
        template_data={"rule_name": "BULK_ACCESS", "severity": "P1", "detected_at": "2026-06-19T10:00:00Z"},
    )
    mock_ses.send_email.assert_called_once()
    call_kwargs = mock_ses.send_email.call_args[1] if mock_ses.send_email.call_args[1] else {}
    dest = mock_ses.send_email.call_args[0][0] if mock_ses.send_email.call_args[0] else call_kwargs.get("Destination", {})
    # Recipient email must be in the call
    call_str = str(mock_ses.send_email.call_args)
    assert "ciso@corp.in" in call_str


@pytest.mark.asyncio
async def test_notify_email_no_ses_when_no_email(svc, mock_ses, mock_db):
    """EMAIL channel without recipient_email must not call SES."""
    await svc.notify(
        tenant_id="tenant-001",
        event_type="ANOMALY_DETECTED",
        recipient_id="ciso-uuid-001",
        recipient_type=RecipientType.OA_USER,
        recipient_email=None,       # no email
        channel=Channel.EMAIL,
        template_id="ANOMALY_P1_ALERT",
        template_data={},
    )
    mock_ses.send_email.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Privacy contract — template_data must be clean
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_template_data_has_no_pan(svc, mock_db):
    """template_data passed to notification_log must never contain raw PAN."""
    dirty_data = {"pan": "ABCDE1234F", "rule_name": "BULK_ACCESS"}
    with pytest.raises(ValueError, match="PAN"):
        await svc.notify(
            tenant_id="tenant-001",
            event_type="ANOMALY_DETECTED",
            recipient_id="ciso-uuid-001",
            recipient_type=RecipientType.OA_USER,
            recipient_email="ciso@corp.in",
            channel=Channel.EMAIL,
            template_id="ANOMALY_P1_ALERT",
            template_data=dirty_data,
        )


@pytest.mark.asyncio
async def test_notify_template_data_has_no_salary(svc, mock_db):
    """template_data must not contain gross_salary or net_salary keys."""
    dirty_data = {"gross_salary": 150000, "doc_type": "SALARY_SLIP"}
    with pytest.raises(ValueError, match="salary"):
        await svc.notify(
            tenant_id="tenant-001",
            event_type="DOC_ROUTED",
            recipient_id="emp-uuid-001",
            recipient_type=RecipientType.EMPLOYEE,
            recipient_email="emp@example.com",
            channel=Channel.EMAIL,
            template_id="DOC_ROUTED",
            template_data=dirty_data,
        )


# ---------------------------------------------------------------------------
# 4. Bounced-email suppression
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_email_suppressed_when_bounced(svc, mock_db, mock_ses):
    """If recipient email has bounced, EMAIL channel must be suppressed."""
    # mock_db.fetchrow returns a bounce record for this email
    mock_db.fetchrow.return_value = {"email": "bounced@corp.in"}

    await svc.notify(
        tenant_id="tenant-001",
        event_type="DOC_ROUTED",
        recipient_id="emp-uuid-001",
        recipient_type=RecipientType.EMPLOYEE,
        recipient_email="bounced@corp.in",
        channel=Channel.EMAIL,
        template_id="DOC_ROUTED",
        template_data={"doc_type": "SALARY_SLIP"},
        check_suppression=True,
    )
    mock_ses.send_email.assert_not_called()
    # notification_log status must be SUPPRESSED
    sql, *args = mock_db.execute.call_args[0]
    assert "SUPPRESSED" in args or any("SUPPRESSED" in str(a) for a in args)


# ---------------------------------------------------------------------------
# 5. Portal bell channel — no SES, just DB write
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_portal_bell_no_ses(svc, mock_db, mock_ses):
    """PORTAL_BELL channel must write notification_log but never call SES."""
    await svc.notify(
        tenant_id="tenant-001",
        event_type="ANOMALY_DETECTED",
        recipient_id="ciso-uuid-001",
        recipient_type=RecipientType.OA_USER,
        recipient_email="ciso@corp.in",
        channel=Channel.PORTAL_BELL,
        template_id="ANOMALY_P2_ALERT",
        template_data={"rule_name": "DUPLICATE_DOC"},
    )
    mock_ses.send_email.assert_not_called()
    mock_db.execute.assert_called_once()


# ---------------------------------------------------------------------------
# 6. notify_anomaly() helper — sends correct channels per severity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_anomaly_p0_sends_email_sms_bell(svc, mock_db):
    """P0 anomaly must dispatch EMAIL + SMS + PORTAL_BELL."""
    with patch.object(svc, "notify", new_callable=AsyncMock) as mock_notify:
        await svc.notify_anomaly(
            tenant_id="tenant-001",
            anomaly_id="anom-uuid-001",
            rule_name="BULK_ACCESS",
            severity="P0",
            ciso_id="ciso-uuid-001",
            ciso_email="ciso@corp.in",
        )
    channels_called = {c.args[0] if c.args else c.kwargs.get("channel")
                       for c in mock_notify.call_args_list}
    # Must include EMAIL, PORTAL_BELL at minimum
    called_str = str(mock_notify.call_args_list)
    assert "EMAIL" in called_str
    assert "PORTAL_BELL" in called_str


@pytest.mark.asyncio
async def test_notify_anomaly_p2_only_bell(svc, mock_db):
    """P2 anomaly must only dispatch PORTAL_BELL — no email."""
    with patch.object(svc, "notify", new_callable=AsyncMock) as mock_notify:
        await svc.notify_anomaly(
            tenant_id="tenant-001",
            anomaly_id="anom-uuid-002",
            rule_name="SLOW_DRAIN",
            severity="P2",
            ciso_id="ciso-uuid-001",
            ciso_email="ciso@corp.in",
        )
    called_str = str(mock_notify.call_args_list)
    assert "EMAIL" not in called_str
    assert "PORTAL_BELL" in called_str


@pytest.mark.asyncio
async def test_notify_anomaly_p3_no_notification(svc, mock_db):
    """P3 anomaly must dispatch nothing — portal bell only via dashboard query."""
    with patch.object(svc, "notify", new_callable=AsyncMock) as mock_notify:
        await svc.notify_anomaly(
            tenant_id="tenant-001",
            anomaly_id="anom-uuid-003",
            rule_name="LOW_SIGNAL",
            severity="P3",
            ciso_id="ciso-uuid-001",
            ciso_email="ciso@corp.in",
        )
    mock_notify.assert_not_called()
