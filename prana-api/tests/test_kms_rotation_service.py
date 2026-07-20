"""Tests for services/kms_rotation_service.py — implements the previously-stub
rotate_tenant_kek / rotate_hmac_secret / get_next_tenant_for_rotation activities
(workflows/security.py's KMSKeyRotationWorkflow, HMACSecretRotationWorkflow).
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.kms_rotation_service import KMSRotationService


class _FakeTxn:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


def _db(fetchrow_return=None, fetch_return=None):
    db = AsyncMock()
    db.fetchrow.return_value = fetchrow_return
    db.fetch.return_value = fetch_return or []
    db.transaction = lambda: _FakeTxn()
    return db


@pytest.mark.asyncio
async def test_get_next_tenant_for_rotation_returns_overdue_tenant():
    tenant_id = uuid.uuid4()
    db = _db(fetchrow_return={"tenant_id": tenant_id, "kek_arn": "arn:1", "last_rotated_at": None})
    svc = KMSRotationService(db)

    result = await svc.get_next_tenant_for_rotation(interval_days=365)

    assert result == {"tenant_id": str(tenant_id), "kek_arn": "arn:1"}
    query_call = db.fetchrow.call_args
    assert query_call.args[1] == 365


@pytest.mark.asyncio
async def test_get_next_tenant_for_rotation_returns_empty_when_none_due():
    db = _db(fetchrow_return=None)
    svc = KMSRotationService(db)

    result = await svc.get_next_tenant_for_rotation(interval_days=365)

    assert result == {}


@pytest.mark.asyncio
async def test_rotate_tenant_kek_rewraps_every_employee_dek_and_logs_count():
    tenant_id = str(uuid.uuid4())
    emp_uuid = uuid.uuid4()
    db = _db(fetch_return=[{"employee_uuid": emp_uuid, "enc_dek": "old-wrapped"}])
    kms = MagicMock()
    kms.create_tenant_kek.return_value = "arn:new"
    kms.unwrap_dek.return_value = b"raw-dek"
    kms.wrap_dek.return_value = "new-wrapped"

    svc = KMSRotationService(db, kms_service=kms)
    await svc.rotate_tenant_kek(tenant_id=tenant_id, kek_arn="arn:old")

    kms.create_tenant_kek.assert_called_once_with(tenant_id)
    kms.unwrap_dek.assert_called_once_with("old-wrapped", "arn:old")
    kms.wrap_dek.assert_called_once_with(b"raw-dek", "arn:new")

    dek_update = next(c for c in db.execute.call_args_list if "UPDATE employee_master SET enc_dek" in c.args[0])
    assert dek_update.args[1] == "new-wrapped"

    tenant_update = next(c for c in db.execute.call_args_list if "UPDATE tenant SET kek_arn" in c.args[0])
    assert tenant_update.args[1] == "arn:new"

    log_insert = next(c for c in db.execute.call_args_list if "INSERT INTO kms_key_log" in c.args[0])
    assert "TENANT_KEK" in log_insert.args[0]
    assert log_insert.args[-1] == 1  # dek_rewrap_count


@pytest.mark.asyncio
async def test_rotate_tenant_kek_logs_zero_rewraps_without_a_kms_client():
    db = _db()
    svc = KMSRotationService(db, kms_service=None)

    await svc.rotate_tenant_kek(tenant_id=str(uuid.uuid4()), kek_arn="arn:old")

    log_insert = next(c for c in db.execute.call_args_list if "INSERT INTO kms_key_log" in c.args[0])
    assert 0 in log_insert.args


@pytest.mark.asyncio
async def test_rotate_hmac_secret_calls_secrets_manager_and_logs_platform_wide():
    db = _db()
    secrets_client = MagicMock()
    svc = KMSRotationService(db, secrets_client=secrets_client)

    await svc.rotate_hmac_secret(secret_id="prana/platform-hmac-secret")

    secrets_client.rotate_secret.assert_called_once_with(SecretId="prana/platform-hmac-secret")
    log_insert = next(c for c in db.execute.call_args_list if "INSERT INTO kms_key_log" in c.args[0])
    assert "PLATFORM_HMAC" in log_insert.args[0]
    assert "NULL" in log_insert.args[0]  # tenant_id — platform-wide, not per-tenant
