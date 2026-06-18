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
