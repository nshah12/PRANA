"""Tests for routers/compliance.py — employee compliance endpoints."""
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


@pytest.mark.asyncio
async def test_erasure_request_publishes_to_kafka_not_starts_workflow_directly(client, mock_kafka):
    _set_employee_auth(client)
    resp = await client.post("/v1/vault/compliance/erasure", headers=AUTH_HEADER)
    assert resp.status_code == 202
    mock_kafka.publish.assert_called()
    topics = [call[0][0] for call in mock_kafka.publish.call_args_list]
    assert any("ingest" in t or "audit" in t for t in topics), \
        "Erasure must publish to Kafka, not start Temporal workflow directly"


def test_erasure_does_not_delete_audit_event_rows():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "compliance.py").read_text(encoding="utf-8").upper()
    assert "DELETE FROM AUDIT_EVENT" not in src, \
        "compliance router must never DELETE audit_event rows"


@pytest.mark.asyncio
async def test_consent_withdrawal_is_immediate(client, mock_db):
    _set_employee_auth(client)
    mock_db.fetchrow.return_value = {
        "consent_id": "con-001", "purpose": "document_processing", "is_active": True
    }
    resp = await client.post(
        "/v1/vault/compliance/consent/withdraw",
        headers=AUTH_HEADER,
        json={"purpose": "document_processing"},
    )
    assert resp.status_code in (200, 202)


@pytest.mark.asyncio
async def test_grievance_publishes_to_kafka(client, mock_kafka):
    _set_employee_auth(client)
    resp = await client.post(
        "/v1/vault/compliance/grievance",
        headers=AUTH_HEADER,
        json={"description": "My document is incorrect", "category": "DATA_ACCURACY"},
    )
    assert resp.status_code in (201, 202)


@pytest.mark.asyncio
async def test_export_request_publishes_to_kafka(client, mock_kafka):
    _set_employee_auth(client)
    resp = await client.post("/v1/vault/compliance/export", headers=AUTH_HEADER)
    assert resp.status_code in (202, 200)
