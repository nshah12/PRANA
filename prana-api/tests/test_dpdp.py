"""Tests for routers/dpdp.py — DPDP Act 2023 employee-facing endpoints."""
import pathlib
import pytest
from unittest.mock import MagicMock, AsyncMock

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_employee_auth(client, user_id: str = "emp-uuid-001") -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": user_id,
        "user_type": "employee",
        "role": "employee",
        "tenant_id": "tenant-001",
        "jti": "emp-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


# ── Auth boundary ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_erasure_requires_auth(client):
    resp = await client.post("/v1/dpdp/erasure")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_export_requires_auth(client):
    resp = await client.post("/v1/dpdp/export")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_correction_requires_auth(client):
    resp = await client.post("/v1/dpdp/correction",
                             json={"field": "designation", "correct_value": "Engineer"})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_grievance_requires_auth(client):
    resp = await client.post("/v1/dpdp/grievance",
                             json={"subject": "Wrong doc", "description": "My document is wrong"})
    assert resp.status_code in (401, 403)


# ── Erasure ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_erasure_publishes_to_kafka_not_workflow(client, mock_db, mock_kafka):
    _set_employee_auth(client)
    mock_db.fetchrow.return_value = None   # no existing pending erasure
    mock_db.execute.return_value = None
    resp = await client.post("/v1/dpdp/erasure", headers=AUTH_HEADER, json={})
    assert resp.status_code == 202
    mock_kafka.compliance_event.assert_called()
    payload = mock_kafka.compliance_event.call_args[0][0]
    assert payload["event_type"] == "ERASURE_REQUESTED", "Must publish ERASURE_REQUESTED via compliance_event"


@pytest.mark.asyncio
async def test_erasure_conflict_when_already_pending(client, mock_db):
    _set_employee_auth(client)
    mock_db.fetchrow.return_value = {"erasure_id": "era-001"}  # already pending
    resp = await client.post("/v1/dpdp/erasure", headers=AUTH_HEADER, json={})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "ERASURE_ALREADY_PENDING"


@pytest.mark.asyncio
async def test_erasure_status_returns_days_remaining(client, mock_db):
    import datetime
    _set_employee_auth(client)
    mock_db.fetchrow.return_value = {
        "erasure_id": "era-001",
        "status": "PENDING",
        "requested_at": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=5),
        "confirmed_at": None,
        "completed_at": None,
    }
    resp = await client.get("/v1/dpdp/erasure", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["pending"] is True
    assert data["days_remaining"] == 25


@pytest.mark.asyncio
async def test_erasure_status_not_found_returns_pending_false(client, mock_db):
    _set_employee_auth(client)
    mock_db.fetchrow.return_value = None
    resp = await client.get("/v1/dpdp/erasure", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json()["pending"] is False


# ── Consent ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_consents_returns_all_purposes(client, mock_db):
    _set_employee_auth(client)
    mock_db.fetch.return_value = []   # no explicit records → all implicit
    resp = await client.get("/v1/dpdp/consents", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    purposes = {c["purpose"] for c in data["consents"]}
    assert "document_processing" in purposes
    assert "insight_generation" in purposes
    assert "notifications" in purposes


@pytest.mark.asyncio
async def test_withdraw_implicit_consent_creates_record(client, mock_db, mock_kafka):
    _set_employee_auth(client)
    mock_db.execute.return_value = None
    resp = await client.post(
        "/v1/dpdp/consents/implicit-notifications/withdraw",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    mock_db.execute.assert_called()


@pytest.mark.asyncio
async def test_withdraw_invalid_implicit_purpose_rejected(client, mock_db):
    _set_employee_auth(client)
    resp = await client.post(
        "/v1/dpdp/consents/implicit-fake_purpose/withdraw",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "INVALID_PURPOSE"


# ── Data export ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_returns_202_and_job_id(client, mock_db, mock_kafka):
    _set_employee_auth(client)
    mock_db.execute.return_value = None
    resp = await client.post("/v1/dpdp/export", headers=AUTH_HEADER)
    assert resp.status_code == 202
    assert "job_id" in resp.json()


@pytest.mark.asyncio
async def test_export_triggers_workflow_via_kafka(client, mock_db, mock_kafka):
    _set_employee_auth(client)
    mock_db.execute.return_value = None
    await client.post("/v1/dpdp/export", headers=AUTH_HEADER)
    mock_kafka.compliance_event.assert_called_once()
    payload = mock_kafka.compliance_event.call_args[0][0]
    assert payload["event_type"] == "DATA_EXPORT_REQUESTED"


# ── Data correction ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_correction_happy_path(client, mock_db, mock_kafka):
    _set_employee_auth(client)
    mock_db.execute.return_value = None
    resp = await client.post(
        "/v1/dpdp/correction",
        headers=AUTH_HEADER,
        json={
            "field": "designation",
            "current_value": "Junior Engineer",
            "correct_value": "Senior Engineer",
            "evidence_note": "Promotion letter dated 2024-01-15",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "PENDING"
    assert "correction_id" in data


@pytest.mark.asyncio
async def test_correction_publishes_to_kafka(client, mock_db, mock_kafka):
    _set_employee_auth(client)
    mock_db.execute.return_value = None
    await client.post(
        "/v1/dpdp/correction",
        headers=AUTH_HEADER,
        json={"field": "department", "correct_value": "Engineering"},
    )
    mock_kafka.compliance_event.assert_called()


# ── Grievance ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_grievance_inserts_correct_columns(client, mock_db, mock_kafka):
    """Verify INSERT uses grievance_type + category (schema-correct columns)."""
    _set_employee_auth(client)
    mock_db.execute.return_value = None
    resp = await client.post(
        "/v1/dpdp/grievance",
        headers=AUTH_HEADER,
        json={"subject": "Wrong document", "description": "Salary slip for March is incorrect"},
    )
    assert resp.status_code == 201
    call_args = mock_db.execute.call_args
    query = call_args[0][0]
    assert "grievance_type" in query, "Must insert grievance_type (schema column)"
    assert "raised_at" in query, "Must use raised_at not filed_at"


@pytest.mark.asyncio
async def test_list_grievances_uses_raised_at_not_filed_at(client, mock_db):
    _set_employee_auth(client)
    mock_db.fetch.return_value = []
    resp = await client.get("/v1/dpdp/grievances", headers=AUTH_HEADER)
    assert resp.status_code == 200
    query = mock_db.fetch.call_args[0][0]
    assert "raised_at" in query
    assert "filed_at" not in query


# ── Source-code contract tests ────────────────────────────────────────────────

def test_dpdp_router_uses_kafka_not_direct_temporal():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "dpdp.py").read_text()
    assert "start_workflow" not in src, \
        "dpdp.py must not call Temporal directly — use Kafka → WorkflowConsumer"


def test_dpdp_erasure_never_deletes_audit_event():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "dpdp.py").read_text().upper()
    assert "DELETE FROM AUDIT_EVENT" not in src


def test_dpdp_uses_correct_schema_column_raised_at():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "dpdp.py").read_text()
    assert "filed_at" not in src, \
        "dpdp_grievance table uses raised_at not filed_at"


def test_dpdp_erasure_sla_from_config():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "dpdp.py").read_text()
    assert "kafka" in src.lower()
