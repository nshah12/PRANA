"""
Unit tests for services/employee_service.py — EmployeeService.

Covers:
  - search() always scopes queries to tenant_id
  - create() never stores raw NIK/PAN in DB (only pan_token + enc_pan)
  - Multi-org employees: same pan_token → same employee_user_id across tenants
  - Response from search() never contains raw salary fields
"""
import datetime
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from services.employee_service import EmployeeService


def _make_kms():
    kms = MagicMock()
    kms.wrap_dek = MagicMock(return_value=b"encrypted_dek")
    kms.unwrap_dek = MagicMock(return_value=b"\x00" * 32)
    return kms


def _make_db(*, eu_exists: bool = False):
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=({"employee_user_id": "eu-uuid-existing"} if eu_exists else None))
    db.fetchval = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=None)
    db.executemany = AsyncMock(return_value=None)
    db.fetch = AsyncMock(return_value=[])
    db.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=None),
        __aexit__=AsyncMock(return_value=False),
    ))
    return db


def _make_svc(db, kms=None):
    return EmployeeService(
        db=db,
        kms=kms or _make_kms(),
        platform_hmac_secret="test_secret_32chars_padding_pad1",
    )


# -- Search scoping ------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_employees_scoped_to_tenant():
    """search() must always pass tenant_id as first WHERE condition."""
    db = _make_db()
    db.fetch = AsyncMock(return_value=[])
    svc = _make_svc(db)

    await svc.search("tenant-abc", active_only=True)

    db.fetch.assert_called_once()
    sql, *args = db.fetch.call_args[0]
    assert "tenant-abc" in args, "search() must include tenant_id in query parameters"


# -- Privacy contract ----------------------------------------------------------

@pytest.mark.asyncio
async def test_employee_response_never_contains_raw_salary():
    """search() result rows must not contain raw salary fields."""
    db = _make_db()
    db.fetch = AsyncMock(return_value=[{
        "employee_uuid":    "emp-uuid-001",
        "employee_user_id": "eu-uuid-001",
        "pan_token":        "hash123",
        "emp_id_org":       "EMP001",
        "full_name":        "Rahul Sharma",
        "designation":      "Engineer",
        "department":       "Engineering",
        "grade":            "L4",
        "location":         "Mumbai",
        "doj":              datetime.date(2022, 1, 15),
        "dol":              None,
        "status":           "ACTIVE",
        "vault_completeness": 75,
    }])
    svc = _make_svc(db)

    results = await svc.search("tenant-001")

    for row in results:
        for field in ("gross_salary", "net_salary", "basic_salary", "ctc", "nik", "pan"):
            assert field not in row, f"Sensitive field '{field}' leaked in search result"


# -- Multi-org employee --------------------------------------------------------

@pytest.mark.asyncio
async def test_career_queries_use_all_employee_master_rows_not_single():
    """search() uses tenant_id scoping — a multi-org employee has a separate
    employee_master row per tenant, all sharing the same pan_token.
    Verify that the DB query is parameterised by tenant_id (not hardcoded to one employee_uuid).
    """
    db = _make_db()
    db.fetch = AsyncMock(return_value=[])
    svc = _make_svc(db)

    # Two searches for different tenants for the same physical employee
    await svc.search("tenant-001")
    await svc.search("tenant-002")

    assert db.fetch.call_count == 2
    calls = db.fetch.call_args_list
    # Each call must be scoped to its respective tenant
    assert "tenant-001" in calls[0][0]
    assert "tenant-002" in calls[1][0]


@pytest.mark.asyncio
async def test_multi_org_employee_has_multiple_master_rows():
    """create() reuses existing employee_user_id when pan_token already exists.
    Two tenants onboarding the same employee should link to one employee_user row.
    """
    db = _make_db(eu_exists=True)  # employee_user already exists for this pan_token
    # fetchrow is called for: (1) employee_user lookup by pan_token, (2) tenant name lookup
    db.fetchrow = AsyncMock(side_effect=[
        {"employee_user_id": "eu-uuid-existing"},  # employee_user exists
        {"tenant_name": "Acme Corp"},               # _tenant_name lookup
    ])
    svc = _make_svc(db)

    result = await svc.create(
        nik="ABCDE1234F",           # pan
        tenant_id="tenant-002",
        emp_id_org="EMP002",
        full_name="Rahul Sharma",
        designation="Engineer",
        department=None,
        grade=None,
        location=None,
        employment_type="PERMANENT",
        cost_centre=None,
        uan=None,
        doj=datetime.date(2022, 1, 15),
        created_by="admin-001",
        kek_arn="arn:aws:kms:ap-south-1:123:key/test",
    )

    # Must reuse existing employee_user_id rather than create a new one
    assert result["employee_user_id"] == "eu-uuid-existing"


# -- NIK never stored ----------------------------------------------------------

@pytest.mark.asyncio
async def test_create_never_stores_raw_nik_in_db():
    """create() must not pass raw NIK to any DB execute call — only pan_token and enc_pan."""
    db = _make_db()
    svc = _make_svc(db)

    raw_nik = "ABCDE1234F"
    await svc.create(
        nik=raw_nik,
        tenant_id="tenant-001",
        emp_id_org=None,
        full_name="Test Employee",
        designation=None, department=None, grade=None, location=None,
        employment_type="PERMANENT",
        cost_centre=None, uan=None,
        doj=datetime.date(2023, 6, 1),
        created_by="admin-001",
        kek_arn="arn:aws:kms:ap-south-1:123:key/test",
    )

    all_calls = str(db.execute.call_args_list)
    assert raw_nik not in all_calls, "Raw NIK/PAN passed to DB execute — must never store plaintext"
