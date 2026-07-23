"""Tests for services/notification_log.py (new).

Shared notification_log INSERT helper — extracted from
NotificationService._log so channel consumers (EmailConsumer, SMSConsumer,
WhatsAppConsumer, IVRConsumer) can record delivery status without pulling in
NotificationService's inline channel-dispatch logic they no longer use.
"""
from unittest.mock import AsyncMock

import pytest

from services.notification_log import write_notification_log


@pytest.mark.asyncio
async def test_write_notification_log_inserts_row():
    db = AsyncMock()
    await write_notification_log(
        db,
        tenant_id="tenant-001",
        event_type="VAULT_WELCOME",
        recipient_id="emp-1",
        recipient_type="EMPLOYEE",
        channel="EMAIL",
        template_id="VAULT_WELCOME",
        template_data={"login_url": "https://prana.in"},
        status="SENT",
    )
    db.execute.assert_called_once()
    sql, *args = db.execute.call_args[0]
    assert "notification_log" in sql
    assert "SENT" in args


@pytest.mark.asyncio
async def test_write_notification_log_records_error_message_on_failure():
    db = AsyncMock()
    await write_notification_log(
        db,
        tenant_id="tenant-001",
        event_type="VAULT_WELCOME",
        recipient_id="emp-1",
        recipient_type="EMPLOYEE",
        channel="SMS",
        template_id="VAULT_WELCOME",
        template_data={},
        status="FAILED",
        error_message="all sms vendors in chain exhausted",
    )
    sql, *args = db.execute.call_args[0]
    assert "all sms vendors in chain exhausted" in args


@pytest.mark.asyncio
async def test_write_notification_log_sets_sent_at_only_when_sent():
    # Positional args after sql: tenant_id, event_type, source_id, source_table,
    # recipient_id, recipient_type, recipient_email, recipient_phone, channel,
    # template_id, template_data, status, provider_ref, sent_at, failed_at, error_message
    SENT_AT_IDX, FAILED_AT_IDX = 13, 14

    db_failed = AsyncMock()
    await write_notification_log(
        db_failed, tenant_id=None, event_type="X", recipient_id="r-1", recipient_type="EMPLOYEE",
        channel="EMAIL", template_id="X", template_data={}, status="FAILED",
    )
    _, *failed_args = db_failed.execute.call_args[0]
    assert failed_args[SENT_AT_IDX] is None
    assert failed_args[FAILED_AT_IDX] is not None

    db_sent = AsyncMock()
    await write_notification_log(
        db_sent, tenant_id=None, event_type="X", recipient_id="r-1", recipient_type="EMPLOYEE",
        channel="EMAIL", template_id="X", template_data={}, status="SENT",
    )
    _, *sent_args = db_sent.execute.call_args[0]
    assert sent_args[SENT_AT_IDX] is not None
    assert sent_args[FAILED_AT_IDX] is None
