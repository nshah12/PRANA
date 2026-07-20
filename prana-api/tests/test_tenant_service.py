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

def _make_kms():
    """create_pending() calls self._kms.create_kek(tenant_id) for a real KMS-
    provisioned KEK (fixed earlier: this used to fabricate a placeholder ARN
    string without ever calling KMS — see services/tenant_service.py's comment)."""
    kms = MagicMock()
    kms.create_kek = MagicMock(return_value="arn:aws:kms:ap-south-1:123456789012:key/mock-kek")
    return kms


@pytest.mark.asyncio
async def test_provision_tenant_creates_kek_in_kms():
    """create_pending() must call KMSService.create_kek(tenant_id) and embed the
    real returned ARN in the INSERT — not a fabricated placeholder string."""
    db = _make_db()
    kms = _make_kms()
    svc = TenantService(db, kms=kms)

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

    # KMSService.create_kek must be called with the newly-generated tenant_id
    kms.create_kek.assert_called_once_with(result["tenant_id"])

    # The INSERT call must have embedded the ARN create_kek() returned
    all_args = str(db.execute.call_args_list)
    assert "arn:aws:kms:ap-south-1:123456789012:key/mock-kek" in all_args, \
        "kek_arn returned by KMSService.create_kek must be embedded in the INSERT"


@pytest.mark.asyncio
async def test_create_pending_generates_own_tenant_id():
    """create_pending() must generate its own UUID.
    Callers must never supply a tenant_id — it's always internal.
    """
    db = _make_db()
    svc = TenantService(db, kms=_make_kms())

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
async def test_suspend_reads_current_status_not_hardcoded():
    """TenantService.suspend() must read the tenant's actual current status
    before writing account_status_event.from_status — not hardcode 'ACTIVE'.
    Mirrors activate()'s existing SELECT-before-UPDATE pattern (tenant_service.py:141-145).
    """
    db = _make_db()
    db.fetchrow = AsyncMock(return_value={"status": "ACTIVE"})
    svc = TenantService(db, None)

    await svc.suspend("tenant-xyz", "Non-payment", "pa-uuid-001")

    db.fetchrow.assert_called_once()
    insert_calls = [c for c in db.execute.call_args_list
                    if "account_status_event" in c[0][0].lower()]
    assert len(insert_calls) == 1
    sql = insert_calls[0].args[0]
    values = insert_calls[0].args[1:]
    # from_status must come from the bound SELECT result, not a SQL literal
    assert "'ACTIVE','SUSPENDED'" not in sql.replace(" ", "").replace("\n", "")
    assert "ACTIVE" in values


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


# -- reinstate() reverses a suspend via account_status_event ---------------

@pytest.mark.asyncio
async def test_reinstate_writes_account_status_event_and_links_reversal():
    """TenantService.reinstate() must mirror ciso.py's manual_unlock pattern:
    insert a new TENANT_REINSTATED row, link it back to the original
    TENANT_SUSPENDED row via reversed_by_event_id, and flip tenant.status
    back to ACTIVE.
    """
    db = _make_db()
    suspend_event_id = "suspend-event-uuid-001"
    db.fetchrow = AsyncMock(side_effect=[
        {"status": "SUSPENDED"},               # current tenant status check
        {"event_id": suspend_event_id},         # most recent unreversed TENANT_SUSPENDED event
    ])
    svc = TenantService(db, None)

    await svc.reinstate("tenant-xyz", "pa-uuid-001")

    executed_sql_calls = [c.args[0] for c in db.execute.call_args_list]
    upper_calls = [s.upper() for s in executed_sql_calls]

    assert any("UPDATE TENANT" in s and "STATUS='ACTIVE'" in s.replace(" ", "") for s in upper_calls)

    insert_calls = [c for c in db.execute.call_args_list
                    if "insert into account_status_event" in c.args[0].lower()]
    assert len(insert_calls) == 1
    insert_sql = insert_calls[0].args[0]
    insert_values = insert_calls[0].args[1:]
    assert "'tenant'" in insert_sql
    assert "TENANT_REINSTATED" in insert_sql
    assert "tenant-xyz" in insert_values
    assert "pa-uuid-001" in insert_values

    reversal_calls = [c for c in db.execute.call_args_list
                      if "reversed_by_event_id" in c.args[0].lower()
                      and "update account_status_event" in c.args[0].lower()]
    assert len(reversal_calls) == 1
    assert suspend_event_id in reversal_calls[0].args[1:]


@pytest.mark.asyncio
async def test_reinstate_rejects_non_suspended_tenant():
    """reinstate() must refuse if the tenant isn't currently SUSPENDED —
    prevents reinstating an already-active or offboarded tenant."""
    db = _make_db()
    db.fetchrow = AsyncMock(return_value={"status": "ACTIVE"})
    svc = TenantService(db, None)

    with pytest.raises(ValueError, match="NOT_SUSPENDED"):
        await svc.reinstate("tenant-xyz", "pa-uuid-001")


@pytest.mark.asyncio
async def test_reinstate_rejects_when_no_unreversed_suspend_event():
    """reinstate() must refuse if no unreversed TENANT_SUSPENDED event exists —
    a data-integrity guard mirroring ciso.py's ALREADY_UNLOCKED check."""
    db = _make_db()
    db.fetchrow = AsyncMock(side_effect=[
        {"status": "SUSPENDED"},
        None,
    ])
    svc = TenantService(db, None)

    with pytest.raises(ValueError, match="NO_ACTIVE_SUSPENSION"):
        await svc.reinstate("tenant-xyz", "pa-uuid-001")


# -- list_all() selects the fields OnboardingQueue/TenantDirectory need ----

@pytest.mark.asyncio
async def test_list_all_includes_onboarding_tier():
    """TenantService.list_all() must select onboarding_tier alongside the
    other tier/profile fields it already selects (industry, sla_tier,
    employee_headcount_band) — OnboardingQueue.tsx needs it to categorize
    tenants for the auto-approval tier display.
    """
    db = _make_db()
    db.fetch = AsyncMock(return_value=[])
    svc = TenantService(db, None)

    await svc.list_all()

    sql = db.fetch.call_args.args[0]
    assert "onboarding_tier" in sql


@pytest.mark.asyncio
async def test_list_all_includes_domain_verified_at_and_computed_approval_tier():
    """list_all() must select domain_verified_at and attach a computed
    approval_tier (services/onboarding_service.classify_onboarding_tier) so
    OnboardingQueue.tsx can categorize into its 3 buckets without duplicating
    the tiering rule in the frontend.
    """
    import datetime
    db = _make_db()
    db.fetch = AsyncMock(return_value=[{
        "tenant_id": "t-1", "tenant_name": "Acme", "domain": "acme.com",
        "status": "PENDING", "home_region": "ap-south-1", "primary_state": "MH",
        "cin": None, "gstin": None, "industry": "IT & Software",
        "employee_headcount_band": "51-200", "sla_tier": "STANDARD",
        "onboarding_tier": "ASSISTED", "domain_verified_at": None,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }])
    db.fetchrow = AsyncMock(return_value={"config_value": "48"})
    svc = TenantService(db, None)

    result = await svc.list_all()

    sql = db.fetch.call_args.args[0]
    assert "domain_verified_at" in sql
    assert result[0]["approval_tier"] == "AUTO_APPROVE"
    assert result[0]["verification_remaining_hours"] is not None


@pytest.mark.asyncio
async def test_list_all_verification_remaining_hours_none_once_verified():
    import datetime
    db = _make_db()
    db.fetch = AsyncMock(return_value=[{
        "tenant_id": "t-1", "tenant_name": "Acme", "domain": "acme.com",
        "status": "PENDING", "home_region": "ap-south-1", "primary_state": "MH",
        "cin": None, "gstin": None, "industry": "IT & Software",
        "employee_headcount_band": "51-200", "sla_tier": "STANDARD",
        "onboarding_tier": "ASSISTED",
        "domain_verified_at": datetime.datetime.now(datetime.timezone.utc),
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }])
    db.fetchrow = AsyncMock(return_value={"config_value": "48"})
    svc = TenantService(db, None)

    result = await svc.list_all()

    assert result[0]["verification_remaining_hours"] is None


@pytest.mark.asyncio
async def test_get_tenant_includes_domain_verified_at():
    """TenantService.get() must select domain_verified_at — the Tenant Detail
    page needs it to show verification status alongside lifecycle actions.
    """
    db = _make_db()
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    svc = TenantService(db, None)

    await svc.get("tenant-xyz")

    sql = db.fetchrow.call_args.args[0]
    assert "domain_verified_at" in sql


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
