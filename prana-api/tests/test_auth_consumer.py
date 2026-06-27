"""Tests for AuthConsumer — prana.auth.events"""
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
    from kafka.consumers.auth_consumer import AuthConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    pool, _ = db_pool
    temporal = AsyncMock()
    return AuthConsumer(settings, db_pool=pool, temporal_client=temporal)


@pytest.mark.asyncio
async def test_login_failed_below_threshold_no_lock(consumer, db_pool):
    _, conn = db_pool
    conn.fetchrow.return_value = {"cnt": 2}  # below threshold of 5
    event = {"event_type": "USER_LOGIN_FAILED", "user_id": "u-1", "user_type": "employee"}
    await consumer._dispatch("USER_LOGIN_FAILED", event)
    consumer._temporal.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_login_failed_at_threshold_starts_lock_and_security_event(consumer, db_pool):
    _, conn = db_pool
    conn.fetchrow.return_value = {"cnt": 5}  # at threshold
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.auth_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        event = {"event_type": "USER_LOGIN_FAILED", "user_id": "u-2", "user_type": "employee", "tenant_id": "t-1"}
        await consumer._dispatch("USER_LOGIN_FAILED", event)
    consumer._temporal.start_workflow.assert_awaited_once()
    mock_kafka.security_event.assert_awaited_once()
    sec = mock_kafka.security_event.call_args[0][0]
    assert sec["event_type"] == "ACCOUNT_LOCKED"
    assert sec["user_id"] == "u-2"


@pytest.mark.asyncio
async def test_totp_failed_starts_lock_at_threshold(consumer, db_pool):
    _, conn = db_pool
    conn.fetchrow.return_value = {"cnt": 5}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.auth_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        event = {"event_type": "TOTP_FAILED", "user_id": "u-3", "user_type": "employee", "tenant_id": "t-1"}
        await consumer._dispatch("TOTP_FAILED", event)
    consumer._temporal.start_workflow.assert_awaited_once()
    assert consumer._temporal.start_workflow.call_args[1]["id"] == "account-lock-u-3"


@pytest.mark.asyncio
async def test_security_event_payload_has_correct_reason(consumer, db_pool):
    _, conn = db_pool
    conn.fetchrow.return_value = {"cnt": 5}
    mock_kafka = AsyncMock()
    with patch("kafka.consumers.auth_consumer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        event = {"event_type": "TOTP_FAILED", "user_id": "u-4", "user_type": "employee", "tenant_id": "t-1"}
        await consumer._dispatch("TOTP_FAILED", event)
    sec = mock_kafka.security_event.call_args[0][0]
    assert "TOTP" in sec["reason"]
