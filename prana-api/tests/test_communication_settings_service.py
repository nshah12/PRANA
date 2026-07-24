"""Tests for services/communication_settings_service.py (new).

Backs the PA + OA-Admin Communication Settings screens
(prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §8): channel policy (per
NotificationTemplate) and vendor chains (per channel), tenant override with
platform-default fallback — same resolution order as everywhere else in
this codebase. Every write publishes an Immudb-audited tenant_event() (§9).
"""
from unittest.mock import AsyncMock, patch

import pytest

from services.communication_settings_service import CommunicationSettingsService


def _db():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    db.execute = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Channel policy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_channel_policy_returns_all_notification_templates():
    db = _db()
    db.fetch = AsyncMock(side_effect=[
        [{"template_id": "OA_WELCOME", "channels": ["email"]}],  # platform rows
    ])
    svc = CommunicationSettingsService(db)
    items = await svc.get_channel_policy(tenant_id=None)

    from messages import NotificationTemplate
    assert len(items) == len(NotificationTemplate)
    oa_welcome = next(i for i in items if i["template_id"] == "OA_WELCOME")
    assert oa_welcome["channels"] == ["email"]
    assert oa_welcome["is_tenant_override"] is False


@pytest.mark.asyncio
async def test_get_channel_policy_marks_tenant_override():
    db = _db()
    db.fetch = AsyncMock(side_effect=[
        [{"template_id": "VAULT_WELCOME", "channels": ["sms", "email"]}],   # platform
        [{"template_id": "VAULT_WELCOME", "channels": ["email"]}],          # tenant override
    ])
    svc = CommunicationSettingsService(db)
    items = await svc.get_channel_policy(tenant_id="tenant-001")

    row = next(i for i in items if i["template_id"] == "VAULT_WELCOME")
    assert row["channels"] == ["email"]              # tenant override wins
    assert row["platform_channels"] == ["sms", "email"]
    assert row["is_tenant_override"] is True


@pytest.mark.asyncio
async def test_update_channel_policy_rejects_unknown_template():
    svc = CommunicationSettingsService(_db())
    with pytest.raises(ValueError, match="UNKNOWN_TEMPLATE_ID"):
        await svc.update_channel_policy(
            template_id="NOT_A_REAL_TEMPLATE", channels=["email"],
            tenant_id=None, updated_by="pa-1",
        )


@pytest.mark.asyncio
async def test_update_channel_policy_rejects_invalid_channel():
    svc = CommunicationSettingsService(_db())
    with pytest.raises(ValueError, match="INVALID_CHANNELS"):
        await svc.update_channel_policy(
            template_id="OA_WELCOME", channels=["carrier_pigeon"],
            tenant_id=None, updated_by="pa-1",
        )


@pytest.mark.asyncio
async def test_update_channel_policy_rejects_empty_channels():
    svc = CommunicationSettingsService(_db())
    with pytest.raises(ValueError, match="AT_LEAST_ONE_CHANNEL"):
        await svc.update_channel_policy(
            template_id="OA_WELCOME", channels=[],
            tenant_id=None, updated_by="pa-1",
        )


@pytest.mark.asyncio
async def test_update_channel_policy_platform_upserts_null_tenant_row():
    db = _db()
    mock_kafka = AsyncMock()
    with patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        svc = CommunicationSettingsService(db)
        result = await svc.update_channel_policy(
            template_id="OA_WELCOME", channels=["email", "portal_bell"],
            tenant_id=None, updated_by="pa-1",
        )
    db.execute.assert_awaited_once()
    sql, *args = db.execute.call_args[0]
    assert "tenant_id IS NULL" in sql
    assert result["channels"] == ["email", "portal_bell"]


@pytest.mark.asyncio
async def test_update_channel_policy_tenant_upserts_tenant_row():
    db = _db()
    mock_kafka = AsyncMock()
    with patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        svc = CommunicationSettingsService(db)
        await svc.update_channel_policy(
            template_id="OA_WELCOME", channels=["email"],
            tenant_id="tenant-001", updated_by="oa-1",
        )
    sql, *args = db.execute.call_args[0]
    assert "tenant_id IS NOT NULL" in sql
    assert "tenant-001" in args


@pytest.mark.asyncio
async def test_update_channel_policy_publishes_immudb_audited_tenant_event():
    db = _db()
    db.fetchrow = AsyncMock(return_value={"channels": ["email"]})
    mock_kafka = AsyncMock()
    with patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        svc = CommunicationSettingsService(db)
        await svc.update_channel_policy(
            template_id="OA_WELCOME", channels=["email", "portal_bell"],
            tenant_id=None, updated_by="pa-1",
        )
    mock_kafka.tenant_event.assert_awaited_once()
    event = mock_kafka.tenant_event.call_args.args[0]
    assert event["event_type"] == "COMM_CHANNEL_POLICY_UPDATED"
    assert event["template_id"] == "OA_WELCOME"
    assert event["old_channels"] == ["email"]
    assert event["new_channels"] == ["email", "portal_bell"]
    assert event["actor_id"] == "pa-1"


# ---------------------------------------------------------------------------
# Vendor chains
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_vendor_chains_resolves_all_four_channels():
    db = _db()

    async def _fetchval(sql, *args):
        if "tenant_config" in sql:
            return None
        key = args[0] if args else None
        return {
            "email_vendor_chain":    '["ses"]',
            "sms_vendor_chain":      '["aws","exotel","msg91"]',
            "whatsapp_vendor_chain": '["waba"]',
            "ivr_vendor_chain":      '["exotel","ozonetel"]',
        }.get(key)

    db.fetchval = AsyncMock(side_effect=_fetchval)
    svc = CommunicationSettingsService(db)
    chains = await svc.get_vendor_chains(tenant_id=None)

    assert chains["email"]["chain"] == ["ses"]
    assert chains["sms"]["chain"] == ["aws", "exotel", "msg91"]
    assert chains["whatsapp"]["chain"] == ["waba"]
    assert chains["ivr"]["chain"] == ["exotel", "ozonetel"]


@pytest.mark.asyncio
async def test_update_vendor_chain_rejects_unknown_channel():
    svc = CommunicationSettingsService(_db())
    with pytest.raises(ValueError, match="UNKNOWN_CHANNEL"):
        await svc.update_vendor_chain(
            channel="carrier_pigeon", vendors=["x"], tenant_id=None, updated_by="pa-1",
        )


@pytest.mark.asyncio
async def test_update_vendor_chain_rejects_unknown_vendor_for_channel():
    svc = CommunicationSettingsService(_db())
    with pytest.raises(ValueError, match="INVALID_VENDORS"):
        await svc.update_vendor_chain(
            channel="sms", vendors=["carrier_pigeon"], tenant_id=None, updated_by="pa-1",
        )


@pytest.mark.asyncio
async def test_update_vendor_chain_tenant_cannot_exceed_platform_chain():
    """OA-Admin can only choose among vendors PA already enabled platform-wide —
    the ceiling described in COMMUNICATION_HUB_ARCHITECTURE.md §8.2."""
    db = _db()
    db.fetchval = AsyncMock(return_value='["aws"]')   # platform only enabled aws
    svc = CommunicationSettingsService(db)
    with pytest.raises(ValueError, match="VENDOR_NOT_ENABLED_BY_PLATFORM"):
        await svc.update_vendor_chain(
            channel="sms", vendors=["msg91"], tenant_id="tenant-001", updated_by="oa-1",
        )


@pytest.mark.asyncio
async def test_update_vendor_chain_platform_writes_platform_config():
    db = _db()
    mock_kafka = AsyncMock()
    with patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        svc = CommunicationSettingsService(db)
        await svc.update_vendor_chain(
            channel="sms", vendors=["msg91", "aws"], tenant_id=None, updated_by="pa-1",
        )
    sql, *args = db.execute.call_args[0]
    assert "platform_config" in sql
    assert '["msg91", "aws"]' in args or ["msg91", "aws"] in args or any(
        "msg91" in str(a) for a in args
    )


@pytest.mark.asyncio
async def test_update_vendor_chain_tenant_writes_tenant_config():
    db = _db()
    db.fetchval = AsyncMock(return_value='["aws", "msg91"]')
    mock_kafka = AsyncMock()
    with patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        svc = CommunicationSettingsService(db)
        await svc.update_vendor_chain(
            channel="sms", vendors=["msg91"], tenant_id="tenant-001", updated_by="oa-1",
        )
    sql, *args = db.execute.call_args[0]
    assert "tenant_config" in sql
    assert "tenant-001" in args


@pytest.mark.asyncio
async def test_update_vendor_chain_publishes_immudb_audited_tenant_event():
    db = _db()
    mock_kafka = AsyncMock()
    with patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        svc = CommunicationSettingsService(db)
        await svc.update_vendor_chain(
            channel="email", vendors=["smtp", "ses"], tenant_id=None, updated_by="pa-1",
        )
    mock_kafka.tenant_event.assert_awaited_once()
    event = mock_kafka.tenant_event.call_args.args[0]
    assert event["event_type"] == "COMM_VENDOR_CHAIN_UPDATED"
    assert event["channel"] == "email"
    assert event["new_chain"] == ["smtp", "ses"]
    assert event["actor_id"] == "pa-1"


# ---------------------------------------------------------------------------
# Vendor credential status (PA only, read-only — never exposes secret values)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vendor_credential_status_never_includes_secret_values():
    from config import Settings
    settings = Settings(
        app_env="test", db_host="localhost", db_port=5433,
        platform_hmac_secret="test_secret_32chars_padding_pad1",
        kafka_bootstrap_servers="localhost:9092", redis_url="redis://localhost:6379/15",
        exotel_sid="SID1", exotel_api_key="super-secret-key",
        msg91_auth_key="another-secret",
    )
    svc = CommunicationSettingsService(_db())
    status = svc.get_vendor_credential_status(settings)

    dumped = str(status)
    assert "super-secret-key" not in dumped
    assert "another-secret" not in dumped
    assert status["exotel"]["configured"] is True
    assert status["msg91"]["configured"] is True


@pytest.mark.asyncio
async def test_vendor_credential_status_reports_unconfigured_vendor():
    from config import Settings
    settings = Settings(
        app_env="test", db_host="localhost", db_port=5433,
        platform_hmac_secret="test_secret_32chars_padding_pad1",
        kafka_bootstrap_servers="localhost:9092", redis_url="redis://localhost:6379/15",
    )
    svc = CommunicationSettingsService(_db())
    status = svc.get_vendor_credential_status(settings)
    assert status["msg91"]["configured"] is False
    assert status["ozonetel"]["configured"] is False
