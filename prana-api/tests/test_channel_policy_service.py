"""Tests for services/channel_policy_service.py (new).

Resolves which channel(s) a NotificationTemplate should go out on —
notification_channel_policy, tenant override with platform-default fallback
(prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §3).
"""
from unittest.mock import AsyncMock

import pytest

from services.channel_policy_service import ChannelPolicyService


@pytest.mark.asyncio
async def test_resolve_tenant_override_takes_precedence():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"channels": ["email", "sms"]})
    svc = ChannelPolicyService(db)

    channels = await svc.resolve("VAULT_WELCOME", tenant_id="tenant-001")
    assert channels == ["email", "sms"]
    sql, *args = db.fetchrow.call_args[0]
    assert "tenant_id = $2" in sql or "tenant_id=$2" in sql.replace(" ", "")
    assert args == ["VAULT_WELCOME", "tenant-001"]


@pytest.mark.asyncio
async def test_resolve_falls_back_to_platform_default_when_no_tenant_row():
    db = AsyncMock()
    db.fetchrow = AsyncMock(side_effect=[None, {"channels": ["portal_bell"]}])
    svc = ChannelPolicyService(db)

    channels = await svc.resolve("ANOMALY_P2_ALERT", tenant_id="tenant-001")
    assert channels == ["portal_bell"]
    assert db.fetchrow.call_count == 2


@pytest.mark.asyncio
async def test_resolve_platform_only_when_no_tenant_id():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"channels": ["email"]})
    svc = ChannelPolicyService(db)

    channels = await svc.resolve("OA_WELCOME", tenant_id=None)
    assert channels == ["email"]
    db.fetchrow.assert_called_once()   # no tenant lookup attempted at all


@pytest.mark.asyncio
async def test_resolve_returns_empty_list_when_nothing_seeded():
    """Defensive fallback — every real template has a seeded platform row, but
    an unrecognized template_id must not crash the Hub, just deliver nothing."""
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=None)
    svc = ChannelPolicyService(db)

    channels = await svc.resolve("SOME_UNSEEDED_TEMPLATE", tenant_id=None)
    assert channels == []
