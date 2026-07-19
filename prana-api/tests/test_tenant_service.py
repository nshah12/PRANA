"""
Tests for services/tenant_service.py — TenantService unit tests.

Covers:
  - create_pending() generates its own tenant_id (never from caller) — KEK ARN embedded
  - Offboard-path: audit_event rows are never deleted (7-year retention rule)
  - tenant_id always from JWT/service layer — never from request body
"""
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.tenant_service import TenantService


def _make_db():
    db = MagicMock()
    db.execute = AsyncMock(return_value=None)
    db.fetchrow = AsyncMock(return_value=None)
    db.fetch = AsyncMock(return_value=[])
    db.fetchval = AsyncMock(return_value=None)
    db.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=None),
        __aexit__=AsyncMock(return_value=False),
    ))
    return db


# -- KEK ARN embedded in create_pending() ----------------------------------

@pytest.mark.asyncio
async def test_provision_tenant_creates_kek_in_kms():
    """create_pending() must embed a KMS KEK ARN in the INSERT.
    In dev mode a placeholder ARN is generated from the tenant_id.
    Verify the INSERT contains an ARN starting with 'arn:aws:kms'.
    """
    db = _make_db()
    svc = TenantService(db, kms=None)  # kms=None: dev mode, placeholder ARN

    result = await svc.create_pending(
        tenant_name="Acme Corp",
        domain="acme.com",
        cin=None,
        gstin=None,
        nik_type="PAN",
        primary_state="Maharashtra",
        home_region="ap-south-1",
        self_upload_policy="ALLOWED_WITH_WARNING",
        storage_quota_gb=50,
        created_by_pa="pa-uuid-001",
        first_oa_admin_email="admin@acme.com",
    )

    # create_pending must return a fresh tenant_id (auto-generated UUID)
    assert "tenant_id" in result
    assert result["status"] == "PENDING"

    # The INSERT call must have embedded a kek_arn starting with arn:aws:kms
    all_args = str(db.execute.call_args_list)
    assert "arn:aws:kms" in all_args, \
        "kek_arn must be embedded in the INSERT (dev placeholder ARN)"

    # KEK must be derived from tenant_id (dev pattern: dev-{tenant_id[:8]})
    tenant_id = result["tenant_id"]
    assert tenant_id[:8] in all_args, \
        "Dev KEK ARN must encode the tenant_id prefix"


@pytest.mark.asyncio
async def test_create_pending_generates_own_tenant_id():
    """create_pending() must generate its own UUID.
    Callers must never supply a tenant_id — it's always internal.
    """
    db = _make_db()
    svc = TenantService(db, kms=None)

    result1 = await svc.create_pending(
        tenant_name="Acme", domain="acme.com", cin=None, gstin=None,
        nik_type="PAN", primary_state="MH", home_region="ap-south-1",
        self_upload_policy="ALLOWED_WITH_WARNING", storage_quota_gb=50,
        created_by_pa="pa-001", first_oa_admin_email="a@acme.com",
    )
    result2 = await svc.create_pending(
        tenant_name="Beta Corp", domain="beta.com", cin=None, gstin=None,
        nik_type="PAN", primary_state="KA", home_region="ap-south-1",
        self_upload_policy="ALLOWED_WITH_WARNING", storage_quota_gb=50,
        created_by_pa="pa-001", first_oa_admin_email="a@beta.com",
    )

    # Each call must generate a different tenant_id
    assert result1["tenant_id"] != result2["tenant_id"]


# -- Audit events are never deleted ----------------------------------------

def test_offboard_tenant_does_not_delete_audit_events():
    """TenantService must NEVER delete audit_event rows — 7-year legal retention.
    Verified by reading source via pathlib (no import tricks needed).
    """
    import pathlib

    source_file = pathlib.Path(__file__).parent.parent / "services" / "tenant_service.py"
    source = source_file.read_text(encoding="utf-8").upper()

    assert "DELETE FROM AUDIT_EVENT" not in source, \
        "tenant_service.py must not DELETE audit_event rows — 7-year retention"
    assert "TRUNCATE AUDIT_EVENT" not in source, \
        "tenant_service.py must not TRUNCATE audit_event"


# -- suspend() never writes audit_event directly ----------------------------

@pytest.mark.asyncio
async def test_suspend_does_not_insert_audit_event_directly():
    """TenantService.suspend() must not INSERT into audit_event itself —
    AuditConsumer owns that, fed by a Kafka publish from the router
    (see routers/tenants.py).
    """
    db = _make_db()
    svc = TenantService(db, None)

    await svc.suspend("tenant-xyz", "Non-payment", "pa-uuid-001")

    executed_sql_calls = [c[0][0].upper() for c in db.execute.call_args_list]
    assert not any("AUDIT_EVENT" in sql for sql in executed_sql_calls)


@pytest.mark.asyncio
async def test_suspend_writes_account_status_event():
    """TenantService.suspend() must record the transition in account_status_event —
    PRANA_UserMgmt_DataArchitecture_v25.html lists TENANT_SUSPENDED as a tracked
    event type there, and every other lock/suspend path (see oa_user_service.py)
    already follows this pattern.
    """
    db = _make_db()
    svc = TenantService(db, None)

    await svc.suspend("tenant-xyz", "Non-payment", "pa-uuid-001")

    insert_calls = [c for c in db.execute.call_args_list
                    if "account_status_event" in c[0][0].lower()]
    assert len(insert_calls) == 1
    sql = insert_calls[0].args[0]
    values = insert_calls[0].args[1:]
    assert "'tenant'" in sql
    assert "TENANT_SUSPENDED" in sql
    assert "SUSPENDED" in sql
    assert "tenant-xyz" in values
    assert "Non-payment" in values
    assert "pa-uuid-001" in values


@pytest.mark.asyncio
async def test_activate_writes_account_status_event():
    """TenantService.activate() must record TENANT_ACTIVATED in account_status_event
    for the same lock/lifecycle history the CISO/PA views read.
    """
    db = _make_db()
    db.fetchrow = AsyncMock(return_value={"status": "PENDING"})
    svc = TenantService(db, None)

    await svc.activate("tenant-xyz", "admin@acme.com", "pa-uuid-001")

    insert_calls = [c for c in db.execute.call_args_list
                    if "account_status_event" in c[0][0].lower()]
    assert len(insert_calls) == 1
    sql = insert_calls[0].args[0]
    values = insert_calls[0].args[1:]
    assert "'tenant'" in sql
    assert "TENANT_ACTIVATED" in sql
    assert "tenant-xyz" in values
    assert "PENDING" in values
    assert "pa-uuid-001" in values


# -- tenant_id never from request body -------------------------------------

@pytest.mark.asyncio
async def test_tenant_id_never_from_request_body():
    """TenantService.create_pending() generates its own tenant_id internally.
    The method signature has no 'tenant_id' parameter — callers cannot inject one.
    """
    import inspect as _inspect
    sig = _inspect.signature(TenantService.create_pending)
    param_names = list(sig.parameters.keys())

    assert "tenant_id" not in param_names, \
        "create_pending() must not accept tenant_id from caller — always auto-generated"
