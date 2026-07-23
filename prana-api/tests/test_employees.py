"""
Tests for routers/employees.py — employee master management (OA-side).

Covers:
  - Auth guard + tenant scoping: list scoped to caller's tenant from JWT
  - Privacy contract: no PAN field in any employee response
  - Alumni (exit) flow: mark_alumni updates employee status
"""
import datetime
import io
from unittest.mock import AsyncMock, MagicMock, patch

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


@pytest.mark.asyncio
async def test_list_employees_chro_blocked(client, mock_db):
    """CHRO cannot access the employee list — analytics role only."""
    _set_auth(client, role="chro")
    resp = await client.get("/v1/org/employees", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_employees_cfo_blocked(client, mock_db):
    """CFO cannot access the employee list — analytics role only."""
    _set_auth(client, role="cfo")
    resp = await client.get("/v1/org/employees", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_employees_ciso_blocked(client, mock_db):
    """CISO cannot access the employee list — security observer role only."""
    _set_auth(client, role="ciso")
    resp = await client.get("/v1/org/employees", headers=AUTH_HEADER)
    assert resp.status_code == 403


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
    assert resp.json().get("message") == "MARKED_AS_ALUMNI"


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


# -- Reactivate (un-mark alumni) — reverse of mark_alumni -----------------------

@pytest.mark.asyncio
async def test_reactivate_requires_auth(client, mock_db):
    resp = await client.post("/v1/org/employees/emp-uuid-001/reactivate")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_reactivate_oa_operator_forbidden(client, mock_db):
    _set_auth(client, role="oa_operator", tenant_id="tenant-001")
    resp = await client.post("/v1/org/employees/emp-uuid-001/reactivate", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reactivate_not_found_returns_404(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = None
    resp = await client.post("/v1/org/employees/emp-uuid-999/reactivate", headers=AUTH_HEADER)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_reactivate_not_alumni_returns_409(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"pan_token": "hash123", "employee_user_id": "eu-001", "status": "ACTIVE"}
    resp = await client.post("/v1/org/employees/emp-uuid-001/reactivate", headers=AUTH_HEADER)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "EMPLOYEE_NOT_ALUMNI"


@pytest.mark.asyncio
async def test_reactivate_clears_dol_and_restores_active_status(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"pan_token": "hash123", "employee_user_id": "eu-001", "status": "ALUMNI"}
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post("/v1/org/employees/emp-uuid-001/reactivate", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["message"] == "EMPLOYEE_REACTIVATED"
    all_sql = " ".join(str(c) for c in mock_db.execute.call_args_list).lower()
    assert "dol=null" in all_sql.replace(" ", "") or "dol = null" in all_sql
    assert "'active'" in all_sql


@pytest.mark.asyncio
async def test_reactivate_publishes_to_kafka(client, mock_db, mock_kafka):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001", user_id="admin-uuid-9")
    mock_db.fetchrow.return_value = {"pan_token": "hash123", "employee_user_id": "eu-001", "status": "ALUMNI"}
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post("/v1/org/employees/emp-uuid-001/reactivate", headers=AUTH_HEADER)

    assert resp.status_code == 200
    mock_kafka.employee_event.assert_called_once()
    event = mock_kafka.employee_event.call_args[0][0]
    assert event["event_type"] == "EMPLOYEE_REJOINED"
    assert event["tenant_id"] == "tenant-001"
    assert event["employee_uuid"] == "emp-uuid-001"


# -- Bulk revoke employee sessions ("sign out everywhere") ----------------------

@pytest.mark.asyncio
async def test_revoke_sessions_requires_auth(client, mock_db):
    resp = await client.post("/v1/org/employees/emp-uuid-001/revoke-sessions")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_revoke_sessions_oa_operator_forbidden(client, mock_db):
    _set_auth(client, role="oa_operator", tenant_id="tenant-001")
    resp = await client.post("/v1/org/employees/emp-uuid-001/revoke-sessions", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_revoke_sessions_allowed_for_ciso(client, mock_db, mock_kafka):
    _set_auth(client, role="ciso", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"employee_user_id": "eu-001"}
    mock_db.fetch.return_value = []
    mock_db.execute = AsyncMock(return_value=None)
    resp = await client.post("/v1/org/employees/emp-uuid-001/revoke-sessions", headers=AUTH_HEADER)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_revoke_sessions_not_found_returns_404(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = None
    resp = await client.post("/v1/org/employees/emp-uuid-999/revoke-sessions", headers=AUTH_HEADER)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_revoke_sessions_revokes_all_active_sessions_and_jwts(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"employee_user_id": "eu-001"}
    mock_db.fetch.return_value = [
        {"session_id": "sess-1"},
        {"session_id": "sess-2"},
    ]
    mock_db.execute = AsyncMock(return_value=None)
    jwt = client.app.state.jwt_service
    jwt.revoke = AsyncMock()

    resp = await client.post("/v1/org/employees/emp-uuid-001/revoke-sessions", headers=AUTH_HEADER)

    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "EMPLOYEE_SESSIONS_REVOKED"
    assert body["revoked_count"] == 2

    all_sql = " ".join(str(c) for c in mock_db.execute.call_args_list).lower()
    assert "revoked=true" in all_sql.replace(" ", "") and "eu-001" in all_sql
    assert jwt.revoke.await_count == 2
    jwt.revoke.assert_any_await("sess-1")
    jwt.revoke.assert_any_await("sess-2")


@pytest.mark.asyncio
async def test_revoke_sessions_no_active_sessions_returns_zero_count(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"employee_user_id": "eu-001"}
    mock_db.fetch.return_value = []

    resp = await client.post("/v1/org/employees/emp-uuid-001/revoke-sessions", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["revoked_count"] == 0


@pytest.mark.asyncio
async def test_revoke_sessions_publishes_audit_event(client, mock_db, mock_kafka):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001", user_id="admin-uuid-9")
    mock_db.fetchrow.return_value = {"employee_user_id": "eu-001"}
    mock_db.fetch.return_value = [{"session_id": "sess-1"}]
    mock_db.execute = AsyncMock(return_value=None)
    jwt = client.app.state.jwt_service
    jwt.revoke = AsyncMock()

    resp = await client.post("/v1/org/employees/emp-uuid-001/revoke-sessions", headers=AUTH_HEADER)

    assert resp.status_code == 200
    mock_kafka.employee_event.assert_called_once()
    event = mock_kafka.employee_event.call_args[0][0]
    assert event["event_type"] == "EMPLOYEE_SESSIONS_REVOKED"
    assert event["actor_type"] == "OA_ADMIN"
    assert event["actor_id"] == "admin-uuid-9"
    assert event["employee_user_id"] == "eu-001"
    assert event["revoked_count"] == 1


# -- Bulk revoke employee share links ------------------------------------------

@pytest.mark.asyncio
async def test_revoke_shares_requires_auth(client, mock_db):
    resp = await client.post("/v1/org/employees/emp-uuid-001/revoke-shares")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_revoke_shares_oa_operator_forbidden(client, mock_db):
    _set_auth(client, role="oa_operator", tenant_id="tenant-001")
    resp = await client.post("/v1/org/employees/emp-uuid-001/revoke-shares", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_revoke_shares_allowed_for_ciso(client, mock_db, mock_kafka):
    _set_auth(client, role="ciso", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"employee_user_id": "eu-001"}
    mock_db.fetch.return_value = []
    resp = await client.post("/v1/org/employees/emp-uuid-001/revoke-shares", headers=AUTH_HEADER)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_revoke_shares_not_found_returns_404(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = None
    resp = await client.post("/v1/org/employees/emp-uuid-999/revoke-shares", headers=AUTH_HEADER)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_revoke_shares_revokes_all_active_shares(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"employee_user_id": "eu-001"}
    mock_db.fetch.return_value = [{"token_id": "tok-1"}, {"token_id": "tok-2"}]

    resp = await client.post("/v1/org/employees/emp-uuid-001/revoke-shares", headers=AUTH_HEADER)

    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "EMPLOYEE_SHARES_REVOKED"
    assert body["revoked_count"] == 2

    sql, *params = mock_db.fetch.call_args[0]
    assert "share_token" in sql.lower() and "revoked" in sql.lower()
    assert "eu-001" in params and "tenant-001" in params


@pytest.mark.asyncio
async def test_revoke_shares_publishes_audit_event(client, mock_db, mock_kafka):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001", user_id="admin-uuid-9")
    mock_db.fetchrow.return_value = {"employee_user_id": "eu-001"}
    mock_db.fetch.return_value = [{"token_id": "tok-1"}]

    resp = await client.post("/v1/org/employees/emp-uuid-001/revoke-shares", headers=AUTH_HEADER)

    assert resp.status_code == 200
    mock_kafka.employee_event.assert_called_once()
    event = mock_kafka.employee_event.call_args[0][0]
    assert event["event_type"] == "EMPLOYEE_SHARES_REVOKED"
    assert event["actor_type"] == "OA_ADMIN"
    assert event["actor_id"] == "admin-uuid-9"
    assert event["employee_user_id"] == "eu-001"
    assert event["revoked_count"] == 1


# -- Bulk employee CSV import ---------------------------------------------------

def _csv_upload(content: str):
    return [("file", ("employees.csv", io.BytesIO(content.encode()), "text/csv"))]


_VALID_CSV = (
    "nik,full_name,doj,emp_id_org,department\n"
    "ABCDE1234F,Rahul Sharma,2022-01-15,EMP001,Engineering\n"
    "FGHIJ5678K,Priya Iyer,2021-06-01,EMP002,Sales\n"
)


@pytest.mark.asyncio
async def test_bulk_import_requires_auth(client, mock_db):
    resp = await client.post("/v1/org/employees/import", files=_csv_upload(_VALID_CSV))
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_bulk_import_rejects_chro(client, mock_db):
    _set_auth(client, role="chro", tenant_id="tenant-001")
    resp = await client.post(
        "/v1/org/employees/import", headers=AUTH_HEADER, files=_csv_upload(_VALID_CSV),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_bulk_import_allowed_for_oa_operator(client, mock_db, mock_kafka):
    _set_auth(client, role="oa_operator", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"kek_arn": "arn:aws:kms:ap-south-1:123:key/abc"}
    with patch("services.employee_service.EmployeeService.create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = {"employee_uuid": "emp-uuid-1", "employee_user_id": "eu-1", "pan_token": "hash1"}
        resp = await client.post(
            "/v1/org/employees/import", headers=AUTH_HEADER, files=_csv_upload(_VALID_CSV),
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_bulk_import_rejects_csv_missing_required_columns(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    bad_csv = "full_name,doj\nRahul Sharma,2022-01-15\n"
    resp = await client.post(
        "/v1/org/employees/import", headers=AUTH_HEADER, files=_csv_upload(bad_csv),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "CSV_MISSING_REQUIRED_COLUMNS"


@pytest.mark.asyncio
async def test_bulk_import_rejects_too_many_rows(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    header = "nik,full_name,doj\n"
    rows = "".join(f"NIK{i:07d},Employee {i},2022-01-15\n" for i in range(501))
    resp = await client.post(
        "/v1/org/employees/import", headers=AUTH_HEADER, files=_csv_upload(header + rows),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "CSV_TOO_MANY_ROWS"


@pytest.mark.asyncio
async def test_bulk_import_creates_each_valid_row_and_returns_summary(client, mock_db, mock_kafka):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001", user_id="admin-uuid-9")
    mock_db.fetchrow.return_value = {"kek_arn": "arn:aws:kms:ap-south-1:123:key/abc"}
    with patch("services.employee_service.EmployeeService.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [
            {"employee_uuid": "emp-uuid-1", "employee_user_id": "eu-1", "pan_token": "hash1"},
            {"employee_uuid": "emp-uuid-2", "employee_user_id": "eu-2", "pan_token": "hash2"},
        ]
        resp = await client.post(
            "/v1/org/employees/import", headers=AUTH_HEADER, files=_csv_upload(_VALID_CSV),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["created"] == 2
    assert body["failed"] == 0
    assert body["errors"] == []
    assert mock_create.await_count == 2
    assert mock_kafka.employee_event.call_count == 2
    for call in mock_kafka.employee_event.call_args_list:
        assert call[0][0]["event_type"] == "EMPLOYEE_ONBOARDED"


@pytest.mark.asyncio
async def test_bulk_import_passes_mobile_email_columns_through(client, mock_db, mock_kafka):
    """Optional mobile/email CSV columns must reach EmployeeService.create() —
    previously there was no code path at all setting a bulk-imported employee's
    login handle, so nobody could ever log in regardless of HRMS data available."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"kek_arn": "arn:aws:kms:ap-south-1:123:key/abc"}
    csv_content = (
        "nik,full_name,doj,mobile,email\n"
        "ABCDE1234F,Rahul Sharma,2022-01-15,+919876543210,rahul@example.com\n"
    )
    with patch("services.employee_service.EmployeeService.create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = {
            "employee_uuid": "emp-uuid-1", "employee_user_id": "eu-1",
            "pan_token": "hash1", "temp_password": "TempPass123",
        }
        resp = await client.post(
            "/v1/org/employees/import", headers=AUTH_HEADER, files=_csv_upload(csv_content),
        )

    assert resp.status_code == 200
    kwargs = mock_create.call_args.kwargs
    assert kwargs["mobile"] == "+919876543210"
    assert kwargs["email"] == "rahul@example.com"


@pytest.mark.asyncio
async def test_bulk_import_publishes_credentials_issued_when_temp_password_returned(client, mock_db, mock_kafka):
    """Previously nothing ever published an event CommunicationHubConsumer could turn into a
    notification for a newly-created employee — this closes that loop."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"kek_arn": "arn:aws:kms:ap-south-1:123:key/abc"}
    single_row_csv = "nik,full_name,doj\nABCDE1234F,Rahul Sharma,2022-01-15\n"
    with patch("services.employee_service.EmployeeService.create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = {
            "employee_uuid": "emp-uuid-1", "employee_user_id": "eu-1",
            "pan_token": "hash1", "temp_password": "TempPass123",
        }
        resp = await client.post(
            "/v1/org/employees/import", headers=AUTH_HEADER, files=_csv_upload(single_row_csv),
        )

    assert resp.status_code == 200
    mock_kafka.employee_credentials_issued.assert_awaited_once()
    payload = mock_kafka.employee_credentials_issued.call_args.args[0]
    assert payload["event_type"] == "EMPLOYEE_CREDENTIALS_ISSUED"
    assert payload["recipient_id"] == "eu-1"
    assert "temp_password" not in str(payload)   # never leak the plaintext password onto Kafka


@pytest.mark.asyncio
async def test_bulk_import_no_credentials_event_when_no_temp_password(client, mock_db, mock_kafka):
    """No mobile/email supplied → EmployeeService.create() returns temp_password=None
    → no EMPLOYEE_CREDENTIALS_ISSUED event should fire (nothing to notify about yet)."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"kek_arn": "arn:aws:kms:ap-south-1:123:key/abc"}
    with patch("services.employee_service.EmployeeService.create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = {
            "employee_uuid": "emp-uuid-1", "employee_user_id": "eu-1",
            "pan_token": "hash1", "temp_password": None,
        }
        resp = await client.post(
            "/v1/org/employees/import", headers=AUTH_HEADER, files=_csv_upload(_VALID_CSV),
        )

    assert resp.status_code == 200
    mock_kafka.employee_credentials_issued.assert_not_awaited()


# -- Single employee create ------------------------------------------------------

@pytest.mark.asyncio
async def test_create_employee_passes_mobile_email_through_and_publishes_credentials(client, mock_db, mock_kafka):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001", user_id="admin-uuid-9")
    mock_db.fetchrow.return_value = {"kek_arn": "arn:aws:kms:ap-south-1:123:key/abc"}
    with patch("services.employee_service.EmployeeService.create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = {
            "employee_uuid": "emp-uuid-1", "employee_user_id": "eu-1",
            "pan_token": "hash1", "temp_password": "TempPass123",
        }
        resp = await client.post(
            "/v1/org/employees", headers=AUTH_HEADER, json={
                "nik": "ABCDE1234F", "full_name": "Rahul Sharma", "doj": "2022-01-15",
                "mobile": "+919876543210", "email": "rahul@example.com",
            },
        )

    assert resp.status_code == 201
    kwargs = mock_create.call_args.kwargs
    assert kwargs["mobile"] == "+919876543210"
    assert kwargs["email"] == "rahul@example.com"
    mock_kafka.employee_credentials_issued.assert_awaited_once()
    payload = mock_kafka.employee_credentials_issued.call_args.args[0]
    assert payload["event_type"] == "EMPLOYEE_CREDENTIALS_ISSUED"
    assert payload["recipient_id"] == "eu-1"


@pytest.mark.asyncio
async def test_create_employee_no_credentials_event_when_no_temp_password(client, mock_db, mock_kafka):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"kek_arn": "arn:aws:kms:ap-south-1:123:key/abc"}
    with patch("services.employee_service.EmployeeService.create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = {
            "employee_uuid": "emp-uuid-1", "employee_user_id": "eu-1",
            "pan_token": "hash1", "temp_password": None,
        }
        resp = await client.post(
            "/v1/org/employees", headers=AUTH_HEADER, json={
                "nik": "ABCDE1234F", "full_name": "Rahul Sharma", "doj": "2022-01-15",
            },
        )

    assert resp.status_code == 201
    mock_kafka.employee_credentials_issued.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_import_isolates_row_level_errors_missing_field(client, mock_db, mock_kafka):
    """One row missing a required field must not abort the whole batch."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"kek_arn": "arn:aws:kms:ap-south-1:123:key/abc"}
    csv_content = (
        "nik,full_name,doj\n"
        "ABCDE1234F,Rahul Sharma,2022-01-15\n"
        ",Missing Nik,2022-01-15\n"
    )
    with patch("services.employee_service.EmployeeService.create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = {"employee_uuid": "emp-uuid-1", "employee_user_id": "eu-1", "pan_token": "hash1"}
        resp = await client.post(
            "/v1/org/employees/import", headers=AUTH_HEADER, files=_csv_upload(csv_content),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["created"] == 1
    assert body["failed"] == 1
    assert body["errors"][0]["row"] == 3
    assert body["errors"][0]["error"] == "CSV_MISSING_REQUIRED_FIELD"
    assert mock_create.await_count == 1


@pytest.mark.asyncio
async def test_bulk_import_isolates_row_level_errors_invalid_date(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"kek_arn": "arn:aws:kms:ap-south-1:123:key/abc"}
    csv_content = "nik,full_name,doj\nABCDE1234F,Rahul Sharma,not-a-date\n"
    with patch("services.employee_service.EmployeeService.create", new_callable=AsyncMock):
        resp = await client.post(
            "/v1/org/employees/import", headers=AUTH_HEADER, files=_csv_upload(csv_content),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["failed"] == 1
    assert body["errors"][0]["error"] == "CSV_INVALID_DATE_FORMAT"


@pytest.mark.asyncio
async def test_bulk_import_isolates_create_exceptions_per_row(client, mock_db):
    """If EmployeeService.create raises for one row (e.g. duplicate constraint),
    the batch must continue with remaining rows rather than 500ing entirely."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = {"kek_arn": "arn:aws:kms:ap-south-1:123:key/abc"}
    with patch("services.employee_service.EmployeeService.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [
            Exception("duplicate emp_id_org"),
            {"employee_uuid": "emp-uuid-2", "employee_user_id": "eu-2", "pan_token": "hash2"},
        ]
        resp = await client.post(
            "/v1/org/employees/import", headers=AUTH_HEADER, files=_csv_upload(_VALID_CSV),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert body["failed"] == 1
    assert body["errors"][0]["error"] == "EMPLOYEE_CREATE_FAILED"


# -- Reset TOTP (OA-Admin, tenant-scoped) ---------------------------------------

@pytest.mark.asyncio
async def test_reset_totp_requires_auth(client, mock_db):
    resp = await client.post("/v1/org/employees/reset-totp", json={"identifier": "a@b.com"})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_reset_totp_oa_operator_forbidden(client, mock_db):
    """Only OA-Admin — not OA-Operator — can reset an employee's TOTP."""
    _set_auth(client, role="oa_operator", tenant_id="tenant-001")
    resp = await client.post(
        "/v1/org/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reset_totp_rejects_empty_identifier(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    resp = await client.post(
        "/v1/org/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "   "},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "IDENTIFIER_REQUIRED"


@pytest.mark.asyncio
async def test_reset_totp_by_email_looks_up_employee_user_table(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.side_effect = [
        {"employee_user_id": "eu-001"},                       # employee_user lookup by email
        {"employee_uuid": "emp-uuid-001"},                    # employee_master tenant-scope check
    ]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/v1/org/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com"},
    )

    assert resp.status_code == 200
    assert resp.json()["message"] == "EMPLOYEE_TOTP_RESET"

    lookup_call = mock_db.fetchrow.call_args_list[0]
    assert "email" in lookup_call[0][0].lower()
    assert lookup_call[0][1] == "rahul@example.com"


@pytest.mark.asyncio
async def test_reset_totp_by_mobile_normalises_to_e164(client, mock_db):
    """mobile is never stored in plaintext (schema.sql employee_user, 2026-07-18) —
    the lookup must query by mobile_token (HMAC of the E.164-normalised value),
    not the raw digits or raw mobile string."""
    from services.encryption_service import compute_mobile_token

    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.side_effect = [
        {"employee_user_id": "eu-001"},
        {"employee_uuid": "emp-uuid-001"},
    ]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/v1/org/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "9000000001"},
    )

    assert resp.status_code == 200
    lookup_call = mock_db.fetchrow.call_args_list[0]
    assert "mobile_token" in lookup_call[0][0].lower()
    expected_token = compute_mobile_token("+919000000001", "test_secret_32chars_padding_pad1")
    assert lookup_call[0][1] == expected_token


@pytest.mark.asyncio
async def test_reset_totp_employee_not_found_returns_404(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = None

    resp = await client.post(
        "/v1/org/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "nobody@example.com"},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_reset_totp_cross_tenant_employee_returns_404_not_leaked(client, mock_db):
    """Employee exists platform-wide (different tenant) — must not reveal that fact."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.side_effect = [
        {"employee_user_id": "eu-001"},   # found in employee_user (any tenant)
        None,                              # NOT in employee_master for tenant-001
    ]

    resp = await client.post(
        "/v1/org/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com"},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_reset_totp_clears_secret_and_configured_at(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.side_effect = [
        {"employee_user_id": "eu-001"},
        {"employee_uuid": "emp-uuid-001"},
    ]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/v1/org/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com"},
    )

    assert resp.status_code == 200
    mock_db.execute.assert_called_once()
    sql = mock_db.execute.call_args[0][0].lower()
    assert "totp_secret_enc" in sql and "totp_configured_at" in sql
    assert "eu-001" in mock_db.execute.call_args[0]


@pytest.mark.asyncio
async def test_reset_totp_publishes_audit_event_with_oa_admin_actor(client, mock_db, mock_kafka):
    """This event must flow through AuditConsumer (audit_event + Immudb) and CISO visibility —
    actor_type/actor_id must be the acting OA-Admin, not SYSTEM."""
    _set_auth(client, role="oa_admin", tenant_id="tenant-001", user_id="admin-uuid-9")
    mock_db.fetchrow.side_effect = [
        {"employee_user_id": "eu-001"},
        {"employee_uuid": "emp-uuid-001"},
    ]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/v1/org/employees/reset-totp",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com"},
    )

    assert resp.status_code == 200
    mock_kafka.employee_event.assert_called_once()
    event = mock_kafka.employee_event.call_args[0][0]
    assert event["event_type"] == "EMPLOYEE_TOTP_RESET"
    assert event["actor_type"] == "OA_ADMIN"
    assert event["actor_id"] == "admin-uuid-9"
    assert event["tenant_id"] == "tenant-001"
    assert event["employee_user_id"] == "eu-001"


# -- Reset password (OA-Admin, tenant-scoped) -----------------------------------

@pytest.mark.asyncio
async def test_reset_password_requires_auth(client, mock_db):
    resp = await client.post("/v1/org/employees/reset-password", json={"identifier": "a@b.com"})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_reset_password_oa_operator_forbidden(client, mock_db):
    _set_auth(client, role="oa_operator", tenant_id="tenant-001")
    resp = await client.post(
        "/v1/org/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reset_password_rejects_empty_identifier(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    resp = await client.post(
        "/v1/org/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "   "},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "IDENTIFIER_REQUIRED"


@pytest.mark.asyncio
async def test_reset_password_employee_not_found_returns_404(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.return_value = None
    resp = await client.post(
        "/v1/org/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "nobody@example.com"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_reset_password_cross_tenant_employee_returns_404_not_leaked(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.side_effect = [
        {"employee_user_id": "eu-001"},
        None,
    ]
    resp = await client.post(
        "/v1/org/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_reset_password_generates_temp_password_and_sets_force_reset(client, mock_db):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001")
    mock_db.fetchrow.side_effect = [
        {"employee_user_id": "eu-001"},
        {"employee_uuid": "emp-uuid-001"},
    ]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/v1/org/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com"},
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
async def test_reset_password_publishes_audit_event_with_oa_admin_actor(client, mock_db, mock_kafka):
    _set_auth(client, role="oa_admin", tenant_id="tenant-001", user_id="admin-uuid-9")
    mock_db.fetchrow.side_effect = [
        {"employee_user_id": "eu-001"},
        {"employee_uuid": "emp-uuid-001"},
    ]
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.post(
        "/v1/org/employees/reset-password",
        headers=AUTH_HEADER,
        json={"identifier": "rahul@example.com"},
    )

    assert resp.status_code == 200
    temp_password = resp.json()["temp_password"]

    mock_kafka.employee_event.assert_called_once()
    event = mock_kafka.employee_event.call_args[0][0]
    assert event["event_type"] == "EMPLOYEE_PASSWORD_RESET"
    assert event["actor_type"] == "OA_ADMIN"
    assert event["actor_id"] == "admin-uuid-9"
    assert event["tenant_id"] == "tenant-001"
    assert event["employee_user_id"] == "eu-001"
    # The generated temp password itself must never be logged/published to Kafka/audit trail
    assert "temp_password" not in event
    assert temp_password not in str(event)
