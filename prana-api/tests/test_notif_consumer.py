"""Tests for kafka/consumers/notif_consumer.py — AUDIT_INTEGRITY_MISMATCH handler.

Scoped to the new handler only; NotifConsumer's pre-existing handlers predate
TDD enforcement and kafka/ is exempt from TDD-01 (see .claude/rules/tdd.md).
"""
from unittest.mock import AsyncMock

import pytest

from kafka.consumers.notif_consumer import NotifConsumer
from services.notification_service import Channel, RecipientType


@pytest.mark.asyncio
async def test_audit_integrity_mismatch_dispatches_to_handler():
    consumer = NotifConsumer.__new__(NotifConsumer)  # skip __init__ (no Kafka connection)
    svc = AsyncMock()
    isvc = AsyncMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    event = {"event_type": "AUDIT_INTEGRITY_MISMATCH", "checked_count": 500, "mismatched_count": 1}
    await consumer._dispatch(event, "AUDIT_INTEGRITY_MISMATCH", svc, isvc, conn)

    conn.fetch.assert_awaited_once()
    assert "portal_admin" in conn.fetch.call_args.args[0]
    assert "ACTIVE" in conn.fetch.call_args.args[0]


@pytest.mark.asyncio
async def test_audit_integrity_mismatch_notifies_every_active_pa_admin():
    consumer = NotifConsumer.__new__(NotifConsumer)
    svc = AsyncMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[
        {"pa_id": "pa-1", "email": "pa1@prana.in"},
        {"pa_id": "pa-2", "email": "pa2@prana.in"},
    ])

    event = {
        "event_type": "AUDIT_INTEGRITY_MISMATCH",
        "checked_count": 500, "mismatched_count": 2, "unverified_count": 0,
    }
    await consumer._handle_audit_integrity_mismatch(event, svc, conn)

    assert svc.notify.await_count == 2
    first_call = svc.notify.call_args_list[0].kwargs
    assert first_call["tenant_id"] is None   # platform-level, not tenant-scoped
    assert first_call["event_type"] == "AUDIT_INTEGRITY_MISMATCH"
    assert first_call["recipient_id"] == "pa-1"
    assert first_call["recipient_email"] == "pa1@prana.in"
    assert first_call["recipient_type"] == RecipientType.OA_USER
    assert first_call["channel"] == Channel.EMAIL
    assert first_call["template_id"] == "AUDIT_INTEGRITY_MISMATCH"
    assert first_call["template_data"]["mismatched_count"] == 2


@pytest.mark.asyncio
async def test_audit_integrity_mismatch_no_pa_admins_does_not_crash():
    consumer = NotifConsumer.__new__(NotifConsumer)
    svc = AsyncMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    await consumer._handle_audit_integrity_mismatch({"event_type": "AUDIT_INTEGRITY_MISMATCH"}, svc, conn)

    svc.notify.assert_not_awaited()
