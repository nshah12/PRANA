"""Tests for OAUserConsumer — prana.oa_users.events"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def db_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.fixture
def consumer(db_pool):
    from kafka.consumers.oa_user_consumer import OAUserConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    pool, _ = db_pool
    temporal = AsyncMock()
    return OAUserConsumer(settings, db_pool=pool, temporal_client=temporal)


@pytest.mark.asyncio
async def test_oa_user_created_publishes_welcome_email(consumer):
    event = {"event_type": "OA_USER_CREATED", "oa_user_id": "u-1",
             "email": "ops@co.com", "tenant_id": "t-1", "role": "oa_operator"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.oa_user_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("OA_USER_CREATED", event)
    mock_kafka.notify_email.assert_awaited_once()
    notif = mock_kafka.notify_email.call_args[0][0]
    assert notif["template_id"] == "OA_WELCOME"
    assert notif["recipient_id"] == "u-1"
    # Regression: this used to put the login_url payload under a "payload" key,
    # but EmailConsumer/NotificationService only ever read "template_data" — the
    # email would send with an empty body.
    assert notif["template_data"] == {"login_url": event.get("login_url", "https://prana.in/org/login")}
    assert "payload" not in notif


@pytest.mark.asyncio
async def test_oa_welcome_resent_publishes_welcome_email(consumer):
    """Resend action reuses the same welcome-email dispatch as OA_USER_CREATED."""
    event = {"event_type": "OA_WELCOME_RESENT", "oa_user_id": "u-1",
             "email": "bounced@co.com", "tenant_id": "t-1", "resent_by": "admin-1"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.oa_user_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("OA_WELCOME_RESENT", event)
    mock_kafka.notify_email.assert_awaited_once()
    notif = mock_kafka.notify_email.call_args[0][0]
    assert notif["template_id"] == "OA_WELCOME"
    assert notif["recipient_id"] == "u-1"
    assert notif["recipient_email"] == "bounced@co.com"


@pytest.mark.asyncio
async def test_oa_user_locked_starts_policy_lock_workflow(consumer):
    """Regression guard: this used to start "AccountLockWorkflow" — never
    @workflow.defn'd anywhere. The real workflow is PolicyLockWorkflow
    (workflows/security.py), registered on secops-queue in worker.py."""
    event = {"event_type": "OA_USER_LOCKED", "oa_user_id": "u-2", "tenant_id": "t-1"}
    await consumer._dispatch("OA_USER_LOCKED", event)
    consumer._temporal.start_workflow.assert_awaited_once()
    call = consumer._temporal.start_workflow.call_args
    assert call.args[0] == "PolicyLockWorkflow"
    assert call.args[1]["user_type"] == "oa_user"
    assert call.args[1]["user_id"] == "u-2"
    assert call.kwargs["id"] == "account-lock-oa-u-2"
    assert call.kwargs["task_queue"] == "secops-queue"


@pytest.mark.asyncio
async def test_elevation_approved_no_longer_sends_email_directly(consumer):
    """ELEVATION_APPROVED/DENIED emails are now owned by CommunicationHubConsumer's
    _handle_elevation (already correct: looks up oa_user.email, uses
    template_data) — reachable because kafka.oa_user_event() dual-publishes
    these two event types to TOPIC_NOTIF. OAUserConsumer must not also send its
    own email, or the requestor gets duplicate notifications."""
    event = {"event_type": "ELEVATION_APPROVED", "oa_user_id": "u-3",
             "requestor_id": "u-3", "elevation_id": "e-1", "tenant_id": "t-1"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.oa_user_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("ELEVATION_APPROVED", event)
    mock_kafka.notify_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_elevation_denied_no_longer_sends_email_directly(consumer):
    event = {"event_type": "ELEVATION_DENIED", "oa_user_id": "u-3",
             "requestor_id": "u-3", "elevation_id": "e-1", "tenant_id": "t-1"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.oa_user_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("ELEVATION_DENIED", event)
    mock_kafka.notify_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_elevation_expired_sends_bell_not_email(consumer):
    event = {"event_type": "ELEVATION_EXPIRED", "oa_user_id": "u-4",
             "requestor_id": "u-4", "elevation_id": "e-2", "tenant_id": "t-1"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.oa_user_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("ELEVATION_EXPIRED", event)
    mock_kafka.notify_bell.assert_awaited_once()
    mock_kafka.notify_email.assert_not_awaited()
    notif = mock_kafka.notify_bell.call_args[0][0]
    # Regression: this used to put duration_hours under a "payload" key that
    # BellConsumer/NotificationService never read.
    assert notif["template_data"] == {"elevation_id": "e-2", "duration_hours": None}
    assert "payload" not in notif


# ── ROLE_CHANGED — PRIVILEGE_ESCALATION detection ───────────────────────────
# See prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §3.1. This consumer never writes
# anomaly_event directly — it publishes ANOMALY_DETECTED to prana.security.events,
# reusing the exact same pipeline (SecurityConsumer persists + creates incidents)
# as every other anomaly source.

@pytest.mark.asyncio
async def test_role_changed_promotion_to_admin_flags_escalation():
    from kafka.consumers.oa_user_consumer import OAUserConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    consumer = OAUserConsumer(settings, db_pool=None, temporal_client=None)

    event = {"event_type": "ROLE_CHANGED", "tenant_id": "t-1", "oa_user_id": "u-5",
             "old_role": "oa_operator", "new_role": "oa_admin", "actor_id": "admin-1"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.oa_user_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("ROLE_CHANGED", event)

    mock_kafka.security_event.assert_awaited_once()
    payload = mock_kafka.security_event.call_args[0][0]
    assert payload["event_type"] == "ANOMALY_DETECTED"
    assert payload["rule_name"] == "PRIVILEGE_ESCALATION"
    assert payload["tenant_id"] == "t-1"
    assert payload["actor_id"] == "admin-1"
    assert payload["event_metadata"]["target_oa_user_id"] == "u-5"
    assert payload["event_metadata"]["old_role"] == "oa_operator"
    assert payload["event_metadata"]["new_role"] == "oa_admin"


@pytest.mark.asyncio
async def test_role_changed_self_change_flags_escalation_regardless_of_direction():
    """An admin changing their OWN role — even sideways/downward — is suspicious;
    normal role management always targets someone else."""
    from kafka.consumers.oa_user_consumer import OAUserConsumer
    settings = MagicMock()
    consumer = OAUserConsumer(settings, db_pool=None, temporal_client=None)

    event = {"event_type": "ROLE_CHANGED", "tenant_id": "t-1", "oa_user_id": "admin-1",
             "old_role": "oa_admin", "new_role": "ciso", "actor_id": "admin-1"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.oa_user_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("ROLE_CHANGED", event)

    mock_kafka.security_event.assert_awaited_once()
    payload = mock_kafka.security_event.call_args[0][0]
    assert payload["rule_name"] == "PRIVILEGE_ESCALATION"


@pytest.mark.asyncio
async def test_role_changed_demotion_by_someone_else_not_flagged():
    from kafka.consumers.oa_user_consumer import OAUserConsumer
    settings = MagicMock()
    consumer = OAUserConsumer(settings, db_pool=None, temporal_client=None)

    event = {"event_type": "ROLE_CHANGED", "tenant_id": "t-1", "oa_user_id": "u-6",
             "old_role": "oa_admin", "new_role": "oa_operator", "actor_id": "admin-1"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.oa_user_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("ROLE_CHANGED", event)

    mock_kafka.security_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_role_changed_lateral_move_by_someone_else_not_flagged():
    """chro -> cfo (both specialist rank 2, changed by a different admin) is routine."""
    from kafka.consumers.oa_user_consumer import OAUserConsumer
    settings = MagicMock()
    consumer = OAUserConsumer(settings, db_pool=None, temporal_client=None)

    event = {"event_type": "ROLE_CHANGED", "tenant_id": "t-1", "oa_user_id": "u-7",
             "old_role": "chro", "new_role": "cfo", "actor_id": "admin-1"}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.oa_user_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        await consumer._dispatch("ROLE_CHANGED", event)

    mock_kafka.security_event.assert_not_awaited()
