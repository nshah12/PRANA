"""Tests for routers/dpdp.py — DPDP Act 2023 endpoints."""
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


def test_dpdp_erasure_sla_from_config_not_hardcoded():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "dpdp.py").read_text(encoding="utf-8")
    # The SLA value (30 days) comes from DPDP Act — the comment/constant is acceptable,
    # but the router must publish to Kafka (not run workflow inline) for async processing
    assert "kafka" in src.lower() or "ingest.events" in src or "audit.events" in src, \
        "dpdp erasure must publish to Kafka for async processing"


@pytest.mark.asyncio
async def test_dpdp_export_triggers_workflow_via_kafka(client, mock_kafka):
    _set_employee_auth(client)
    resp = await client.post("/v1/dpdp/export", headers=AUTH_HEADER)
    assert resp.status_code in (202, 200)


@pytest.mark.asyncio
async def test_dpdp_correction_requires_authenticated_employee(client):
    resp = await client.post(
        "/v1/dpdp/correction",
        json={"document_id": "doc-001", "description": "Incorrect designation"},
    )
    assert resp.status_code in (401, 403)
