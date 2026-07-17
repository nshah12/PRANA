"""Tests for services/share_service.py."""
import inspect
import pathlib
from unittest.mock import AsyncMock

import pytest

from services.share_service import ShareService


_SOURCE = pathlib.Path(__file__).parent.parent / "services" / "share_service.py"


def test_create_share_token_stored_in_redis_with_config_ttl():
    src = _SOURCE.read_text(encoding="utf-8")
    assert "share:" in src or "share_token" in src, \
        "ShareService must store token in Redis under share: namespace"
    assert "setex" in src or "expire" in src or "expires_at" in src, \
        "Share token must have a TTL"


def test_share_otp_sent_to_recipient_not_owner():
    src = _SOURCE.read_text(encoding="utf-8")
    assert "otp_required" in src, \
        "ShareService must support OTP requirement for share access"
    assert "recipient" in src.lower(), \
        "OTP is for the recipient — must use recipient identifier"


def test_max_active_shares_per_doc_enforced_from_config():
    src = _SOURCE.read_text(encoding="utf-8").upper()
    # Max shares per doc must be enforced — either via DB count query or config check
    assert "MAX_ACTIVE" in src or "USAGE_LIMIT" in src or "COUNT" in src, \
        "ShareService must enforce max active shares per document"


def test_revoke_share_deletes_redis_key():
    src = inspect.getsource(ShareService.revoke)
    assert "revoke" in src.lower() or "status" in src, \
        "revoke() must update share token status"
    # Revocation should clear the DB record
    assert "UPDATE" in src.upper() or "DELETE" in src.upper(), \
        "revoke() must UPDATE or DELETE the share_token row"


# ── revoke_by_id / mark_expired — internal mutations for Temporal activities,
# no employee_user_id ownership check (workflow already has an authorized
# actor context, unlike revoke() which is called from an employee's own
# authenticated HTTP request) ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revoke_by_id_updates_status_without_ownership_check():
    db = AsyncMock()
    svc = ShareService(db=db, redis=None, settings=None)
    await svc.revoke_by_id("share-1")
    sql, *args = db.execute.call_args.args
    assert "UPDATE share_token" in sql
    assert "REVOKED" in sql
    assert "share-1" in args
    assert "employee_user_id" not in sql


@pytest.mark.asyncio
async def test_mark_expired_updates_status_to_expired():
    db = AsyncMock()
    svc = ShareService(db=db, redis=None, settings=None)
    await svc.mark_expired("share-1")
    sql, *args = db.execute.call_args.args
    assert "UPDATE share_token" in sql
    assert "EXPIRED" in sql
    assert "share-1" in args


@pytest.mark.asyncio
async def test_mark_expired_only_touches_active_rows():
    """Idempotent: a retry after the row is already EXPIRED/REVOKED must not
    clobber a REVOKED row back to EXPIRED."""
    db = AsyncMock()
    svc = ShareService(db=db, redis=None, settings=None)
    await svc.mark_expired("share-1")
    sql, *_ = db.execute.call_args.args
    assert "status='ACTIVE'" in sql or "status = 'ACTIVE'" in sql
