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


# ── SHARE_ACCESSED — workflows/vault_shares.py's notify_share_accessed activity ──

@pytest.mark.asyncio
async def test_share_accessed_notifies_employee_via_email():
    consumer = NotifConsumer.__new__(NotifConsumer)
    svc = AsyncMock()
    isvc = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"email": "emp@example.com"})

    event = {"event_type": "SHARE_ACCESSED", "employee_user_id": "emp-1", "tenant_id": "t-1"}
    await consumer._dispatch(event, "SHARE_ACCESSED", svc, isvc, conn)

    conn.fetchrow.assert_awaited_once()
    svc.notify.assert_awaited_once()
    call = svc.notify.call_args.kwargs
    assert call["recipient_id"] == "emp-1"
    assert call["recipient_email"] == "emp@example.com"
    assert call["recipient_type"] == RecipientType.EMPLOYEE
    assert call["channel"] == Channel.EMAIL
    assert call["template_id"] == "SHARE_ACCESSED"


@pytest.mark.asyncio
async def test_share_accessed_no_employee_email_does_not_crash():
    consumer = NotifConsumer.__new__(NotifConsumer)
    svc = AsyncMock()
    isvc = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)

    event = {"event_type": "SHARE_ACCESSED", "employee_user_id": "emp-1"}
    await consumer._dispatch(event, "SHARE_ACCESSED", svc, isvc, conn)

    svc.notify.assert_not_awaited()


# ── DOC_ROUTED — mobile column bug ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_doc_routed_queries_mobile_column_not_phone():
    """employee_user has no 'phone' column (schema.sql: it's 'mobile') — the old
    query crashed with UndefinedColumnError on every real invocation."""
    consumer = NotifConsumer.__new__(NotifConsumer)
    svc = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"email": "emp@example.com", "mobile": "+919876543210"})

    event = {"employee_user_id": "emp-1", "doc_type": "SALARY_SLIP", "tenant_id": "t-1"}
    await consumer._handle_doc_routed(event, svc, conn)

    query = conn.fetchrow.call_args.args[0]
    assert "mobile" in query
    assert "phone" not in query

    whatsapp_call = next(c for c in svc.notify.call_args_list if c.kwargs["channel"] == Channel.WHATSAPP)
    assert whatsapp_call.kwargs["recipient_phone"] == "+919876543210"


# ── VAULT_WELCOME / VAULT_WELCOME_REJOIN / EMPLOYEE_CREDENTIALS_ISSUED ───────
# Previously unhandled entirely — fell through to the "unhandled event_type"
# debug log, so no employee was ever notified their account/vault was ready.

@pytest.mark.asyncio
async def test_dispatch_routes_vault_welcome_to_handler():
    consumer = NotifConsumer.__new__(NotifConsumer)
    svc = AsyncMock()
    isvc = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)

    event = {"event_type": "VAULT_WELCOME", "recipient_id": "eu-1", "tenant_id": "t-1"}
    await consumer._dispatch(event, "VAULT_WELCOME", svc, isvc, conn)

    conn.fetchrow.assert_awaited_once()


@pytest.mark.asyncio
async def test_employee_welcome_notifies_via_sms_when_mobile_present():
    consumer = NotifConsumer.__new__(NotifConsumer)
    svc = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"mobile": "+919876543210", "email": None})

    event = {"event_type": "VAULT_WELCOME", "recipient_id": "eu-1", "tenant_id": "t-1"}
    await consumer._handle_employee_welcome(event, "VAULT_WELCOME", svc, conn)

    svc.notify.assert_awaited_once()
    call = svc.notify.call_args.kwargs
    assert call["recipient_phone"] == "+919876543210"
    assert call["channel"] == Channel.SMS
    assert call["recipient_type"] == RecipientType.EMPLOYEE
    assert call["template_id"] == "VAULT_WELCOME"


@pytest.mark.asyncio
async def test_employee_welcome_notifies_via_email_when_only_email_present():
    consumer = NotifConsumer.__new__(NotifConsumer)
    svc = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"mobile": None, "email": "emp@example.com"})

    event = {"event_type": "EMPLOYEE_CREDENTIALS_ISSUED", "recipient_id": "eu-1", "tenant_id": "t-1"}
    await consumer._handle_employee_welcome(event, "EMPLOYEE_CREDENTIALS_ISSUED", svc, conn)

    svc.notify.assert_awaited_once()
    call = svc.notify.call_args.kwargs
    assert call["recipient_email"] == "emp@example.com"
    assert call["channel"] == Channel.EMAIL


@pytest.mark.asyncio
async def test_employee_welcome_dispatches_to_both_channels_when_both_present():
    consumer = NotifConsumer.__new__(NotifConsumer)
    svc = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"mobile": "+919876543210", "email": "emp@example.com"})

    event = {"event_type": "VAULT_WELCOME_REJOIN", "recipient_id": "eu-1", "tenant_id": "t-1"}
    await consumer._handle_employee_welcome(event, "VAULT_WELCOME_REJOIN", svc, conn)

    assert svc.notify.await_count == 2
    channels = {c.kwargs["channel"] for c in svc.notify.call_args_list}
    assert channels == {Channel.SMS, Channel.EMAIL}


@pytest.mark.asyncio
async def test_employee_welcome_no_delivery_channel_does_not_crash():
    consumer = NotifConsumer.__new__(NotifConsumer)
    svc = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"mobile": None, "email": None})

    event = {"event_type": "VAULT_WELCOME", "recipient_id": "eu-1", "tenant_id": "t-1"}
    await consumer._handle_employee_welcome(event, "VAULT_WELCOME", svc, conn)

    svc.notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_employee_welcome_missing_recipient_id_does_not_crash():
    consumer = NotifConsumer.__new__(NotifConsumer)
    svc = AsyncMock()
    conn = AsyncMock()

    event = {"event_type": "VAULT_WELCOME", "tenant_id": "t-1"}
    await consumer._handle_employee_welcome(event, "VAULT_WELCOME", svc, conn)

    conn.fetchrow.assert_not_awaited()
    svc.notify.assert_not_awaited()
