"""Tests for services/tenant_isolation_guard.py — CROSS_TENANT_QUERY detection.

Called from an HTTP handler AFTER an ownership-scoped lookup (WHERE id=$1 AND
tenant_id=$2) returns nothing. Distinguishes a genuine cross-tenant read attempt
(the resource exists, just under a DIFFERENT tenant) from a plain bad ID (the
resource doesn't exist anywhere) — only the former is worth flagging. Publishes
via Kafka only; never writes anomaly_event directly (this runs inside an HTTP
handler, which the HTTP handler contract forbids from doing audit-adjacent
writes — SecurityConsumer persists the row downstream).
"""
from unittest.mock import AsyncMock, patch

import pytest

from services.tenant_isolation_guard import TenantIsolationGuard


@pytest.mark.asyncio
async def test_document_belongs_to_different_tenant_publishes_anomaly():
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value="tenant-OTHER")
    guard = TenantIsolationGuard(db)

    with patch("kafka.producer.get_kafka_producer", new_callable=AsyncMock) as mock_get_kafka:
        mock_kafka = AsyncMock()
        mock_get_kafka.return_value = mock_kafka
        await guard.check_document_access(
            document_id="doc-1", requesting_tenant_id="tenant-A", actor_id="oa-1",
        )

    mock_kafka.security_event.assert_awaited_once()
    payload = mock_kafka.security_event.call_args[0][0]
    assert payload["event_type"] == "ANOMALY_DETECTED"
    assert payload["rule_name"] == "CROSS_TENANT_QUERY"
    assert payload["tenant_id"] == "tenant-A"
    assert payload["actor_id"] == "oa-1"
    assert payload["event_metadata"]["resource_type"] == "document"
    assert payload["event_metadata"]["resource_id"] == "doc-1"


@pytest.mark.asyncio
async def test_document_does_not_exist_anywhere_does_not_publish():
    """A plain bad/typo'd ID — no cross-tenant signal here, don't flag it."""
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=None)
    guard = TenantIsolationGuard(db)

    with patch("kafka.producer.get_kafka_producer", new_callable=AsyncMock) as mock_get_kafka:
        await guard.check_document_access(
            document_id="doc-nonexistent", requesting_tenant_id="tenant-A", actor_id="oa-1",
        )
        mock_get_kafka.assert_not_called()


@pytest.mark.asyncio
async def test_document_belongs_to_same_tenant_does_not_publish():
    """Defensive: if the resource actually IS in the requester's own tenant (a race
    between the failed lookup and this check, e.g. concurrent creation), don't flag."""
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value="tenant-A")
    guard = TenantIsolationGuard(db)

    with patch("kafka.producer.get_kafka_producer", new_callable=AsyncMock) as mock_get_kafka:
        await guard.check_document_access(
            document_id="doc-1", requesting_tenant_id="tenant-A", actor_id="oa-1",
        )
        mock_get_kafka.assert_not_called()


@pytest.mark.asyncio
async def test_employee_access_cross_tenant_publishes_anomaly():
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value="tenant-OTHER")
    guard = TenantIsolationGuard(db)

    with patch("kafka.producer.get_kafka_producer", new_callable=AsyncMock) as mock_get_kafka:
        mock_kafka = AsyncMock()
        mock_get_kafka.return_value = mock_kafka
        await guard.check_employee_access(
            employee_uuid="emp-1", requesting_tenant_id="tenant-A", actor_id="admin-1",
        )

    payload = mock_kafka.security_event.call_args[0][0]
    assert payload["rule_name"] == "CROSS_TENANT_QUERY"
    assert payload["event_metadata"]["resource_type"] == "employee_master"
    assert payload["event_metadata"]["resource_id"] == "emp-1"


@pytest.mark.asyncio
async def test_kafka_publish_failure_never_raises():
    """A guard failing to publish must never break the 404 response it's attached to."""
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value="tenant-OTHER")
    guard = TenantIsolationGuard(db)

    with patch("kafka.producer.get_kafka_producer", side_effect=RuntimeError("kafka down")):
        await guard.check_document_access(
            document_id="doc-1", requesting_tenant_id="tenant-A", actor_id="oa-1",
        )  # must not raise


@pytest.mark.asyncio
async def test_lookup_uses_literal_parameterized_sql_no_dynamic_table_names():
    """Regression guard: never build SQL with an f-string table name — each resource
    type gets its own hardcoded, parameterized query."""
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=None)
    guard = TenantIsolationGuard(db)
    await guard.check_document_access(document_id="doc-1", requesting_tenant_id="t-1", actor_id=None)
    sql = db.fetchval.call_args.args[0]
    assert "document" in sql
    assert "$1" in sql
    assert "{" not in sql
