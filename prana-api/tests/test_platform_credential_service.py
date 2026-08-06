"""Tests for services/platform_credential_service.py.

Generalizes the platform_vendor_credential pattern already proven by
CommunicationSettingsService's vendor-credential methods (KMS-encrypted,
Immudb-audited via tenant_event()) to non-communication paid services —
currently just Qdrant (prana-ask's vector store). Same table, same
encryption model, same audit event shape, different — smaller — field map.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.platform_credential_service import PlatformCredentialService


def _db():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    db.execute = AsyncMock()
    return db


def _settings(**overrides):
    from config import Settings
    defaults = dict(
        app_env="test", db_host="localhost", db_port=5433,
        platform_hmac_secret="test_secret_32chars_padding_pad1",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _kms():
    kms = MagicMock()
    kms.encrypt_value = MagicMock(return_value="kms-ciphertext-blob")
    return kms


@pytest.mark.asyncio
async def test_get_status_reports_unconfigured_when_nothing_set():
    settings = _settings()
    svc = PlatformCredentialService(_db())
    status = await svc.get_status(settings)
    assert status["qdrant"]["configured"] is False
    assert status["qdrant"]["source"] == "none"


@pytest.mark.asyncio
async def test_get_status_source_is_env_when_env_set():
    settings = _settings(qdrant_api_key="env-key")
    svc = PlatformCredentialService(_db())
    status = await svc.get_status(settings)
    assert status["qdrant"]["configured"] is True
    assert status["qdrant"]["source"] == "env"


@pytest.mark.asyncio
async def test_get_status_reports_db_stored_credential_as_configured():
    settings = _settings()   # env empty
    db = _db()
    db.fetch = AsyncMock(return_value=[{"vendor": "qdrant", "field_name": "qdrant_api_key"}])
    svc = PlatformCredentialService(db)
    status = await svc.get_status(settings)
    assert status["qdrant"]["configured"] is True
    assert status["qdrant"]["source"] == "db"


@pytest.mark.asyncio
async def test_set_credential_rejects_unknown_vendor():
    svc = PlatformCredentialService(_db())
    with pytest.raises(ValueError, match="UNKNOWN_VENDOR"):
        await svc.set_credential(
            vendor="carrier_pigeon", field_name="x", value="y",
            updated_by="pa-1", kms=_kms(), kek_arn="arn:test",
        )


@pytest.mark.asyncio
async def test_set_credential_rejects_unknown_field_for_vendor():
    svc = PlatformCredentialService(_db())
    with pytest.raises(ValueError, match="UNKNOWN_FIELD"):
        await svc.set_credential(
            vendor="qdrant", field_name="not_a_real_field", value="y",
            updated_by="pa-1", kms=_kms(), kek_arn="arn:test",
        )


@pytest.mark.asyncio
async def test_set_credential_encrypts_before_storing():
    db = _db()
    kms = _kms()
    mock_kafka = AsyncMock()
    with patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        svc = PlatformCredentialService(db)
        await svc.set_credential(
            vendor="qdrant", field_name="qdrant_api_key", value="real-secret-value",
            updated_by="pa-1", kms=kms, kek_arn="arn:test",
        )

    kms.encrypt_value.assert_called_once_with("real-secret-value", "arn:test")
    db.execute.assert_awaited_once()
    sql, *args = db.execute.call_args[0]
    assert "platform_vendor_credential" in sql
    assert "kms-ciphertext-blob" in args
    assert "real-secret-value" not in args


@pytest.mark.asyncio
async def test_set_credential_publishes_immudb_audited_event_without_secret():
    db = _db()
    kms = _kms()
    mock_kafka = AsyncMock()
    with patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        svc = PlatformCredentialService(db)
        await svc.set_credential(
            vendor="qdrant", field_name="qdrant_url", value="https://real-cluster.qdrant.io",
            updated_by="pa-1", kms=kms, kek_arn="arn:test",
        )

    mock_kafka.tenant_event.assert_awaited_once()
    event = mock_kafka.tenant_event.call_args.args[0]
    assert event["event_type"] == "PLATFORM_CREDENTIAL_ROTATED"
    assert event["vendor"] == "qdrant"
    assert event["field_name"] == "qdrant_url"
    assert event["actor_id"] == "pa-1"
    assert "real-cluster" not in str(event)
