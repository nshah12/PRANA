"""Tests for routers/labour_law.py — statutory compliance obligations."""
import pathlib
import pytest
from unittest.mock import MagicMock, AsyncMock

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_chro_auth(client, tenant_id="tenant-001"):
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "chro-uuid-001",
        "user_type": "oa_user",
        "role": "chro",
        "tenant_id": tenant_id,
        "jti": "chro-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def _set_oa_admin_auth(client, tenant_id="tenant-001"):
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "oa-admin-uuid-001",
        "user_type": "oa_user",
        "role": "oa_admin",
        "tenant_id": tenant_id,
        "jti": "oa-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


# ── Auth tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_obligations_requires_auth(client):
    resp = await client.get("/v1/compliance/statutory", headers={})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_obligation_requires_oa_admin(client):
    resp = await client.post(
        "/v1/compliance/statutory",
        json={
            "obligation_name": "EPF Filing May 2025",
            "statutory_act": "EPF_ACT",
            "deadline": "2025-06-15",
        },
        headers={},
    )
    assert resp.status_code in (401, 403)


# ── Tenant isolation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_obligations_scoped_to_tenant(client, mock_db):
    _set_chro_auth(client, tenant_id="tenant-001")
    mock_db.fetch.return_value = []
    mock_db.fetchval.return_value = 0
    resp = await client.get("/v1/compliance/statutory", headers=AUTH_HEADER)
    assert resp.status_code == 200
    call_args = mock_db.fetch.call_args
    query = call_args[0][0]
    assert "tenant_id" in query, "Query must scope by tenant_id"


# ── Happy path tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_obligations_returns_items_shape(client, mock_db):
    _set_chro_auth(client)
    mock_db.fetch.return_value = [
        {
            "obligation_id": "obl-001",
            "tenant_id": "tenant-001",
            "obligation_name": "EPF ECR Filing — May 2025",
            "statutory_act": "EPF_ACT",
            "category": None,
            "period_start": None,
            "period_end": None,
            "deadline": __import__("datetime").date(2025, 6, 15),
            "status": "PENDING",
            "filing_reference": None,
            "headcount": 42,
            "overdue_since": None,
            "document_id": None,
            "created_at": __import__("datetime").datetime(2025, 5, 1),
            "updated_at": __import__("datetime").datetime(2025, 5, 1),
        }
    ]
    mock_db.fetchval.return_value = 1
    resp = await client.get("/v1/compliance/statutory", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "total" in data
    assert data["items"][0]["statutory_act"] == "EPF_ACT"
    assert data["items"][0]["headcount"] == 42


@pytest.mark.asyncio
async def test_create_obligation_publishes_audit_event(client, mock_db, mock_kafka):
    _set_oa_admin_auth(client)
    mock_db.execute.return_value = None
    resp = await client.post(
        "/v1/compliance/statutory",
        headers=AUTH_HEADER,
        json={
            "obligation_name": "ESIC Contribution — June 2025",
            "statutory_act": "ESIC_ACT",
            "deadline": "2025-07-15",
            "period_start": "2025-06-01",
            "period_end": "2025-06-30",
            "headcount": 87,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "PENDING"
    mock_kafka.statutory_event.assert_called_once()
    payload = mock_kafka.statutory_event.call_args[0][0]
    assert payload["event_type"] == "OBLIGATION_DUE"


@pytest.mark.asyncio
async def test_create_obligation_rejects_invalid_act(client, mock_db):
    _set_oa_admin_auth(client)
    resp = await client.post(
        "/v1/compliance/statutory",
        headers=AUTH_HEADER,
        json={
            "obligation_name": "Fake Act Filing",
            "statutory_act": "FAKE_ACT",
            "deadline": "2025-07-15",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "INVALID_ACT"


_OBL_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


@pytest.mark.asyncio
async def test_update_obligation_to_complete(client, mock_db, mock_kafka):
    _set_oa_admin_auth(client)
    mock_db.fetchrow.return_value = {"obligation_id": _OBL_UUID}
    mock_db.execute.return_value = None
    resp = await client.patch(
        f"/v1/compliance/statutory/{_OBL_UUID}",
        headers=AUTH_HEADER,
        json={"status": "COMPLETE", "filing_reference": "ECR2025060001"},
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] is True


@pytest.mark.asyncio
async def test_update_obligation_404_for_wrong_tenant(client, mock_db):
    _set_oa_admin_auth(client, tenant_id="tenant-002")
    mock_db.fetchrow.return_value = None  # tenant_id mismatch → no row
    resp = await client.patch(
        f"/v1/compliance/statutory/{_OBL_UUID}",
        headers=AUTH_HEADER,
        json={"status": "COMPLETE"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_calendar_endpoint_returns_upcoming(client, mock_db):
    _set_chro_auth(client)
    mock_db.fetch.return_value = []
    resp = await client.get(
        "/v1/compliance/statutory/calendar?days=30", headers=AUTH_HEADER
    )
    assert resp.status_code == 200
    assert "items" in resp.json()


# ── Source-code contract tests ────────────────────────────────────────────────

def test_no_raw_salary_in_response():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "labour_law.py").read_text()
    # Obligation tracking must never store or return ₹ figures
    assert "payroll_total" not in src
    assert "salary_amount" not in src


def test_tenant_id_always_from_auth_not_body():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "labour_law.py").read_text()
    assert "body.tenant_id" not in src, "tenant_id must come from JWT, never request body"


def test_all_valid_indian_acts_covered():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "labour_law.py").read_text()
    for act in ["EPF_ACT", "ESIC_ACT", "INCOME_TAX", "GRATUITY_ACT", "BONUS_ACT",
                "MATERNITY_ACT", "POSH_ACT", "MIN_WAGES_ACT"]:
        assert act in src, f"VALID_ACTS must include {act}"
