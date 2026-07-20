"""Tests for services/audit_integrity_service.py.

Re-verifies recent audit_event rows against their Immudb dual-write to catch
tampering applied directly against YugabyteDB. See KAFKA_REDIS_ARCHITECTURE.md §8.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.audit_integrity_service import AuditIntegrityService

EVENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ACTOR_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
TENANT_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _row(**over):
    base = {
        "event_id": EVENT_ID,
        "event_type": "EMPLOYEE_PASSWORD_RESET",
        "actor_type": "OA_ADMIN",
        "actor_id": ACTOR_ID,
        "tenant_id": TENANT_ID,
        "document_id": None,
        "event_metadata": {"reason": "lost device"},
        "occurred_at": "2026-07-15T10:00:00+00:00",
    }
    base.update(over)
    return base


def _immudb_value(**over):
    base = {
        "event_id": str(EVENT_ID),
        "event_type": "EMPLOYEE_PASSWORD_RESET",
        "actor_type": "OA_ADMIN",
        "actor_id": str(ACTOR_ID),
        "tenant_id": str(TENANT_ID),
        "document_id": None,
        "ip_address": None,
        "event_metadata": {"reason": "lost device"},
        "occurred_at": None,   # producer didn't set it — legitimate, not tampering
    }
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_verify_recent_reports_no_mismatch_when_immudb_matches():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[_row()])
    immudb = MagicMock()
    immudb.verified_get = MagicMock(return_value={"value": _immudb_value(), "verified": True})
    kafka = AsyncMock()

    svc = AuditIntegrityService(db, immudb, kafka)
    result = await svc.verify_recent(limit=500)

    assert result == {"checked": 1, "mismatched": [], "missing": [], "unverified": []}
    kafka.security_event.assert_not_called()


@pytest.mark.asyncio
async def test_verify_recent_flags_mismatch_when_db_row_was_altered():
    db = AsyncMock()
    # DB row's actor_type has been changed since it was written — tampering.
    db.fetch = AsyncMock(return_value=[_row(actor_type="PA")])
    immudb = MagicMock()
    immudb.verified_get = MagicMock(return_value={"value": _immudb_value(), "verified": True})
    kafka = AsyncMock()

    svc = AuditIntegrityService(db, immudb, kafka)
    result = await svc.verify_recent()

    assert result["mismatched"] == [str(EVENT_ID)]
    kafka.security_event.assert_awaited_once()
    published = kafka.security_event.call_args.args[0]
    assert published["event_type"] == "AUDIT_INTEGRITY_MISMATCH"
    assert published["mismatched_count"] == 1


@pytest.mark.asyncio
async def test_verify_recent_flags_missing_without_alerting():
    """Missing = Immudb was down at write time (resilience gap), not proven
    tampering — worth surfacing in the return value but not worth paging."""
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[_row()])
    immudb = MagicMock()
    immudb.verified_get = MagicMock(return_value=None)
    kafka = AsyncMock()

    svc = AuditIntegrityService(db, immudb, kafka)
    result = await svc.verify_recent()

    assert result["missing"] == [str(EVENT_ID)]
    assert result["mismatched"] == []
    kafka.security_event.assert_not_called()


@pytest.mark.asyncio
async def test_verify_recent_flags_unverified_when_immudb_proof_fails():
    """verified=False means Immudb's own cryptographic proof failed — the most
    alarming case, must alert."""
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[_row()])
    immudb = MagicMock()
    immudb.verified_get = MagicMock(return_value={"value": _immudb_value(), "verified": False})
    kafka = AsyncMock()

    svc = AuditIntegrityService(db, immudb, kafka)
    result = await svc.verify_recent()

    assert result["unverified"] == [str(EVENT_ID)]
    kafka.security_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_recent_treats_immudb_exception_as_unverified():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[_row()])
    immudb = MagicMock()
    immudb.verified_get = MagicMock(side_effect=RuntimeError("immudb down"))
    kafka = AsyncMock()

    svc = AuditIntegrityService(db, immudb, kafka)
    result = await svc.verify_recent()

    assert result["unverified"] == [str(EVENT_ID)]


@pytest.mark.asyncio
async def test_verify_recent_ignores_occurred_at_and_ip_differences():
    """Immudb stores the raw Kafka event's occurred_at/ip_address, which can
    legitimately be None while the DB row has a server-generated value —
    must not be flagged as a mismatch."""
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[_row(occurred_at="2026-07-15T11:30:00+00:00")])
    immudb = MagicMock()
    immudb.verified_get = MagicMock(
        return_value={"value": _immudb_value(occurred_at=None, ip_address=None), "verified": True}
    )
    kafka = AsyncMock()

    svc = AuditIntegrityService(db, immudb, kafka)
    result = await svc.verify_recent()

    assert result["mismatched"] == []


@pytest.mark.asyncio
async def test_verify_recent_flags_mismatch_on_metadata_tamper():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[_row(event_metadata={"reason": "TAMPERED"})])
    immudb = MagicMock()
    immudb.verified_get = MagicMock(return_value={"value": _immudb_value(), "verified": True})
    kafka = AsyncMock()

    svc = AuditIntegrityService(db, immudb, kafka)
    result = await svc.verify_recent()

    assert result["mismatched"] == [str(EVENT_ID)]


@pytest.mark.asyncio
async def test_verify_recent_parses_jsonb_metadata_returned_as_string():
    """asyncpg returns JSONB columns as raw JSON text by default — must be
    parsed before comparison, not compared as a string against a dict."""
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[_row(event_metadata='{"reason": "lost device"}')])
    immudb = MagicMock()
    immudb.verified_get = MagicMock(return_value={"value": _immudb_value(), "verified": True})
    kafka = AsyncMock()

    svc = AuditIntegrityService(db, immudb, kafka)
    result = await svc.verify_recent()

    assert result["mismatched"] == []


@pytest.mark.asyncio
async def test_verify_recent_empty_table_returns_zero_counts():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    immudb = MagicMock()
    kafka = AsyncMock()

    svc = AuditIntegrityService(db, immudb, kafka)
    result = await svc.verify_recent()

    assert result == {"checked": 0, "mismatched": [], "missing": [], "unverified": []}
    immudb.verified_get.assert_not_called()


@pytest.mark.asyncio
async def test_verify_recent_works_without_kafka():
    """kafka=None must not crash even when there's a mismatch to report."""
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[_row(actor_type="PA")])
    immudb = MagicMock()
    immudb.verified_get = MagicMock(return_value={"value": _immudb_value(), "verified": True})

    svc = AuditIntegrityService(db, immudb, kafka=None)
    result = await svc.verify_recent()

    assert result["mismatched"] == [str(EVENT_ID)]


@pytest.mark.asyncio
async def test_verify_recent_passes_limit_through_to_query():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    immudb = MagicMock()

    svc = AuditIntegrityService(db, immudb, kafka=None)
    await svc.verify_recent(limit=250)

    args = db.fetch.call_args.args
    assert 250 in args
