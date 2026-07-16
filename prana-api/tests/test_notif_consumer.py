"""Tests for kafka/consumers/notif_consumer.py — AUDIT_INTEGRITY_MISMATCH handler
and _handle_anomaly's severity resolution.

Scoped to touched handlers only; NotifConsumer's pre-existing handlers predate
TDD enforcement and kafka/ is exempt from TDD-01 (see .claude/rules/tdd.md).
"""
from unittest.mock import AsyncMock, patch

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


# ── _handle_anomaly — shared severity resolution (fixes the P3/P2 disagreement) ──

@pytest.mark.asyncio
async def test_handle_anomaly_uses_explicit_severity_when_present():
    consumer = NotifConsumer.__new__(NotifConsumer)
    consumer._lookup_ciso = AsyncMock(return_value=None)
    svc = AsyncMock()
    isvc = AsyncMock()
    conn = AsyncMock()

    event = {"tenant_id": "t-1", "anomaly_id": "a-1", "rule_name": "BRUTE_FORCE", "severity": "P0"}
    with patch("services.severity_policy_service.SeverityPolicyService.resolve_severity",
               new_callable=AsyncMock) as mock_resolve:
        await consumer._handle_anomaly(event, svc, isvc, conn)

    mock_resolve.assert_not_awaited()
    isvc.auto_create_for_anomaly.assert_awaited_once_with(
        anomaly_id="a-1", tenant_id="t-1", rule_name="BRUTE_FORCE",
        severity="P0", assigned_ciso_id=None,
    )


@pytest.mark.asyncio
async def test_handle_anomaly_resolves_severity_via_policy_when_missing():
    """Same shared policy lookup security_consumer.py uses — the two consumers
    can no longer default to different severities for the same event."""
    consumer = NotifConsumer.__new__(NotifConsumer)
    consumer._lookup_ciso = AsyncMock(return_value=None)
    svc = AsyncMock()
    isvc = AsyncMock()
    conn = AsyncMock()

    event = {"tenant_id": "t-1", "anomaly_id": "a-2", "rule_name": "SOME_NEW_RULE"}
    with patch("services.severity_policy_service.SeverityPolicyService.resolve_severity",
               new_callable=AsyncMock, return_value="P3") as mock_resolve:
        await consumer._handle_anomaly(event, svc, isvc, conn)

    mock_resolve.assert_awaited_once_with(domain="ANOMALY_RULE", value="SOME_NEW_RULE")
    isvc.auto_create_for_anomaly.assert_awaited_once_with(
        anomaly_id="a-2", tenant_id="t-1", rule_name="SOME_NEW_RULE",
        severity="P3", assigned_ciso_id=None,
    )
