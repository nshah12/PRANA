"""
Tests for kafka/producer.py's platform_event() — specifically the dual-publish
to TOPIC_NOTIF for event types that need a real human (PA) notified rather than
just ops/PagerDuty alerting.

Regression coverage for a confirmed gap: STORAGE_EXPANSION_REQUESTED and
ONBOARDING_REVIEW_SLA_BREACH only reached PlatformConsumer (ops-alert path,
no handler for either type — falls through to a log line). No PA was ever
actually notified despite workflows/platform_ops.py's docstrings claiming a
human-in-the-loop signal / auto-escalation to senior PA team.
"""
from unittest.mock import AsyncMock

import pytest

from kafka.producer import KafkaPub, TOPIC_PLATFORM, TOPIC_NOTIF


def _make_pub():
    pub = KafkaPub.__new__(KafkaPub)  # skip __init__ (no real AIOKafkaProducer)
    pub.publish = AsyncMock()
    return pub


@pytest.mark.asyncio
async def test_storage_expansion_requested_reaches_notif_topic():
    pub = _make_pub()
    await pub.platform_event({"event_type": "STORAGE_EXPANSION_REQUESTED", "tenant_id": "t-1"})
    topics = [c.args[0] for c in pub.publish.call_args_list]
    assert TOPIC_PLATFORM in topics
    assert TOPIC_NOTIF in topics


@pytest.mark.asyncio
async def test_onboarding_review_sla_breach_reaches_notif_topic():
    pub = _make_pub()
    await pub.platform_event({"event_type": "ONBOARDING_REVIEW_SLA_BREACH", "tenant_id": "t-2"})
    topics = [c.args[0] for c in pub.publish.call_args_list]
    assert TOPIC_PLATFORM in topics
    assert TOPIC_NOTIF in topics


@pytest.mark.asyncio
async def test_share_accessed_reaches_notif_topic():
    """Regression: routers/share_access.py's serve_shared_document previously had
    no way to notify the document owner their share was viewed except a raw
    kafka.publish() call (KAFKA-01 violation) — this domain helper replaces it."""
    pub = _make_pub()
    await pub.share_accessed({"event_type": "SHARE_ACCESSED", "employee_user_id": "emp-1"})
    topics = [c.args[0] for c in pub.publish.call_args_list]
    assert TOPIC_NOTIF in topics


@pytest.mark.asyncio
async def test_worker_crashed_does_not_reach_notif_topic():
    """Ops-only events (PagerDuty/Slack territory) must not also spam PA email."""
    pub = _make_pub()
    await pub.platform_event({"event_type": "WORKER_CRASHED", "service": "ingest"})
    topics = [c.args[0] for c in pub.publish.call_args_list]
    assert TOPIC_PLATFORM in topics
    assert TOPIC_NOTIF not in topics


# ── oa_user_event() / tenant_event() dual-publish for notification-worthy events ──
# Regression coverage for a confirmed gap: ELEVATION_APPROVED/DENIED and
# TENANT_PROVISIONED never reached CommunicationHubConsumer (only TOPIC_OA_USERS/TOPIC_TENANT +
# TOPIC_AUDIT), even though CommunicationHubConsumer's _handle_elevation/_handle_welcome are
# fully correct, already-tested handlers for exactly these event types — they were
# just unreachable dead code because nothing ever published there.

from kafka.producer import TOPIC_OA_USERS, TOPIC_TENANT  # noqa: E402


@pytest.mark.asyncio
async def test_elevation_approved_reaches_notif_topic():
    pub = _make_pub()
    await pub.oa_user_event({"event_type": "ELEVATION_APPROVED", "tenant_id": "t-1", "oa_user_id": "oa-1"})
    topics = [c.args[0] for c in pub.publish.call_args_list]
    assert TOPIC_OA_USERS in topics
    assert TOPIC_NOTIF in topics


@pytest.mark.asyncio
async def test_elevation_denied_reaches_notif_topic():
    pub = _make_pub()
    await pub.oa_user_event({"event_type": "ELEVATION_DENIED", "tenant_id": "t-1", "oa_user_id": "oa-1"})
    topics = [c.args[0] for c in pub.publish.call_args_list]
    assert TOPIC_OA_USERS in topics
    assert TOPIC_NOTIF in topics


@pytest.mark.asyncio
async def test_elevation_expired_does_not_reach_notif_topic():
    """ELEVATION_EXPIRED stays a bell-only notification via OAUserConsumer — it
    isn't handled by CommunicationHubConsumer, so dual-publishing it would be a no-op at best."""
    pub = _make_pub()
    await pub.oa_user_event({"event_type": "ELEVATION_EXPIRED", "tenant_id": "t-1", "oa_user_id": "oa-1"})
    topics = [c.args[0] for c in pub.publish.call_args_list]
    assert TOPIC_OA_USERS in topics
    assert TOPIC_NOTIF not in topics


@pytest.mark.asyncio
async def test_oa_user_created_does_not_reach_notif_topic():
    """OA_USER_CREATED's welcome email is owned entirely by OAUserConsumer's own
    direct notify_email() call — dual-publishing to TOPIC_NOTIF too would double-send."""
    pub = _make_pub()
    await pub.oa_user_event({"event_type": "OA_USER_CREATED", "tenant_id": "t-1", "oa_user_id": "oa-1"})
    topics = [c.args[0] for c in pub.publish.call_args_list]
    assert TOPIC_OA_USERS in topics
    assert TOPIC_NOTIF not in topics


@pytest.mark.asyncio
async def test_tenant_provisioned_reaches_notif_topic():
    pub = _make_pub()
    await pub.tenant_event({"event_type": "TENANT_PROVISIONED", "tenant_id": "t-1", "admin_email": "a@b.com"})
    topics = [c.args[0] for c in pub.publish.call_args_list]
    assert TOPIC_TENANT in topics
    assert TOPIC_NOTIF in topics


@pytest.mark.asyncio
async def test_tenant_created_does_not_reach_notif_topic():
    pub = _make_pub()
    await pub.tenant_event({"event_type": "TENANT_CREATED", "tenant_id": "t-1"})
    topics = [c.args[0] for c in pub.publish.call_args_list]
    assert TOPIC_TENANT in topics
    assert TOPIC_NOTIF not in topics
