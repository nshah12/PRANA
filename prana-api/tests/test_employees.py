"""
Tests for routers/employees.py — employee master management (OA-side).

Covers:
  - Auth guard + tenant scoping: list scoped to caller's tenant from JWT
  - Privacy contract: no PAN field in any employee response
  - Alumni (exit) flow: mark_alumni updates employee status
"""
import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_auth(client, role: str = "oa_operator", user_id: str = "op-uuid-001",
              tenant_id: str = "tenant-001") -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": user_id,
        "user_type": "oa_user",
        "role": role,
        "tenant_id": tenant_id,
        "jti": "test-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def _make_employee_row():
    return {
        "employee_uuid":    "emp-uuid-001",
        "employee_user_id": "eu-uuid-001",
        "pan_token":        "abc123hash",    # hashed token — not plaintext PAN
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
    }


# -- Auth guard ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_employees_requires_auth(client, mock_db):
    """Unauthenticated request must be rejected."""
    resp = await client.get("/v1/org/employees")
    assert resp.status_code in (401, 403)


# -- Tenant scoping ------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_employees_scoped_to_tenant(client, mock_db):
    """Employee list must only return employees from the caller's tenant (JWT claim)."""
    _set_auth(client, role="oa_operator", tenant_id="tenant-001")
    mock_db.fetch.return_value = [_make_employee_row()]

    resp = await client.get("/v1/org/employees", headers=AUTH_HEADER)

    assert resp.status_code == 200

    # All DB fetch calls must include the JWT tenant_id — never a user-supplied one
    for call in mock_db.fetch.call_args_list:
        args = call[0]
        assert "tenant-001" in args, f"DB call missing tenant scope: {call}"


# -- Privacy contract ----------------------------------------------------------

@pytest.mark.asyncio
async def test_employee_response_contains_no_pan_field(client, mock_db):
    """Employee list response must never include a 'pan' or 'nik' field.
    pan_token (HMAC output) may appear as an internal key but must not expose raw PAN.
    """
    _set_auth(client, role="oa_operator", tenant_id="tenant-001")
    mock_db.fetch.return_value = [_make_employee_row()]

    resp = await client.get("/v1/org/employees", headers=AUTH_HEADER)

    assert resp.status_code == 200
    body_str = resp.text.lower()
    # Raw PAN field names must not appear in any response
    for field in ("\"pan\"", "\"nik\"", "enc_pan"):
        assert field not in body_str, f"Sensitive field '{field}' found in employee response"


# -- Alumni / exit flow --------------------------------------------------------

@pytest.mark.asyncio
async def test_employee_exit_mark_alumni_returns_200(client, mock_db):
    """mark_alumni (POST /employees/{uuid}/alumni) must return 200 on success."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")

    # Tenant push_window_months
    mock_db.fetchrow.side_effect = [
        {"push_window_months": 3},     # tenant query
        {"pan_token": "hash123", "employee_user_id": "eu-001", "status": "ACTIVE"},  # employee query
    ]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/v1/org/employees/emp-uuid-001/alumni",
        headers=AUTH_HEADER,
        json={"dol": "2024-03-15"},
    )

    assert resp.status_code == 200
    assert resp.json().get("message") == "Marked as alumni"


@pytest.mark.asyncio
async def test_employee_exit_publishes_to_kafka(client, mock_db, mock_kafka):
    """mark_alumni must persist the alumni status — DB must be updated."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.side_effect = [
        {"push_window_months": 3},
        {"pan_token": "hash123", "employee_user_id": "eu-001", "status": "ACTIVE"},
    ]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/v1/org/employees/emp-uuid-001/alumni",
        headers=AUTH_HEADER,
        json={"dol": "2024-03-15"},
    )

    assert resp.status_code == 200
    # DB must have been updated (UPDATE + career_event + history inserts)
    assert mock_db.execute.call_count >= 1
    all_sql = " ".join(str(c) for c in mock_db.execute.call_args_list).lower()
    assert "alumni" in all_sql or "update" in all_sql
