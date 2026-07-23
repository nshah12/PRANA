"""Tests for workflows/vault_shares.py — share token lifecycle workflows."""
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workflows.vault_shares import (
    ShareExpiryWorkflow,
    ShareRevocationWorkflow,
    DocumentShareWorkflow,
    expire_share_token,
    revoke_share_token,
    create_share_token,
    send_share_otp,
    notify_share_accessed,
    get_share_config,
)


def test_share_expiry_workflow_uses_durable_timer():
    src = inspect.getsource(ShareExpiryWorkflow.run)
    assert "workflow.sleep" in src, \
        "ShareExpiryWorkflow must use workflow.sleep (durable timer, not asyncio.sleep)"
    assert "asyncio.sleep" not in src, \
        "Must use workflow.sleep not asyncio.sleep — durable across restarts"


def test_share_revocation_signal_cancels_expiry_timer():
    src = inspect.getsource(ShareRevocationWorkflow.run)
    assert "revoke_share_token" in src, \
        "ShareRevocationWorkflow must call revoke_share_token activity"
    assert "execute_activity" in src, \
        "Must use execute_activity for durable revocation"


def test_share_ttl_from_platform_config_not_hardcoded():
    src = inspect.getsource(DocumentShareWorkflow.run)
    assert "get_share_config" in src, \
        "DocumentShareWorkflow must read TTL from get_share_config activity"
    assert "share_otp_ttl_minutes" in src, \
        "TTL key must be share_otp_ttl_minutes from platform_config"


# ── Activity implementations — real bodies, previously bare stubs ────────────

@pytest.mark.asyncio
async def test_expire_share_token_delegates_to_share_service():
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("services.share_service.ShareService.mark_expired",
               new_callable=AsyncMock) as mock_expire:
        await expire_share_token({"share_id": "share-1"})
    mock_expire.assert_awaited_once_with("share-1")


@pytest.mark.asyncio
async def test_revoke_share_token_delegates_to_share_service():
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("services.share_service.ShareService.revoke_by_id",
               new_callable=AsyncMock) as mock_revoke:
        await revoke_share_token({"share_id": "share-1"})
    mock_revoke.assert_awaited_once_with("share-1")


@pytest.mark.asyncio
async def test_create_share_token_delegates_to_share_service():
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("services.share_service.ShareService.create",
               new_callable=AsyncMock, return_value={"share_id": "s-1", "share_token": "tok"}) as mock_create:
        result = await create_share_token({
            "employee_user_id": "emp-1", "document_ids": ["d-1"],
            "expires_hours": 24, "max_views": 1, "otp_required": True,
            "recipient_email": "r@example.com",
        })
    assert result == {"share_id": "s-1", "share_token": "tok"}
    mock_create.assert_awaited_once_with(
        employee_user_id="emp-1", document_ids=["d-1"], expires_hours=24,
        max_views=1, recipient_label=None, otp_required=True,
        recipient_email="r@example.com",
    )


@pytest.mark.asyncio
async def test_send_share_otp_dispatches_via_sms_service():
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("redis.asyncio.from_url", return_value=fake_redis), \
         patch("services.sms_service.SMSService.send_otp", new_callable=AsyncMock) as mock_send:
        await send_share_otp({"recipient_mobile": "+919000000001", "otp": "123456", "tenant_id": "t-1"})
    mock_send.assert_awaited_once_with("+919000000001", "123456", tenant_id="t-1")


@pytest.mark.asyncio
async def test_send_share_otp_noop_without_mobile_or_otp():
    with patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect, \
         patch("services.sms_service.SMSService.send_otp", new_callable=AsyncMock) as mock_send:
        await send_share_otp({"otp": "123456"})
    mock_send.assert_not_awaited()
    mock_connect.assert_not_awaited()   # early-return must skip DB/Redis connect entirely


@pytest.mark.asyncio
async def test_notify_share_accessed_publishes_to_notifications_topic():
    mock_kafka = AsyncMock()
    with patch("kafka.producer.get_kafka_producer", new_callable=AsyncMock, return_value=mock_kafka):
        await notify_share_accessed({"employee_user_id": "emp-1", "tenant_id": "t-1"})
    mock_kafka.publish.assert_awaited_once()
    topic, event = mock_kafka.publish.call_args.args
    assert topic == "prana.notifications"
    assert event["event_type"] == "SHARE_ACCESSED"
    assert event["employee_user_id"] == "emp-1"
    assert mock_kafka.publish.call_args.kwargs["key"] == "emp-1"


@pytest.mark.asyncio
async def test_get_share_config_returns_resolved_value():
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("redis.asyncio.from_url", return_value=fake_redis), \
         patch("services.config_service.ConfigService.get", new_callable=AsyncMock, return_value="15"):
        result = await get_share_config({"key": "share_otp_ttl_minutes", "default": "10"})
    assert result == "15"


@pytest.mark.asyncio
async def test_get_share_config_falls_back_to_default():
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    with patch("asyncpg.connect", new_callable=AsyncMock), \
         patch("redis.asyncio.from_url", return_value=fake_redis), \
         patch("services.config_service.ConfigService.get", new_callable=AsyncMock, return_value=None):
        result = await get_share_config({"key": "share_otp_ttl_minutes", "default": "10"})
    assert result == "10"
