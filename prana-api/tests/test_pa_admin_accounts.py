"""
Tests for routers/pa_admin_accounts.py — account, identity & exception admin.
Split 2026-08-10 out of test_pa_admin.py (see that file's docstring). Covers:
PA platform-wide TOTP/password reset override, PA account unlock, employee
record merge/dedupe.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_pa_auth(client, pa_id: str = "pa-uuid-001") -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": pa_id,
        "user_type": "portal_admin",
        "role": "portal_admin",
        "tenant_id": None,     # PA has no tenant affiliation
        "jti": "pa-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def _set_oa_auth(client) -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "oa-uuid-001",
        "user_type": "oa_user",
        "role": "oa_admin",
        "tenant_id": "tenant-001",
        "jti": "oa-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)

# -- PA platform-wide reset TOTP override -----------------------------------
# Departure from pa_admin.py's "zero employee PII" boundary — an explicit,
# reason-required override matching the oa-emergency/reset pattern.

@pytest.mark.asyncio
async def test_pa_reset_totp_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason": "Employee lost device"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pa_reset_totp_requires_reason(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": ""},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "OVERRIDE_REASON_REQUIRED"


@pytest.mark.asyncio
async def test_pa_reset_totp_rejects_unknown_reason_code(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": "MADE_UP_CODE"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "INVALID_REASON_CODE"


@pytest.mark.asyncio
async def test_pa_reset_totp_requires_note_when_reason_code_is_other(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": "OTHER"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "REASON_NOTE_REQUIRED_FOR_OTHER"


@pytest.mark.asyncio
async def test_pa_reset_totp_requires_identifier(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "  ", "reason_code": "EMPLOYEE_LOST_DEVICE"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "IDENTIFIER_REQUIRED"


@pytest.mark.asyncio
async def test_pa_reset_totp_employee_not_found_returns_404(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = None

    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "nobody@example.com", "reason_code": "EMPLOYEE_LOST_DEVICE"},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_pa_reset_totp_clears_secret_platform_wide_no_tenant_scope(client, mock_db):
    """PA is platform-wide — no tenant_id filter on the employee_user lookup or UPDATE."""
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = {"employee_user_id": "eu-001"}
    mock_db.fetch.return_value = [{"tenant_id": "tenant-001", "employee_uuid": "emp-uuid-001"}]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": "EMPLOYEE_LOST_DEVICE",
              "reason_note": "CHRO confirmed"},
    )

    assert resp.status_code == 200
    assert resp.json()["message"] == "EMPLOYEE_TOTP_RESET"
    mock_db.execute.assert_called_once()
    sql, *params = mock_db.execute.call_args[0]
    assert "totp_secret_enc" in sql.lower() and "totp_configured_at" in sql.lower()
    assert "eu-001" in params


@pytest.mark.asyncio
async def test_pa_reset_totp_publishes_override_event_with_reason_per_tenant(client, mock_db, mock_kafka):
    """Must fan out one PORTAL_ADMIN-actor audit event per tenant the employee belongs
    to (multi-org employees have multiple employee_master rows) so each affected
    tenant's CISO gets visibility — using the employee's real tenant_id, not a
    platform-level placeholder. reason_code/reason_note are structured, queryable
    audit fields (see account_status_event.reason_code/reason_note) — not a single
    free-text blob."""
    _set_pa_auth(client, pa_id="pa-uuid-777")
    mock_db.fetchrow.return_value = {"employee_user_id": "eu-002"}
    mock_db.fetch.return_value = [
        {"tenant_id": "tenant-001", "employee_uuid": "emp-uuid-a"},
        {"tenant_id": "tenant-002", "employee_uuid": "emp-uuid-b"},
    ]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/admin/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "9000000002", "reason_code": "SUPPORT_ESCALATION",
              "reason_note": "TCK-1234"},
    )

    assert resp.status_code == 200
    assert mock_kafka.employee_event.call_count == 2
    seen_tenants = set()
    for call in mock_kafka.employee_event.call_args_list:
        event = call[0][0]
        assert event["event_type"] == "EMPLOYEE_TOTP_RESET"
        assert event["actor_type"] == "PORTAL_ADMIN"
        assert event["actor_id"] == "pa-uuid-777"
        assert event["reason_code"] == "SUPPORT_ESCALATION"
        assert event["reason_note"] == "TCK-1234"
        assert event["override"] is True
        seen_tenants.add(event["tenant_id"])
    assert seen_tenants == {"tenant-001", "tenant-002"}


# -- PA unlock (another PA unlocks a locked-out PA) --------------------------
# auth_pa.py: "PA lockout is not auto-unlocked — requires another PA to unlock."
# No endpoint existed for this until now.

@pytest.mark.asyncio
async def test_pa_unlock_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.post(
        "/admin/pa-users/unlock", headers=AUTH_HEADER, json={"email": "locked@prana.in"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pa_unlock_not_found_returns_404(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = None
    resp = await client.post(
        "/admin/pa-users/unlock", headers=AUTH_HEADER, json={"email": "nobody@prana.in"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "USER_NOT_FOUND"


@pytest.mark.asyncio
async def test_pa_unlock_not_locked_returns_409(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = {"pa_id": "pa-uuid-002", "status": "ACTIVE"}
    resp = await client.post(
        "/admin/pa-users/unlock", headers=AUTH_HEADER, json={"email": "already-active@prana.in"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "ALREADY_UNLOCKED"


@pytest.mark.asyncio
async def test_pa_unlock_restores_locked_account_and_publishes_event(client, mock_db, mock_kafka):
    _set_pa_auth(client, pa_id="pa-uuid-001")
    mock_db.fetchrow.return_value = {"pa_id": "pa-uuid-002", "status": "LOCKED"}
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/admin/pa-users/unlock", headers=AUTH_HEADER, json={"email": "locked@prana.in"},
    )

    assert resp.status_code == 200
    assert resp.json()["message"] == "LOCK_REMOVED"

    all_sql = " ".join(str(c) for c in mock_db.execute.call_args_list).lower()
    assert "portal_admin" in all_sql and "'active'" in all_sql
    assert "account_status_event" in all_sql

    mock_kafka.security_event.assert_awaited_once()
    sec = mock_kafka.security_event.call_args[0][0]
    assert sec["event_type"] == "ACCOUNT_UNLOCKED"
    assert sec["actor_type"] == "PORTAL_ADMIN"
    assert sec["actor_id"] == "pa-uuid-001"
    assert sec["target_account_id"] == "pa-uuid-002"


# -- Employee record merge/dedupe ---------------------------------------------
# PA-only, platform-wide: merges a duplicate employee_user (e.g. PAN-typo led to
# two identities for the same physical person) into a canonical employee_user_id.

def _merge_body(duplicate="dup@example.com", canonical="canonical@example.com", reason="PAN typo dedup"):
    return {"duplicate_identifier": duplicate, "canonical_identifier": canonical, "reason": reason}


@pytest.mark.asyncio
async def test_merge_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.post("/admin/employees/merge", headers=AUTH_HEADER, json=_merge_body())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_merge_requires_reason(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/merge", headers=AUTH_HEADER, json=_merge_body(reason=""),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "OVERRIDE_REASON_REQUIRED"


@pytest.mark.asyncio
async def test_merge_duplicate_not_found_returns_404(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = None
    resp = await client.post("/admin/employees/merge", headers=AUTH_HEADER, json=_merge_body())
    assert resp.status_code == 404
    assert resp.json()["detail"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_merge_canonical_not_found_returns_404(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.side_effect = [{"employee_user_id": "eu-dup"}, None]
    resp = await client.post("/admin/employees/merge", headers=AUTH_HEADER, json=_merge_body())
    assert resp.status_code == 404
    assert resp.json()["detail"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_merge_rejects_merging_employee_into_itself(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.side_effect = [{"employee_user_id": "eu-same"}, {"employee_user_id": "eu-same"}]
    resp = await client.post("/admin/employees/merge", headers=AUTH_HEADER, json=_merge_body())
    assert resp.status_code == 400
    assert resp.json()["detail"] == "CANNOT_MERGE_SAME_EMPLOYEE"


@pytest.mark.asyncio
async def test_merge_repoints_all_referencing_tables_and_marks_duplicate(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.side_effect = [{"employee_user_id": "eu-dup"}, {"employee_user_id": "eu-canonical"}]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post("/admin/employees/merge", headers=AUTH_HEADER, json=_merge_body())

    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "EMPLOYEE_RECORDS_MERGED"
    assert body["canonical_employee_user_id"] == "eu-canonical"

    all_sql = " ".join(str(c) for c in mock_db.execute.call_args_list).lower()
    for table in (
        "employee_master", "career_event", "device_credential", "share_token",
        "document_access_log", "employee_consent", "erasure_request",
        "data_export_request", "data_correction_request", "dpdp_grievance", "oa_user",
    ):
        assert table in all_sql, f"merge must re-point {table}"
    # The duplicate row itself must be marked MERGED with merged_into set — never deleted.
    assert "merged" in all_sql and "eu-dup" in all_sql and "eu-canonical" in all_sql


@pytest.mark.asyncio
async def test_merge_publishes_audit_event(client, mock_db, mock_kafka):
    _set_pa_auth(client, pa_id="pa-uuid-555")
    mock_db.fetchrow.side_effect = [{"employee_user_id": "eu-dup"}, {"employee_user_id": "eu-canonical"}]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/admin/employees/merge", headers=AUTH_HEADER,
        json=_merge_body(reason="Confirmed same person via HR"),
    )

    assert resp.status_code == 200
    mock_kafka.employee_event.assert_called_once()
    event = mock_kafka.employee_event.call_args[0][0]
    assert event["event_type"] == "EMPLOYEE_RECORDS_MERGED"
    assert event["actor_type"] == "PORTAL_ADMIN"
    assert event["actor_id"] == "pa-uuid-555"
    assert event["duplicate_employee_user_id"] == "eu-dup"
    assert event["canonical_employee_user_id"] == "eu-canonical"
    assert event["reason"] == "Confirmed same person via HR"


# -- PA platform-wide reset password override ---------------------------------

@pytest.mark.asyncio
async def test_pa_reset_password_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": "EMPLOYEE_LOST_DEVICE"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pa_reset_password_requires_reason(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": ""},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "OVERRIDE_REASON_REQUIRED"


@pytest.mark.asyncio
async def test_pa_reset_password_rejects_unknown_reason_code(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": "MADE_UP_CODE"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "INVALID_REASON_CODE"


@pytest.mark.asyncio
async def test_pa_reset_password_requires_note_when_reason_code_is_other(client, mock_db):
    _set_pa_auth(client)
    resp = await client.post(
        "/admin/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": "OTHER", "reason_note": "  "},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "REASON_NOTE_REQUIRED_FOR_OTHER"


@pytest.mark.asyncio
async def test_pa_reset_password_employee_not_found_returns_404(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = None
    resp = await client.post(
        "/admin/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "nobody@example.com", "reason_code": "EMPLOYEE_LOST_DEVICE"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_pa_reset_password_generates_temp_password_platform_wide(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = {"employee_user_id": "eu-001"}
    mock_db.fetch.return_value = [{"tenant_id": "tenant-001", "employee_uuid": "emp-uuid-001"}]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/admin/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com", "reason_code": "EMPLOYEE_LOST_DEVICE",
              "reason_note": "CHRO confirmed"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "EMPLOYEE_PASSWORD_RESET"
    assert len(body["temp_password"]) >= 12
    mock_db.execute.assert_called_once()
    sql, *params = mock_db.execute.call_args[0]
    assert "password_hash" in sql.lower() and "force_reset" in sql.lower()
    assert "eu-001" in params


@pytest.mark.asyncio
async def test_pa_reset_password_publishes_override_event_with_reason_per_tenant(client, mock_db, mock_kafka):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    mock_db.fetchrow.return_value = {"employee_user_id": "eu-002"}
    mock_db.fetch.return_value = [
        {"tenant_id": "tenant-001", "employee_uuid": "emp-uuid-a"},
        {"tenant_id": "tenant-002", "employee_uuid": "emp-uuid-b"},
    ]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/admin/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "9000000002", "reason_code": "SUPPORT_ESCALATION",
              "reason_note": "TCK-1234"},
    )
    temp_password = resp.json()["temp_password"]

    assert resp.status_code == 200
    assert mock_kafka.employee_event.call_count == 2
    seen_tenants = set()
    for call in mock_kafka.employee_event.call_args_list:
        event = call[0][0]
        assert event["event_type"] == "EMPLOYEE_PASSWORD_RESET"
        assert event["actor_type"] == "PORTAL_ADMIN"
        assert event["actor_id"] == "pa-uuid-777"
        assert event["reason_code"] == "SUPPORT_ESCALATION"
        assert event["reason_note"] == "TCK-1234"
        assert event["override"] is True
        assert temp_password not in str(event)
        seen_tenants.add(event["tenant_id"])
    assert seen_tenants == {"tenant-001", "tenant-002"}


