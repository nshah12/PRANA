"""Tests for workflows/hrms_sync.py — run_hrms_pull activity."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_run_hrms_pull_uses_real_kafka_producer_not_nonexistent_class():
    """Regression guard: this used to do `from kafka.producer import
    KafkaProducer` and `KafkaProducer(bootstrap_servers=...)` — no such class
    exists in kafka/producer.py (that's aiokafka's raw constructor signature,
    not this project's KafkaPub wrapper). AttributeError the instant this
    activity ran for real; no test previously called it end-to-end. The real
    producer is obtained via get_kafka_producer(), and hrms_sync_service.py's
    run_pull_sync calls kafka.employee_event(...) — a KafkaPub method — so it
    must actually receive a KafkaPub instance, not a bare aiokafka producer."""
    import os

    from workflows.hrms_sync import run_hrms_pull

    fake_kafka = AsyncMock()
    mock_conn = AsyncMock()
    mock_conn.close = AsyncMock()

    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://x", "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092"}), \
         patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn), \
         patch("boto3.client", return_value=MagicMock()), \
         patch("kafka.producer.get_kafka_producer", new_callable=AsyncMock, return_value=fake_kafka) as mock_get_kafka, \
         patch("services.hrms_sync_service.HRMSSyncService.run_pull_sync", new_callable=AsyncMock,
               return_value={"records_pulled": 0}) as mock_pull:
        result = await run_hrms_pull(str(uuid.uuid4()), str(uuid.uuid4()))

    mock_get_kafka.assert_awaited_once()
    assert mock_pull.call_args.kwargs["kafka"] is fake_kafka
    assert result == {"records_pulled": 0}


@pytest.mark.asyncio
async def test_run_hrms_pull_temporal_run_id_defaults_to_none_outside_activity_context():
    """Regression guard: this used to call `workflow.info().run_id if
    workflow.in_workflow() else None` — temporalio.workflow has no
    in_workflow() function at all, so this raised AttributeError on every
    single call, real activity context or not. The real API for an ACTIVITY
    (not workflow code) to get its run id is activity.info().workflow_run_id,
    which raises RuntimeError outside an activity context — caught here and
    treated the same way the original code intended None to mean."""
    import os

    from workflows.hrms_sync import run_hrms_pull

    mock_conn = AsyncMock()
    mock_conn.close = AsyncMock()

    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://x", "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092"}), \
         patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn), \
         patch("boto3.client", return_value=MagicMock()), \
         patch("kafka.producer.get_kafka_producer", new_callable=AsyncMock, return_value=AsyncMock()), \
         patch("services.hrms_sync_service.HRMSSyncService.run_pull_sync", new_callable=AsyncMock,
               return_value={}) as mock_pull:
        await run_hrms_pull(str(uuid.uuid4()), str(uuid.uuid4()))

    assert mock_pull.call_args.kwargs["temporal_run_id"] is None
