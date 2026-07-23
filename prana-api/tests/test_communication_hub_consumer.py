"""Tests for kafka/consumers/communication_hub_consumer.py — renamed/repurposed
from NotifConsumer per prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md.

Handler tests mock _fan_out() directly (verifies correct recipient resolution
+ template_id selection — the same DB-lookup logic NotifConsumer had).
_fan_out() itself is tested separately against a real ChannelPolicyService
call chain (mocked at the DB boundary) + kafka producer dispatch.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kafka.consumers.communication_hub_consumer import CommunicationHubConsumer
from kafka.producer import TOPIC_COMM, TOPIC_NOTIF
from services.notification_service import RecipientType


def _consumer():
    return CommunicationHubConsumer.__new__(CommunicationHubConsumer)  # skip __init__


# ---------------------------------------------------------------------------
# _fan_out — the one place a channel decision is made
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fan_out_resolves_policy_and_publishes_to_each_channel():
    consumer = _consumer()
    conn = AsyncMock()
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.communication_hub_consumer.ChannelPolicyService.resolve",
               new=AsyncMock(return_value=["email", "portal_bell"])), \
         patch("kafka.consumers.communication_hub_consumer.get_kafka_producer",
               new=AsyncMock(return_value=mock_kafka)):
        await consumer._fan_out(
            template_id="ANOMALY_P0_ALERT", tenant_id="t-1", recipient_id="ciso-1",
            recipient_type=RecipientType.OA_USER, recipient_email="ciso@corp.in",
            template_data={"rule_name": "X"}, event_type="ANOMALY_DETECTED", conn=conn,
        )
    mock_kafka.notify_email.assert_awaited_once()
    mock_kafka.notify_bell.assert_awaited_once()
    payload = mock_kafka.notify_email.call_args.args[0]
    assert payload["template_id"] == "ANOMALY_P0_ALERT"
    assert payload["recipient_email"] == "ciso@corp.in"


@pytest.mark.asyncio
async def test_fan_out_does_nothing_when_no_policy_resolved():
    consumer = _consumer()
    conn = AsyncMock()
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.communication_hub_consumer.ChannelPolicyService.resolve",
               new=AsyncMock(return_value=[])), \
         patch("kafka.consumers.communication_hub_consumer.get_kafka_producer",
               new=AsyncMock(return_value=mock_kafka)):
        await consumer._fan_out(
            template_id="UNSEEDED", tenant_id=None, recipient_id="r-1",
            recipient_type=RecipientType.EMPLOYEE, template_data={}, event_type="X", conn=conn,
        )
    mock_kafka.notify_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_fan_out_ivr_channel_publishes_to_notify_ivr():
    consumer = _consumer()
    conn = AsyncMock()
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.communication_hub_consumer.ChannelPolicyService.resolve",
               new=AsyncMock(return_value=["ivr"])), \
         patch("kafka.consumers.communication_hub_consumer.get_kafka_producer",
               new=AsyncMock(return_value=mock_kafka)):
        await consumer._fan_out(
            template_id="ANOMALY_P0_ALERT", tenant_id="t-1", recipient_id="ciso-1",
            recipient_type=RecipientType.OA_USER, recipient_phone="+919000000000",
            template_data={}, event_type="ANOMALY_DETECTED", conn=conn,
        )
    mock_kafka.notify_ivr.assert_awaited_once()


# ---------------------------------------------------------------------------
# communication_requested (new generic intake topic)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_communication_requested_calls_fan_out():
    consumer = _consumer()
    conn = AsyncMock()
    consumer._fan_out = AsyncMock()
    event = {"template_id": "VAULT_WELCOME", "recipient_id": "emp-1", "tenant_id": "t-1",
             "recipient_type": "EMPLOYEE", "template_data": {"x": 1}}
    await consumer._handle_communication_requested(event, conn)
    consumer._fan_out.assert_awaited_once()
    call = consumer._fan_out.call_args.kwargs
    assert call["template_id"] == "VAULT_WELCOME"
    assert call["recipient_id"] == "emp-1"


@pytest.mark.asyncio
async def test_communication_requested_missing_fields_skips():
    consumer = _consumer()
    conn = AsyncMock()
    consumer._fan_out = AsyncMock()
    await consumer._handle_communication_requested({"template_id": "X"}, conn)
    consumer._fan_out.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_routes_comm_topic_to_communication_requested():
    consumer = _consumer()
    isvc = AsyncMock()
    conn = AsyncMock()
    consumer._handle_communication_requested = AsyncMock()
    await consumer._dispatch({"template_id": "X", "recipient_id": "r-1"}, None, TOPIC_COMM, isvc, conn)
    consumer._handle_communication_requested.assert_awaited_once()


# ---------------------------------------------------------------------------
# AUDIT_INTEGRITY_MISMATCH
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_integrity_mismatch_dispatches_to_handler():
    consumer = _consumer()
    isvc = AsyncMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    event = {"event_type": "AUDIT_INTEGRITY_MISMATCH", "checked_count": 500, "mismatched_count": 1}
    await consumer._dispatch(event, "AUDIT_INTEGRITY_MISMATCH", TOPIC_NOTIF, isvc, conn)
    conn.fetch.assert_awaited_once()
    assert "portal_admin" in conn.fetch.call_args.args[0]
    assert "ACTIVE" in conn.fetch.call_args.args[0]


@pytest.mark.asyncio
async def test_audit_integrity_mismatch_notifies_every_active_pa_admin():
    consumer = _consumer()
    consumer._fan_out = AsyncMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[
        {"pa_id": "pa-1", "email": "pa1@prana.in"},
        {"pa_id": "pa-2", "email": "pa2@prana.in"},
    ])
    event = {"event_type": "AUDIT_INTEGRITY_MISMATCH", "checked_count": 500, "mismatched_count": 2}
    await consumer._handle_audit_integrity_mismatch(event, conn)

    assert consumer._fan_out.await_count == 2
    first_call = consumer._fan_out.call_args_list[0].kwargs
    assert first_call["tenant_id"] is None
    assert first_call["recipient_id"] == "pa-1"
    assert first_call["recipient_email"] == "pa1@prana.in"
    assert first_call["template_id"] == "AUDIT_INTEGRITY_MISMATCH"
    assert first_call["template_data"]["mismatched_count"] == 2


@pytest.mark.asyncio
async def test_audit_integrity_mismatch_no_pa_admins_does_not_crash():
    consumer = _consumer()
    consumer._fan_out = AsyncMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    await consumer._handle_audit_integrity_mismatch({"event_type": "AUDIT_INTEGRITY_MISMATCH"}, conn)
    consumer._fan_out.assert_not_awaited()


# ---------------------------------------------------------------------------
# STORAGE_EXPANSION_REQUESTED / ONBOARDING_REVIEW_SLA_BREACH
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_storage_expansion_requested_notifies_every_active_pa_admin():
    consumer = _consumer()
    consumer._fan_out = AsyncMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"pa_id": "pa-1", "email": "pa1@prana.in"}])
    event = {"event_type": "STORAGE_EXPANSION_REQUESTED", "tenant_id": "t-1", "request_id": "req-1"}
    await consumer._handle_storage_expansion_requested(event, conn)

    consumer._fan_out.assert_awaited_once()
    call = consumer._fan_out.call_args.kwargs
    assert call["tenant_id"] == "t-1"
    assert call["recipient_id"] == "pa-1"
    assert call["template_id"] == "STORAGE_EXPANSION_REQUESTED"
    assert call["template_data"]["request_id"] == "req-1"


@pytest.mark.asyncio
async def test_onboarding_review_sla_breach_notifies_every_active_pa_admin():
    consumer = _consumer()
    consumer._fan_out = AsyncMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"pa_id": "pa-1", "email": "pa1@prana.in"}])
    event = {"event_type": "ONBOARDING_REVIEW_SLA_BREACH", "tenant_id": "t-2"}
    await consumer._handle_onboarding_review_sla_breach(event, conn)

    consumer._fan_out.assert_awaited_once()
    call = consumer._fan_out.call_args.kwargs
    assert call["tenant_id"] == "t-2"
    assert call["template_id"] == "ONBOARDING_REVIEW_SLA_BREACH"


# ---------------------------------------------------------------------------
# _handle_anomaly — severity resolution + template selection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_anomaly_uses_explicit_severity_when_present():
    consumer = _consumer()
    consumer._lookup_ciso = AsyncMock(return_value={"oa_user_id": "ciso-1", "email": "c@corp.in"})
    consumer._fan_out = AsyncMock()
    isvc = AsyncMock()
    conn = AsyncMock()

    event = {"tenant_id": "t-1", "anomaly_id": "a-1", "rule_name": "BRUTE_FORCE", "severity": "P0"}
    with patch("services.severity_policy_service.SeverityPolicyService.resolve_severity",
               new_callable=AsyncMock) as mock_resolve:
        await consumer._handle_anomaly(event, isvc, conn)

    mock_resolve.assert_not_awaited()
    consumer._fan_out.assert_awaited_once()
    assert consumer._fan_out.call_args.kwargs["template_id"] == "ANOMALY_P0_ALERT"
    isvc.auto_create_for_anomaly.assert_awaited_once_with(
        anomaly_id="a-1", tenant_id="t-1", rule_name="BRUTE_FORCE",
        severity="P0", assigned_ciso_id="ciso-1",
    )


@pytest.mark.asyncio
async def test_handle_anomaly_resolves_severity_via_policy_when_missing():
    consumer = _consumer()
    consumer._lookup_ciso = AsyncMock(return_value=None)
    consumer._fan_out = AsyncMock()
    isvc = AsyncMock()
    conn = AsyncMock()

    event = {"tenant_id": "t-1", "anomaly_id": "a-2", "rule_name": "SOME_NEW_RULE"}
    with patch("services.severity_policy_service.SeverityPolicyService.resolve_severity",
               new_callable=AsyncMock, return_value="P3") as mock_resolve:
        await consumer._handle_anomaly(event, isvc, conn)

    mock_resolve.assert_awaited_once_with(domain="ANOMALY_RULE", value="SOME_NEW_RULE")
    consumer._fan_out.assert_not_awaited()   # P3 has no template mapping, and no ciso anyway
    isvc.auto_create_for_anomaly.assert_awaited_once_with(
        anomaly_id="a-2", tenant_id="t-1", rule_name="SOME_NEW_RULE",
        severity="P3", assigned_ciso_id=None,
    )


@pytest.mark.asyncio
async def test_handle_anomaly_p3_with_ciso_still_no_fan_out():
    """P3 has no NotificationTemplate mapping — auto-incident creation still
    happens, but no notification is fanned out (matches old notify_anomaly's
    explicit P3 early-return)."""
    consumer = _consumer()
    consumer._lookup_ciso = AsyncMock(return_value={"oa_user_id": "ciso-1", "email": "c@corp.in"})
    consumer._fan_out = AsyncMock()
    isvc = AsyncMock()
    conn = AsyncMock()

    event = {"tenant_id": "t-1", "anomaly_id": "a-3", "rule_name": "LOW_SIGNAL", "severity": "P3"}
    await consumer._handle_anomaly(event, isvc, conn)

    consumer._fan_out.assert_not_awaited()
    isvc.auto_create_for_anomaly.assert_awaited_once()


# ---------------------------------------------------------------------------
# SHARE_ACCESSED
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_share_accessed_notifies_employee_via_fan_out():
    consumer = _consumer()
    consumer._fan_out = AsyncMock()
    isvc = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"email": "emp@example.com"})

    event = {"event_type": "SHARE_ACCESSED", "employee_user_id": "emp-1", "tenant_id": "t-1"}
    await consumer._dispatch(event, "SHARE_ACCESSED", TOPIC_NOTIF, isvc, conn)

    conn.fetchrow.assert_awaited_once()
    consumer._fan_out.assert_awaited_once()
    call = consumer._fan_out.call_args.kwargs
    assert call["recipient_id"] == "emp-1"
    assert call["recipient_email"] == "emp@example.com"
    assert call["template_id"] == "SHARE_ACCESSED"


@pytest.mark.asyncio
async def test_share_accessed_no_employee_email_does_not_crash():
    consumer = _consumer()
    consumer._fan_out = AsyncMock()
    isvc = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)

    event = {"event_type": "SHARE_ACCESSED", "employee_user_id": "emp-1"}
    await consumer._dispatch(event, "SHARE_ACCESSED", TOPIC_NOTIF, isvc, conn)
    consumer._fan_out.assert_not_awaited()


# ---------------------------------------------------------------------------
# DOC_ROUTED — enc_mobile decryption
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_doc_routed_queries_enc_mobile_and_decrypts_via_kms():
    consumer = _consumer()
    consumer._settings = MagicMock()
    consumer._kms = MagicMock()
    consumer._kms.decrypt_value = MagicMock(return_value="+919876543210")
    consumer._fan_out = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"email": "emp@example.com", "enc_mobile": "kms-ciphertext-blob"})

    event = {"employee_user_id": "emp-1", "doc_type": "SALARY_SLIP", "tenant_id": "t-1"}
    await consumer._handle_doc_routed(event, conn)

    query = conn.fetchrow.call_args.args[0]
    assert "enc_mobile" in query
    consumer._fan_out.assert_awaited_once()
    call = consumer._fan_out.call_args.kwargs
    assert call["recipient_phone"] == "+919876543210"
    assert call["template_id"] == "DOC_ROUTED"


@pytest.mark.asyncio
async def test_doc_routed_no_enc_mobile_skips_phone_gracefully():
    consumer = _consumer()
    consumer._settings = MagicMock()
    consumer._kms = MagicMock()
    consumer._fan_out = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"email": "emp@example.com", "enc_mobile": None})

    event = {"employee_user_id": "emp-1", "doc_type": "SALARY_SLIP", "tenant_id": "t-1"}
    await consumer._handle_doc_routed(event, conn)   # must not raise

    consumer._kms.decrypt_value.assert_not_called()
    call = consumer._fan_out.call_args.kwargs
    assert call["recipient_phone"] is None


# ---------------------------------------------------------------------------
# TENANT_PROVISIONED / OA_USER_CREATED / DIGEST_READY dead-code guards
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tenant_provisioned_dispatches_to_welcome_handler():
    consumer = _consumer()
    consumer._fan_out = AsyncMock()
    isvc = AsyncMock()
    conn = AsyncMock()

    event = {"event_type": "TENANT_PROVISIONED", "tenant_id": "t-1",
             "admin_email": "admin@acme.example", "login_url": "https://prana.in/org/login"}
    await consumer._dispatch(event, "TENANT_PROVISIONED", TOPIC_NOTIF, isvc, conn)

    consumer._fan_out.assert_awaited_once()
    call = consumer._fan_out.call_args.kwargs
    assert call["recipient_email"] == "admin@acme.example"
    assert call["template_id"] == "OA_WELCOME"


@pytest.mark.asyncio
async def test_oa_user_created_no_longer_dispatched_here():
    consumer = _consumer()
    consumer._fan_out = AsyncMock()
    isvc = AsyncMock()
    conn = AsyncMock()
    event = {"event_type": "OA_USER_CREATED", "tenant_id": "t-1", "email": "new@acme.example"}
    await consumer._dispatch(event, "OA_USER_CREATED", TOPIC_NOTIF, isvc, conn)
    consumer._fan_out.assert_not_awaited()


@pytest.mark.asyncio
async def test_digest_ready_no_longer_dispatched_here():
    consumer = _consumer()
    consumer._fan_out = AsyncMock()
    isvc = AsyncMock()
    conn = AsyncMock()
    event = {"event_type": "DIGEST_READY", "tenant_id": "t-1", "role": "chro"}
    await consumer._dispatch(event, "DIGEST_READY", TOPIC_NOTIF, isvc, conn)
    consumer._fan_out.assert_not_awaited()
    conn.fetch.assert_not_awaited()


# ---------------------------------------------------------------------------
# _handle_employee_welcome — one fan_out carries both phone and email
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_employee_welcome_fans_out_once_with_both_contact_fields():
    consumer = _consumer()
    consumer._settings = MagicMock()
    consumer._kms = MagicMock()
    consumer._kms.decrypt_value = MagicMock(return_value="+919876543210")
    consumer._fan_out = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"enc_mobile": "kms-ciphertext-blob", "email": "emp@example.com"})

    event = {"event_type": "VAULT_WELCOME_REJOIN", "recipient_id": "eu-1", "tenant_id": "t-1"}
    await consumer._handle_employee_welcome(event, "VAULT_WELCOME_REJOIN", conn)

    consumer._fan_out.assert_awaited_once()
    call = consumer._fan_out.call_args.kwargs
    assert call["recipient_phone"] == "+919876543210"
    assert call["recipient_email"] == "emp@example.com"
    assert call["template_id"] == "VAULT_WELCOME_REJOIN"


@pytest.mark.asyncio
async def test_employee_welcome_no_delivery_channel_does_not_fan_out():
    consumer = _consumer()
    consumer._settings = MagicMock()
    consumer._kms = MagicMock()
    consumer._fan_out = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"enc_mobile": None, "email": None})

    event = {"event_type": "VAULT_WELCOME", "recipient_id": "eu-1", "tenant_id": "t-1"}
    await consumer._handle_employee_welcome(event, "VAULT_WELCOME", conn)
    consumer._fan_out.assert_not_awaited()


@pytest.mark.asyncio
async def test_employee_welcome_missing_recipient_id_does_not_crash():
    consumer = _consumer()
    consumer._fan_out = AsyncMock()
    conn = AsyncMock()

    event = {"event_type": "VAULT_WELCOME", "tenant_id": "t-1"}
    await consumer._handle_employee_welcome(event, "VAULT_WELCOME", conn)

    conn.fetchrow.assert_not_awaited()
    consumer._fan_out.assert_not_awaited()
