"""
RED tests for HRMSConnectorService.

All tests written before implementation exists — they must fail with
ImportError or AttributeError first (RED), then pass after implementation (GREEN).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4


# ── Fixtures ──────────────────────────────────────────────────────────────────

TENANT_ID   = UUID("b0000000-0000-0000-0000-000000000001")
PA_USER_ID  = UUID("c0000000-0000-0000-0000-000000000001")
CONN_DEF_ID = UUID("d0000000-0000-0000-0000-000000000001")
CONN_ID     = UUID("e0000000-0000-0000-0000-000000000001")

DARWINBOX_DEF = {
    "connector_definition_id": str(CONN_DEF_ID),
    "connector_key":           "darwinbox",
    "display_name":            "Darwinbox",
    "auth_method":             "OAUTH2",
    "supported_modes":         ["PULL", "WEBHOOK"],
    "canonical_field_schema":  {"employee_id": "employee_id"},
    "docs_url":                "https://developers.darwinbox.com/",
    "is_active":               True,
}


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
    kms.encrypt = MagicMock(return_value=b"encrypted_blob")
    kms.decrypt = MagicMock(return_value=b'{"client_id":"x","client_secret":"y"}')
    return kms


@pytest.fixture
def svc():
    from services.hrms_connector_service import HRMSConnectorService
    return HRMSConnectorService()


# ── list_definitions ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_definitions_returns_active_only(svc, mock_db):
    """PA can list all active connector definitions."""
    mock_db.fetch.return_value = [MagicMock(**DARWINBOX_DEF, __getitem__=lambda s, k: DARWINBOX_DEF[k])]
    result = await svc.list_definitions(mock_db)
    assert isinstance(result, list)
    mock_db.fetch.assert_awaited_once()
    # SQL must filter is_active = TRUE
    call_sql = mock_db.fetch.call_args[0][0].lower()
    assert "is_active" in call_sql


@pytest.mark.asyncio
async def test_get_definition_by_key(svc, mock_db):
    """Fetch one connector definition by its key."""
    row = MagicMock()
    row.__getitem__ = lambda s, k: DARWINBOX_DEF[k]
    mock_db.fetchrow.return_value = row
    result = await svc.get_definition(connector_key="darwinbox", db=mock_db)
    assert result is not None
    mock_db.fetchrow.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_definition_not_found_returns_none(svc, mock_db):
    mock_db.fetchrow.return_value = None
    result = await svc.get_definition(connector_key="nonexistent", db=mock_db)
    assert result is None


# ── create_definition (PA) ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_definition_inserts_and_returns_id(svc, mock_db):
    """PA can register a new connector type."""
    new_id = uuid4()
    mock_db.fetchval.return_value = new_id
    result = await svc.create_definition(
        connector_key="greythr",
        display_name="Greythr",
        auth_method="API_KEY",
        supported_modes=["PULL"],
        canonical_field_schema={"employee_id": "empId"},
        db=mock_db,
    )
    assert result == new_id
    mock_db.fetchval.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_definition_rejects_invalid_auth_method(svc, mock_db):
    """auth_method must be one of OAUTH2, API_KEY, WEBHOOK, SFTP."""
    with pytest.raises(ValueError, match="auth_method"):
        await svc.create_definition(
            connector_key="bad",
            display_name="Bad",
            auth_method="BASIC",          # invalid
            supported_modes=["PULL"],
            canonical_field_schema={},
            db=mock_db,
        )


# ── create_tenant_config ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_tenant_config_encrypts_credentials(svc, mock_db, mock_kms):
    """Credentials must be KMS-encrypted before DB write — never stored plaintext."""
    mock_db.fetchval.return_value = CONN_ID

    await svc.create_tenant_config(
        tenant_id=TENANT_ID,
        connector_definition_id=CONN_DEF_ID,
        display_name="Darwinbox – NPCI",
        integration_mode="PULL",
        credentials={"client_id": "abc", "client_secret": "secret"},
        kek_arn="arn:aws:kms:ap-south-1:123:key/test",
        kms=mock_kms,
        db=mock_db,
    )

    # KMS must have been called
    mock_kms.encrypt.assert_called_once()
    # The DB call must NOT contain the raw secret
    db_call_args = str(mock_db.fetchval.call_args)
    assert "secret" not in db_call_args


@pytest.mark.asyncio
async def test_create_tenant_config_returns_connector_id(svc, mock_db, mock_kms):
    new_id = uuid4()
    mock_db.fetchval.return_value = new_id
    result = await svc.create_tenant_config(
        tenant_id=TENANT_ID,
        connector_definition_id=CONN_DEF_ID,
        display_name="Keka – Acme",
        integration_mode="PULL",
        credentials={"api_key": "keka_abc"},
        kek_arn="arn:aws:kms:ap-south-1:123:key/test",
        kms=mock_kms,
        db=mock_db,
    )
    assert result == new_id


# ── update_field_mapping ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_field_mapping_tenant_scoped(svc, mock_db):
    """Field mapping update must be scoped to the tenant — cannot update another tenant's config."""
    await svc.update_field_mapping(
        connector_id=CONN_ID,
        tenant_id=TENANT_ID,
        field_mapping={"employee_id": "emp_code"},
        db=mock_db,
    )
    mock_db.execute.assert_awaited_once()
    # Both connector_id AND tenant_id must be in the WHERE clause
    call_sql = mock_db.execute.call_args[0][0]
    assert "$1" in call_sql and "$2" in call_sql and "$3" in call_sql


# ── get_tenant_configs ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_tenant_configs_scoped_to_tenant(svc, mock_db):
    """list must only return connectors for the given tenant."""
    await svc.list_tenant_configs(tenant_id=TENANT_ID, db=mock_db)
    mock_db.fetch.assert_awaited_once()
    call_sql = mock_db.fetch.call_args[0][0].lower()
    assert "tenant_id" in call_sql


# ── pause / resume ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pause_connector_sets_status_paused(svc, mock_db):
    await svc.set_status(connector_id=CONN_ID, tenant_id=TENANT_ID, status="PAUSED", db=mock_db)
    mock_db.execute.assert_awaited_once()
    call_sql = mock_db.execute.call_args[0][0]
    # Must update status and must be tenant-scoped
    assert "status" in call_sql.lower()


@pytest.mark.asyncio
async def test_set_status_rejects_invalid(svc, mock_db):
    with pytest.raises(ValueError, match="status"):
        await svc.set_status(connector_id=CONN_ID, tenant_id=TENANT_ID, status="DELETED", db=mock_db)


# ── decrypt_credentials ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_decrypt_credentials_calls_kms(svc, mock_kms):
    """Decrypting stored credentials must go through KMS — never stored plaintext."""
    import json
    result = await svc.decrypt_credentials(
        enc_credentials=b"encrypted_blob",
        kek_arn="arn:aws:kms:ap-south-1:123:key/test",
        kms=mock_kms,
    )
    mock_kms.decrypt.assert_called_once_with(b"encrypted_blob", "arn:aws:kms:ap-south-1:123:key/test")
    assert isinstance(result, dict)


# ── log_sync ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_log_sync_start_inserts_row(svc, mock_db):
    sync_id = uuid4()
    mock_db.fetchval.return_value = sync_id
    result = await svc.log_sync_start(
        connector_id=CONN_ID,
        tenant_id=TENANT_ID,
        sync_mode="PULL",
        cursor_before="2026-01-01T00:00:00Z",
        db=mock_db,
    )
    assert result == sync_id


@pytest.mark.asyncio
async def test_log_sync_complete_updates_row(svc, mock_db):
    sync_id = uuid4()
    await svc.log_sync_complete(
        sync_id=sync_id,
        status="SUCCESS",
        docs_pushed=10,
        docs_failed=0,
        cursor_after="2026-06-27T12:00:00Z",
        db=mock_db,
    )
    mock_db.execute.assert_awaited_once()
    call_args = mock_db.execute.call_args[0]
    assert "SUCCESS" in str(call_args)
