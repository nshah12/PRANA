"""
RED tests for HRMSSyncService.

Verifies that the sync service:
- Loads connector config from DB
- Decrypts credentials via KMS
- Instantiates the correct adapter (Darwinbox vs Keka)
- Calls adapter.pull() and maps records to ingest events
- Publishes DOC_INGESTED via Kafka domain helper (not directly to topic)
- Logs sync start/complete to hrms_sync_log
- Never puts raw salary/CTC in Kafka events
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

TENANT_ID    = UUID("b0000000-0000-0000-0000-000000000001")
CONNECTOR_ID = UUID("e0000000-0000-0000-0000-000000000001")
SYNC_ID      = UUID("f0000000-0000-0000-0000-000000000001")

CONNECTOR_ROW = {
    "connector_id":            CONNECTOR_ID,
    "tenant_id":               TENANT_ID,
    "connector_definition_id": str(uuid4()),
    "connector_key":           "darwinbox",
    "integration_mode":        "PULL",
    "enc_credentials":         b"encrypted_blob",
    "kek_arn":                 "arn:aws:kms:ap-south-1:123:key/test",
    "field_mapping":           "{}",
    "pull_schedule":           None,
    "status":                  "ACTIVE",
    "last_pulled_at":          None,
}

SAMPLE_RECORDS = [
    {
        "employee_id":  "EMP001",
        "first_name":   "Rahul",
        "last_name":    "Sharma",
        "date_of_join": "2022-01-15",
        "designation":  "Software Engineer",
        "department":   "Engineering",
        "status":       "active",
    }
]


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.fetchrow  = AsyncMock(return_value=None)
    db.fetch     = AsyncMock(return_value=[])
    db.fetchval  = AsyncMock(return_value=None)
    db.execute   = AsyncMock()
    return db


@pytest.fixture
def mock_kms():
    kms = MagicMock()
    import json
    kms.decrypt = MagicMock(return_value=json.dumps(
        {"client_id": "x", "client_secret": "y", "base_url": "https://test.darwinbox.com"}
    ).encode())
    return kms


@pytest.fixture
def mock_kafka():
    kafka = AsyncMock()
    kafka.publish        = AsyncMock()
    kafka.employee_event = AsyncMock()
    return kafka


@pytest.fixture
def svc():
    from services.hrms_sync_service import HRMSSyncService
    return HRMSSyncService()


# ── load_connector ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_load_connector_config(svc, mock_db):
    """Service must load connector config from DB and return it."""
    row = MagicMock()
    row.__getitem__ = lambda s, k: CONNECTOR_ROW[k]
    row.get = lambda k, default=None: CONNECTOR_ROW.get(k, default)
    mock_db.fetchrow.return_value = row

    cfg = await svc.load_connector_config(
        connector_id=CONNECTOR_ID,
        tenant_id=TENANT_ID,
        db=mock_db,
    )
    assert cfg is not None
    mock_db.fetchrow.assert_awaited_once()
    # Query must be tenant-scoped
    call_sql = mock_db.fetchrow.call_args[0][0].lower()
    assert "tenant_id" in call_sql


@pytest.mark.asyncio
async def test_load_connector_config_not_found(svc, mock_db):
    mock_db.fetchrow.return_value = None
    cfg = await svc.load_connector_config(
        connector_id=CONNECTOR_ID, tenant_id=TENANT_ID, db=mock_db
    )
    assert cfg is None


# ── build_adapter ─────────────────────────────────────────────────────────────

def test_build_adapter_darwinbox(svc, mock_kms):
    from connectors.darwinbox import DarwinboxConnector
    import json
    config = {
        "connector_key":  "darwinbox",
        "enc_credentials": b"enc",
        "kek_arn":         "arn:aws:kms:ap-south-1:123:key/test",
        "field_mapping":   {},
    }
    mock_kms.decrypt.return_value = json.dumps(
        {"client_id": "x", "client_secret": "y", "base_url": "https://t.darwinbox.com"}
    ).encode()
    adapter = svc.build_adapter(config=config, kms=mock_kms)
    assert isinstance(adapter, DarwinboxConnector)


def test_build_adapter_keka(svc, mock_kms):
    from connectors.keka import KekaConnector
    import json
    config = {
        "connector_key":   "keka",
        "enc_credentials": b"enc",
        "kek_arn":         "arn:aws:kms:ap-south-1:123:key/test",
        "field_mapping":   {},
    }
    mock_kms.decrypt.return_value = json.dumps(
        {"api_key": "keka_key", "base_url": "https://t.keka.com"}
    ).encode()
    adapter = svc.build_adapter(config=config, kms=mock_kms)
    assert isinstance(adapter, KekaConnector)


def test_build_adapter_unknown_raises(svc, mock_kms):
    import json
    config = {
        "connector_key":   "unknown_hrms",
        "enc_credentials": b"enc",
        "kek_arn":         "arn",
        "field_mapping":   {},
    }
    mock_kms.decrypt.return_value = json.dumps({}).encode()
    with pytest.raises(ValueError, match="connector_key"):
        svc.build_adapter(config=config, kms=mock_kms)


# ── run_pull_sync ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_pull_sync_calls_kafka_for_each_record(svc, mock_db, mock_kms, mock_kafka):
    """Each employee record from pull() must result in a Kafka publish."""
    row = MagicMock()
    row.__getitem__ = lambda s, k: CONNECTOR_ROW[k]
    row.get = lambda k, default=None: CONNECTOR_ROW.get(k, default)
    mock_db.fetchrow.return_value = row
    mock_db.fetchval.return_value = SYNC_ID

    mock_adapter = AsyncMock()
    mock_adapter.pull = AsyncMock(return_value={
        "records":     SAMPLE_RECORDS,
        "next_cursor": None,
    })

    with patch.object(svc, "build_adapter", return_value=mock_adapter):
        result = await svc.run_pull_sync(
            connector_id=CONNECTOR_ID,
            tenant_id=TENANT_ID,
            db=mock_db,
            kms=mock_kms,
            kafka=mock_kafka,
        )

    assert result["docs_pushed"] == len(SAMPLE_RECORDS)
    assert mock_kafka.employee_event.await_count >= len(SAMPLE_RECORDS)


@pytest.mark.asyncio
async def test_run_pull_sync_no_salary_in_kafka_events(svc, mock_db, mock_kms, mock_kafka):
    """Privacy: no raw salary/CTC in any Kafka publish call."""
    row = MagicMock()
    row.__getitem__ = lambda s, k: CONNECTOR_ROW[k]
    row.get = lambda k, default=None: CONNECTOR_ROW.get(k, default)
    mock_db.fetchrow.return_value = row
    mock_db.fetchval.return_value = SYNC_ID

    records_with_salary = [{**SAMPLE_RECORDS[0], "ctc": "1200000", "salary": "100000"}]
    mock_adapter = AsyncMock()
    mock_adapter.pull = AsyncMock(return_value={"records": records_with_salary, "next_cursor": None})

    with patch.object(svc, "build_adapter", return_value=mock_adapter):
        await svc.run_pull_sync(
            connector_id=CONNECTOR_ID,
            tenant_id=TENANT_ID,
            db=mock_db,
            kms=mock_kms,
            kafka=mock_kafka,
        )

    for call in mock_kafka.employee_event.call_args_list:
        payload = str(call)
        assert "1200000" not in payload
        assert "ctc"     not in payload.lower()


@pytest.mark.asyncio
async def test_run_pull_sync_logs_start_and_complete(svc, mock_db, mock_kms, mock_kafka):
    """Sync log must record start and completion."""
    row = MagicMock()
    row.__getitem__ = lambda s, k: CONNECTOR_ROW[k]
    row.get = lambda k, default=None: CONNECTOR_ROW.get(k, default)
    mock_db.fetchrow.return_value = row
    mock_db.fetchval.return_value = SYNC_ID

    mock_adapter = AsyncMock()
    mock_adapter.pull = AsyncMock(return_value={"records": [], "next_cursor": None})

    with patch.object(svc, "build_adapter", return_value=mock_adapter):
        await svc.run_pull_sync(
            connector_id=CONNECTOR_ID,
            tenant_id=TENANT_ID,
            db=mock_db,
            kms=mock_kms,
            kafka=mock_kafka,
        )

    # fetchval for sync_id insert + execute for sync complete
    assert mock_db.execute.await_count >= 1


@pytest.mark.asyncio
async def test_run_pull_sync_skips_paused_connector(svc, mock_db, mock_kms, mock_kafka):
    """PAUSED connectors must not sync."""
    paused_row = MagicMock()
    paused_connector = {**CONNECTOR_ROW, "status": "PAUSED"}
    paused_row.__getitem__ = lambda s, k: paused_connector[k]
    paused_row.get = lambda k, default=None: paused_connector.get(k, default)
    mock_db.fetchrow.return_value = paused_row

    result = await svc.run_pull_sync(
        connector_id=CONNECTOR_ID,
        tenant_id=TENANT_ID,
        db=mock_db,
        kms=mock_kms,
        kafka=mock_kafka,
    )

    assert result.get("skipped") is True
    mock_kafka.employee_event.assert_not_awaited()
