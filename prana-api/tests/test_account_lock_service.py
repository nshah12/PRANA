"""Tests for services/account_lock_service.py — implements the previously-stub
apply_policy_lock / release_policy_lock activities (workflows/security.py) for
real. See prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §3.3.
"""
import uuid
from unittest.mock import AsyncMock

import pytest

from services.account_lock_service import AccountLockService


class _FakeTxn:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


def _db(fetchval_return=None, fetchrow_return=None):
    db = AsyncMock()
    db.fetchval.return_value = fetchval_return
    db.fetchrow.return_value = fetchrow_return
    db.transaction = lambda: _FakeTxn()
    return db


@pytest.mark.asyncio
async def test_apply_policy_lock_writes_account_status_event_and_locks_employee():
    db = _db(fetchval_return=None)
    svc = AccountLockService(db)

    event_id = await svc.apply_policy_lock(
        user_type="employee", user_id="emp-1", tenant_id="tenant-1",
        reason_code="BULK_ACCESS_ANOMALY", lock_hours=24,
    )

    assert event_id
    insert_call = next(c for c in db.execute.call_args_list if "INSERT INTO account_status_event" in c.args[0])
    sql, *args = insert_call.args
    assert args[1] == "employee"       # user_type
    assert args[2] == "emp-1"          # user_id
    assert args[3] == "tenant-1"       # tenant_id
    assert args[4] == "BULK_ACCESS_ANOMALY"
    assert args[5] == 24               # lock_hours

    status_call = next(c for c in db.execute.call_args_list if "UPDATE employee_user" in c.args[0])
    assert status_call.args[1] == "LOCKED"
    assert status_call.args[2] == "emp-1"


@pytest.mark.asyncio
async def test_apply_policy_lock_locks_oa_user_table_not_employee_table():
    db = _db(fetchval_return=None)
    svc = AccountLockService(db)

    await svc.apply_policy_lock(
        user_type="oa_user", user_id="oa-1", tenant_id="tenant-1",
        reason_code="BRUTE_FORCE_ANOMALY", lock_hours=24,
    )

    assert any("UPDATE oa_user" in c.args[0] for c in db.execute.call_args_list)
    assert not any("UPDATE employee_user" in c.args[0] for c in db.execute.call_args_list)


@pytest.mark.asyncio
async def test_apply_policy_lock_is_idempotent_returns_existing_open_lock():
    """Regression guard: a Temporal activity retry after a successful-but-lost
    response must not double-lock or create a second account_status_event row."""
    existing_id = uuid.uuid4()
    db = _db(fetchval_return=existing_id)
    svc = AccountLockService(db)

    event_id = await svc.apply_policy_lock(
        user_type="employee", user_id="emp-1", tenant_id="tenant-1",
        reason_code="BULK_ACCESS_ANOMALY", lock_hours=24,
    )

    assert event_id == str(existing_id)
    assert not any("INSERT INTO account_status_event" in c.args[0] for c in db.execute.call_args_list)


@pytest.mark.asyncio
async def test_release_policy_lock_reverses_event_and_restores_active():
    lock_event_id = str(uuid.uuid4())
    db = _db(fetchrow_return={"reversed_by_event_id": None})
    svc = AccountLockService(db)

    await svc.release_policy_lock(
        user_type="employee", user_id="emp-1",
        event_id=lock_event_id, unlocked_by="", early=False,
    )

    insert_call = next(c for c in db.execute.call_args_list if "INSERT INTO account_status_event" in c.args[0])
    assert insert_call.args[2] == "employee"
    assert insert_call.args[3] == "emp-1"
    assert insert_call.args[4] == "SYSTEM"  # actor_type: auto-expiry, not CISO-initiated

    reverse_call = next(c for c in db.execute.call_args_list if "SET reversed_by_event_id" in c.args[0])
    assert str(reverse_call.args[2]) == lock_event_id

    status_call = next(c for c in db.execute.call_args_list if "UPDATE employee_user" in c.args[0])
    assert status_call.args[1] == "ACTIVE"


@pytest.mark.asyncio
async def test_release_policy_lock_early_unlock_records_ciso_actor():
    db = _db(fetchrow_return={"reversed_by_event_id": None})
    svc = AccountLockService(db)
    ciso_id = str(uuid.uuid4())

    await svc.release_policy_lock(
        user_type="oa_user", user_id="oa-1",
        event_id=str(uuid.uuid4()), unlocked_by=ciso_id, early=True,
    )

    insert_call = next(c for c in db.execute.call_args_list if "INSERT INTO account_status_event" in c.args[0])
    assert insert_call.args[4] == "CISO"
    assert str(insert_call.args[5]) == ciso_id


@pytest.mark.asyncio
async def test_release_policy_lock_is_idempotent_noop_if_already_reversed():
    """Regression guard: routers/ciso.py's manual_unlock can reverse the lock
    directly (it doesn't signal the running workflow) before the workflow's own
    timer fires — release_policy_lock must not double-reverse or re-lock."""
    db = _db(fetchrow_return={"reversed_by_event_id": uuid.uuid4()})
    svc = AccountLockService(db)

    await svc.release_policy_lock(
        user_type="employee", user_id="emp-1",
        event_id=str(uuid.uuid4()), unlocked_by="", early=False,
    )

    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_release_policy_lock_noop_if_event_not_found():
    db = _db(fetchrow_return=None)
    svc = AccountLockService(db)

    await svc.release_policy_lock(
        user_type="employee", user_id="emp-1",
        event_id=str(uuid.uuid4()), unlocked_by="", early=False,
    )

    db.execute.assert_not_called()


# ── apply_totp_lockout / release_totp_lockout ─────────────────────────────────

@pytest.mark.asyncio
async def test_apply_totp_lockout_writes_totp_lockout_event():
    db = _db(fetchval_return=None)
    svc = AccountLockService(db)

    event_id = await svc.apply_totp_lockout(user_type="employee", user_id="emp-1", tenant_id="tenant-1")

    assert event_id
    insert_call = next(c for c in db.execute.call_args_list if "INSERT INTO account_status_event" in c.args[0])
    assert "TOTP_LOCKOUT" in insert_call.args[0]
    assert insert_call.args[2] == "employee"
    assert insert_call.args[3] == "emp-1"


@pytest.mark.asyncio
async def test_apply_totp_lockout_is_idempotent():
    existing_id = uuid.uuid4()
    db = _db(fetchval_return=existing_id)
    svc = AccountLockService(db)

    event_id = await svc.apply_totp_lockout(user_type="employee", user_id="emp-1", tenant_id="tenant-1")

    assert event_id == str(existing_id)
    assert not any("INSERT INTO account_status_event" in c.args[0] for c in db.execute.call_args_list)


@pytest.mark.asyncio
async def test_apply_totp_lockout_locks_portal_admin_table():
    db = _db(fetchval_return=None)
    svc = AccountLockService(db)

    await svc.apply_totp_lockout(user_type="portal_admin", user_id="pa-1", tenant_id=None)

    assert any("UPDATE portal_admin" in c.args[0] for c in db.execute.call_args_list)


@pytest.mark.asyncio
async def test_release_totp_lockout_restores_active_and_resets_failed_count():
    lock_event_id = str(uuid.uuid4())
    db = _db(fetchrow_return={"reversed_by_event_id": None})
    svc = AccountLockService(db)

    await svc.release_totp_lockout(user_type="employee", user_id="emp-1", event_id=lock_event_id)

    status_call = next(c for c in db.execute.call_args_list if "UPDATE employee_user SET status" in c.args[0])
    assert status_call.args[1] == "ACTIVE"
    reset_call = next(c for c in db.execute.call_args_list if "failed_totp_count=0" in c.args[0])
    assert reset_call.args[1] == "emp-1"


@pytest.mark.asyncio
async def test_release_totp_lockout_is_idempotent_noop_if_already_reversed():
    db = _db(fetchrow_return={"reversed_by_event_id": uuid.uuid4()})
    svc = AccountLockService(db)

    await svc.release_totp_lockout(user_type="employee", user_id="emp-1", event_id=str(uuid.uuid4()))

    db.execute.assert_not_called()
