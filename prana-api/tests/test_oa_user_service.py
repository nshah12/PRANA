"""
Unit tests for services/oa_user_service.py — OAUserService.

Covers:
  - Password hashed with Argon2id (temp_password never stored plaintext)
  - User creation scoped to the tenant_id passed by the caller
  - Min-admin constraint: cannot deactivate last admin
  - Email domain validation
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.oa_user_service import OAUserService
from services.encryption_service import verify_password


def _make_db(*, domain="acme.com", existing_admins=2):
    db = MagicMock()
    # fetchrow: tenant domain check
    db.fetchrow = AsyncMock(return_value={"domain": domain})
    # fetchval: admin count check (for min-admin guard)
    db.fetchval = AsyncMock(return_value=existing_admins)
    db.execute = AsyncMock(return_value=None)
    db.fetch = AsyncMock(return_value=[])
    return db


# -- Password hashing ----------------------------------------------------------

@pytest.mark.asyncio
async def test_create_oa_user_hashes_password_with_argon2id():
    """temp_password must be hashed with Argon2id before DB insert — never stored plaintext."""
    db = _make_db()
    svc = OAUserService(db)

    result = await svc.create(
        tenant_id="tenant-001",
        email="op@acme.com",
        role="oa_operator",
        created_by="admin-uuid-001",
    )

    # temp_password is returned for email delivery
    assert "temp_password" in result
    raw = result["temp_password"]

    # The DB insert must have used a hash, not the raw password
    insert_sql = str(db.execute.call_args)
    assert raw not in insert_sql, "Plaintext temp_password found in DB INSERT — must hash first"

    # The hash stored must be verifiable by Argon2id
    # Extract the hash from the call args (5th positional arg after oa_user_id, tenant_id, email, role)
    call_args = db.execute.call_args[0]
    stored_hash = call_args[5]  # temp_password_hash is 6th arg (0-indexed: 5)
    assert verify_password(raw, stored_hash), "Stored hash must be verifiable with Argon2id"


@pytest.mark.asyncio
async def test_create_oa_user_returns_temp_password_for_email():
    """Service must return the plaintext temp_password (once) so router can email it."""
    db = _make_db()
    svc = OAUserService(db)

    result = await svc.create(
        tenant_id="tenant-001",
        email="op@acme.com",
        role="oa_operator",
        created_by="admin-uuid-001",
    )

    assert "temp_password" in result
    assert len(result["temp_password"]) > 8  # meaningful length


# -- Tenant scoping ------------------------------------------------------------

@pytest.mark.asyncio
async def test_oa_user_scoped_to_tenant_of_creating_admin():
    """New user must be inserted with the tenant_id that was passed in — not derived from email."""
    db = _make_db(domain="acme.com")
    svc = OAUserService(db)

    await svc.create(
        tenant_id="tenant-xyz",
        email="op@acme.com",
        role="oa_operator",
        created_by="admin-uuid-001",
    )

    # The INSERT must use the passed tenant_id
    insert_args = db.execute.call_args[0]
    assert "tenant-xyz" in insert_args, "INSERT must use passed tenant_id, not a derived one"


@pytest.mark.asyncio
async def test_create_rejects_email_domain_mismatch():
    """Service raises EMAIL_DOMAIN_MISMATCH when email domain != tenant domain."""
    db = _make_db(domain="acme.com")
    svc = OAUserService(db)

    with pytest.raises(ValueError, match="EMAIL_DOMAIN_MISMATCH"):
        await svc.create(
            tenant_id="tenant-001",
            email="op@rival.com",
            role="oa_operator",
            created_by="admin-uuid-001",
        )


# -- Min-admin constraint ------------------------------------------------------

@pytest.mark.asyncio
async def test_deactivate_last_admin_raises_constraint():
    """Cannot deactivate the last remaining oa_admin — MIN_ADMIN_CONSTRAINT."""
    db = _make_db(existing_admins=0)  # 0 OTHER admins → would leave tenant adminless
    # fetchrow for role check
    db.fetchrow = AsyncMock(return_value={"role": "oa_admin"})
    db.fetchval = AsyncMock(return_value=0)  # no other admins
    db.fetch = AsyncMock(return_value=[])
    svc = OAUserService(db)

    with pytest.raises(ValueError, match="MIN_ADMIN_CONSTRAINT"):
        await svc.deactivate("admin-uuid-001", "tenant-001", "admin-uuid-001")
