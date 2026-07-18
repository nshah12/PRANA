"""Tests for services/employee_lifecycle_service.py — implements the previously-stub
activities in workflows/employee_lifecycle.py for real.
"""
from unittest.mock import AsyncMock

import pytest

from services.employee_lifecycle_service import EmployeeLifecycleService


def _db(fetchrow_return=None, fetchval_return=None, fetch_return=None):
    db = AsyncMock()
    db.fetchrow.return_value = fetchrow_return
    db.fetchval.return_value = fetchval_return
    db.fetch.return_value = fetch_return or []
    return db


@pytest.mark.asyncio
async def test_freeze_employee_vault_blocks_push_and_revokes_sessions():
    db = _db(fetchrow_return={"employee_user_id": "eu-1"})
    svc = EmployeeLifecycleService(db)

    await svc.freeze_employee_vault(employee_uuid="emp-1", tenant_id="t-1")

    push_call = next(c for c in db.execute.call_args_list if "can_push=FALSE" in c.args[0])
    assert push_call.args[1] == "emp-1"
    assert push_call.args[2] == "t-1"

    session_call = next(c for c in db.execute.call_args_list if "UPDATE user_session" in c.args[0])
    assert "revoked=TRUE" in session_call.args[0]
    assert session_call.args[1] == "eu-1"


@pytest.mark.asyncio
async def test_freeze_employee_vault_noop_if_employee_not_found():
    db = _db(fetchrow_return=None)
    svc = EmployeeLifecycleService(db)

    await svc.freeze_employee_vault(employee_uuid="emp-1", tenant_id="t-1")

    assert not any("UPDATE user_session" in c.args[0] for c in db.execute.call_args_list)


@pytest.mark.asyncio
async def test_close_push_window_sets_can_push_false():
    db = _db()
    svc = EmployeeLifecycleService(db)

    await svc.close_push_window(employee_uuid="emp-2", tenant_id="t-1")

    call = db.execute.call_args_list[0]
    assert "can_push=FALSE" in call.args[0]
    assert call.args[1] == "emp-2"


@pytest.mark.asyncio
async def test_provision_vault_activates_pending_employee():
    db = _db()
    svc = EmployeeLifecycleService(db)

    await svc.provision_vault(employee_user_id="eu-3")

    call = db.execute.call_args_list[0]
    assert "status='ACTIVE'" in call.args[0]
    assert "PENDING_ACTIVATION" in call.args[0]
    assert call.args[1] == "eu-3"


@pytest.mark.asyncio
async def test_provision_vault_guards_against_missing_login_handle():
    """chk_eu_login_handle (schema.sql) requires mobile OR email once status leaves
    PENDING_ACTIVATION — activating a row with neither set would fail that CHECK
    constraint. The UPDATE's WHERE clause must guard on this rather than crash."""
    db = _db()
    svc = EmployeeLifecycleService(db)

    await svc.provision_vault(employee_user_id="eu-3")

    call = db.execute.call_args_list[0]
    assert "mobile IS NOT NULL" in call.args[0]
    assert "email IS NOT NULL" in call.args[0]


@pytest.mark.asyncio
async def test_reconcile_rejoining_employee_restores_can_push():
    db = _db()
    svc = EmployeeLifecycleService(db)

    await svc.reconcile_rejoining_employee(employee_uuid="emp-4", tenant_id="t-1")

    call = db.execute.call_args_list[0]
    assert "can_push=TRUE" in call.args[0]
    assert call.args[1] == "emp-4"


@pytest.mark.asyncio
async def test_recompute_vault_completeness_scores_core_doc_type_coverage():
    db = _db(fetch_return=[{"doc_type": "OFFER_LETTER"}, {"doc_type": "SALARY_SLIP"}])
    svc = EmployeeLifecycleService(db)

    result = await svc.recompute_vault_completeness(employee_uuid="emp-5", tenant_id="t-1")

    assert result == {"vault_completeness": 50.0}  # 2 of 4 core types
    update_call = next(c for c in db.execute.call_args_list if "vault_completeness" in c.args[0])
    assert update_call.args[1] == "emp-5"
    assert update_call.args[2] == 50.0


@pytest.mark.asyncio
async def test_recompute_vault_completeness_zero_when_no_documents():
    db = _db(fetch_return=[])
    svc = EmployeeLifecycleService(db)

    result = await svc.recompute_vault_completeness(employee_uuid="emp-6", tenant_id="t-1")

    assert result == {"vault_completeness": 0.0}


@pytest.mark.asyncio
async def test_grant_nominee_access_sets_activation_and_expiry():
    db = _db(fetchrow_return={"pan_token": "pan-tok-1"})
    svc = EmployeeLifecycleService(db)

    await svc.grant_nominee_access(employee_uuid="emp-7", tenant_id="t-1", window_days=90)

    call = db.execute.call_args_list[0]
    assert "access_expires_at" in call.args[0]
    assert call.args[1] == "pan-tok-1"
    assert call.args[2] == 90


@pytest.mark.asyncio
async def test_grant_nominee_access_noop_if_employee_not_found():
    db = _db(fetchrow_return=None)
    svc = EmployeeLifecycleService(db)

    await svc.grant_nominee_access(employee_uuid="emp-7", tenant_id="t-1", window_days=90)

    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_nominee_access_expires_immediately():
    db = _db(fetchrow_return={"pan_token": "pan-tok-2"})
    svc = EmployeeLifecycleService(db)

    await svc.revoke_nominee_access(employee_uuid="emp-8", tenant_id="t-1")

    call = db.execute.call_args_list[0]
    assert "access_expires_at=NOW()" in call.args[0]
    assert call.args[1] == "pan-tok-2"


@pytest.mark.asyncio
async def test_flag_dormant_account_inserts_soft_flag_not_a_lock():
    """from_status == to_status == 'ACTIVE' distinguishes this from a real
    POLICY_LOCK/TOTP_LOCKOUT row — dormancy doesn't change login-ability."""
    db = _db(fetchval_return=None)
    svc = EmployeeLifecycleService(db)

    await svc.flag_dormant_account(employee_user_id="eu-9", tenant_id="t-1")

    call = next(c for c in db.execute.call_args_list if "INSERT INTO account_status_event" in c.args[0])
    assert "'employee'" in call.args[0]
    assert call.args[2] == "eu-9"
    assert call.args[3] == "t-1"
    assert "'ACTIVE', 'ACTIVE'" in call.args[0]  # from_status, to_status
    assert "'DORMANCY_THRESHOLD_EXCEEDED'" in call.args[0]


@pytest.mark.asyncio
async def test_flag_dormant_account_idempotent_skips_if_already_flagged():
    db = _db(fetchval_return="existing-event-id")
    svc = EmployeeLifecycleService(db)

    await svc.flag_dormant_account(employee_user_id="eu-9", tenant_id="t-1")

    assert not any("INSERT INTO account_status_event" in c.args[0] for c in db.execute.call_args_list)
