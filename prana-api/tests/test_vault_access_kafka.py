"""
Tests for vault access log migration to Kafka.

Verifies:
  1. VaultService._log_access publishes DOC_ACCESSED to prana.vault.events (not DB)
  2. Falls back to DB if Kafka is unavailable
  3. AuditConsumer._write_access_log writes document_access_log correctly
  4. AuditConsumer subscribes to prana.vault.events
  5. No raw salary or PAN in the published event
"""
import inspect
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── VaultService._log_access publishes to Kafka ───────────────────────────────

@pytest.mark.asyncio
async def test_log_access_publishes_to_vault_topic():
    from services.vault_service import VaultService, TOPIC_VAULT

    mock_db    = AsyncMock()
    mock_kafka = AsyncMock()

    svc = VaultService(db=mock_db, kms=MagicMock(), s3_client=MagicMock(),
                       documents_bucket="bucket", kafka_producer=mock_kafka)

    await svc._log_access(
        document_id="doc-001", employee_user_id="emp-001",
        employee_uuid="uuid-001", tenant_id="t-001",
        actor_type="EMPLOYEE", actor_id="emp-001",
        access_type="VIEW", access_channel="MOBILE",
        ip_address="1.2.3.4", session_id="sess-001",
    )

    mock_kafka.doc_accessed.assert_called_once()
    event = mock_kafka.doc_accessed.call_args[0][0]
    assert event["event_type"] == "DOC_ACCESSED"
    assert event["document_id"] == "doc-001"
    assert event["watermark_applied"] is True


@pytest.mark.asyncio
async def test_log_access_does_not_write_db_when_kafka_available():
    from services.vault_service import VaultService

    mock_db    = AsyncMock()
    mock_kafka = AsyncMock()

    svc = VaultService(db=mock_db, kms=MagicMock(), s3_client=MagicMock(),
                       documents_bucket="bucket", kafka_producer=mock_kafka)

    await svc._log_access(
        document_id="doc-001", employee_user_id="emp-001",
        employee_uuid="uuid-001", tenant_id="t-001",
        actor_type="EMPLOYEE", actor_id="emp-001",
        access_type="VIEW", access_channel="MOBILE",
        ip_address="1.2.3.4", session_id="sess-001",
    )

    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_log_access_falls_back_to_db_when_kafka_fails():
    from services.vault_service import VaultService

    mock_db    = AsyncMock()
    mock_kafka = AsyncMock()
    mock_kafka.doc_accessed = AsyncMock(side_effect=Exception("Kafka down"))

    svc = VaultService(db=mock_db, kms=MagicMock(), s3_client=MagicMock(),
                       documents_bucket="bucket", kafka_producer=mock_kafka)

    await svc._log_access(
        document_id="doc-001", employee_user_id="emp-001",
        employee_uuid="uuid-001", tenant_id="t-001",
        actor_type="EMPLOYEE", actor_id="emp-001",
        access_type="VIEW", access_channel="MOBILE",
        ip_address="1.2.3.4", session_id="sess-001",
    )

    # Fallback DB write must have happened
    mock_db.execute.assert_called_once()
    sql = mock_db.execute.call_args[0][0]
    assert "document_access_log" in sql


@pytest.mark.asyncio
async def test_log_access_falls_back_to_db_when_no_kafka():
    """No kafka_producer injected (dev mode) → direct DB write."""
    from services.vault_service import VaultService

    mock_db = AsyncMock()

    svc = VaultService(db=mock_db, kms=MagicMock(), s3_client=MagicMock(),
                       documents_bucket="bucket", kafka_producer=None)

    await svc._log_access(
        document_id="doc-001", employee_user_id="emp-001",
        employee_uuid="uuid-001", tenant_id="t-001",
        actor_type="EMPLOYEE", actor_id="emp-001",
        access_type="VIEW", access_channel="MOBILE",
        ip_address="1.2.3.4", session_id="sess-001",
    )

    mock_db.execute.assert_called_once()


def test_log_access_event_contains_no_raw_salary_or_pan():
    """DOC_ACCESSED event must never carry raw salary figures or PAN."""
    src = inspect.getsource(__import__("services.vault_service", fromlist=["VaultService"]).VaultService._log_access)
    assert "salary" not in src.lower()
    assert "gross" not in src.lower()
    assert "pan_number" not in src


# ── AuditConsumer subscribes to vault topic ───────────────────────────────────

def test_audit_consumer_subscribes_to_vault_events():
    src = inspect.getsource(__import__("kafka.consumers.audit_consumer",
                                       fromlist=["AuditConsumer"]).AuditConsumer.__init__)
    assert "prana.vault.events" in src, \
        "AuditConsumer must subscribe to prana.vault.events to write document_access_log"


# ── AuditConsumer._write_access_log ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_write_access_log_inserts_correct_columns():
    from kafka.consumers.audit_consumer import AuditConsumer
    from unittest.mock import patch, AsyncMock, MagicMock

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("kafka.consumers.audit_consumer.AIOKafkaConsumer"):
        from config import Settings
        settings = MagicMock(spec=Settings)
        settings.kafka_bootstrap_servers = "localhost:9092"
        consumer = AuditConsumer(settings, mock_pool)

    event = {
        "event_type":        "DOC_ACCESSED",
        "document_id":       "doc-001",
        "employee_user_id":  "emp-001",
        "employee_uuid":     "uuid-001",
        "tenant_id":         "t-001",
        "actor_type":        "EMPLOYEE",
        "actor_id":          "emp-001",
        "access_type":       "VIEW",
        "access_channel":    "MOBILE",
        "ip_address":        "1.2.3.4",
        "session_id":        "sess-001",
        "watermark_applied": True,
    }

    await consumer._write_access_log(event)

    mock_conn.execute.assert_called_once()
    sql = mock_conn.execute.call_args[0][0]
    assert "document_access_log" in sql
    assert "watermark_applied" in sql


# ── Producer vault helper ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_producer_doc_accessed_publishes_to_vault_and_audit():
    from kafka.producer import KafkaPub, TOPIC_VAULT, TOPIC_AUDIT

    with patch("kafka.producer.AIOKafkaProducer"):
        from config import Settings
        settings = MagicMock(spec=Settings)
        settings.kafka_bootstrap_servers = "localhost:9092"
        pub = KafkaPub(settings)
        pub.publish = AsyncMock()

    event = {"event_type": "DOC_ACCESSED", "document_id": "d1",
             "employee_uuid": "u1", "tenant_id": "t1"}
    await pub.doc_accessed(event)

    topics = {call.args[0] for call in pub.publish.call_args_list}
    assert TOPIC_VAULT in topics
    assert TOPIC_AUDIT in topics
