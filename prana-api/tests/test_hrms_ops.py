"""
RED tests for:
  POST /v1/hrms/config/{id}/test  — live connection test
  POST /v1/hrms/config/{id}/sync  — manual sync trigger (fires HRMSSyncWorkflow)

Rules:
  - Both require OA-Admin role
  - tenant_id from JWT, never from request
  - test: calls adapter.test_connection() → 200 {ok: true/false}
  - sync: starts HRMSSyncWorkflow via Temporal → 202 {workflow_id}
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

TENANT_ID    = UUID("b0000000-0000-0000-0000-000000000001")
CONNECTOR_ID = uuid4()


def _oa_admin_headers(client):
    """Inject OA-Admin JWT claims."""
    from unittest.mock import AsyncMock as AM
    jwt = client.app.state.jwt_service
    jwt.decode.return_value = {
        "sub":       str(uuid4()),
        "user_type": "oa_user",
        "role":      "OA-Admin",
        "tenant_id": str(TENANT_ID),
        "jti":       "oa-session-ops-001",
        "exp":       9999999999,
    }
    jwt.is_revoked = AM(return_value=False)
    return {"Authorization": "Bearer fake.oa.admin.jwt"}


MOCK_CONFIG = {
    "connector_id":    str(CONNECTOR_ID),
    "tenant_id":       str(TENANT_ID),
    "connector_key":   "darwinbox",
    "status":          "ACTIVE",
    "enc_credentials": b"enc",
    "kek_arn":         "arn:aws:kms:ap-south-1:123:key/test",
    "field_mapping":   {},
}


# ── test-connection ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_connection_success(client):
    """POST /v1/hrms/config/{id}/test → {ok: true} when adapter.test_connection() returns True."""
    mock_adapter = AsyncMock()
    mock_adapter.test_connection = AsyncMock(return_value=True)

    with patch("routers.hrms_config.HRMSSyncService") as MockSvc, \
         patch("boto3.client"):
        mock_svc = MockSvc.return_value
        mock_svc.load_connector_config = AsyncMock(return_value=MOCK_CONFIG)
        mock_svc.build_adapter = MagicMock(return_value=mock_adapter)

        resp = await client.post(
            f"/v1/hrms/config/{CONNECTOR_ID}/test",
            headers=_oa_admin_headers(client),
        )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_connection_failure(client):
    """POST /v1/hrms/config/{id}/test → {ok: false} when adapter.test_connection() returns False."""
    mock_adapter = AsyncMock()
    mock_adapter.test_connection = AsyncMock(return_value=False)

    with patch("routers.hrms_config.HRMSSyncService") as MockSvc, \
         patch("boto3.client"):
        mock_svc = MockSvc.return_value
        mock_svc.load_connector_config = AsyncMock(return_value=MOCK_CONFIG)
        mock_svc.build_adapter = MagicMock(return_value=mock_adapter)

        resp = await client.post(
            f"/v1/hrms/config/{CONNECTOR_ID}/test",
            headers=_oa_admin_headers(client),
        )

    assert resp.status_code == 200
    assert resp.json()["ok"] is False


@pytest.mark.asyncio
async def test_connection_unknown_connector_404(client):
    """Cannot test a connector that doesn't belong to this tenant."""
    with patch("routers.hrms_config.HRMSSyncService") as MockSvc:
        mock_svc = MockSvc.return_value
        mock_svc.load_connector_config = AsyncMock(return_value=None)

        resp = await client.post(
            f"/v1/hrms/config/{uuid4()}/test",
            headers=_oa_admin_headers(client),
        )

    assert resp.status_code == 404


# ── manual sync trigger ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_trigger_returns_202(client):
    """POST /v1/hrms/config/{id}/sync → 202 with workflow_id."""
    client.app.state.temporal_client = AsyncMock()
    with patch("routers.hrms_config.HRMSSyncService") as MockSvc:
        mock_svc = MockSvc.return_value
        mock_svc.load_connector_config = AsyncMock(return_value=MOCK_CONFIG)

        resp = await client.post(
            f"/v1/hrms/config/{CONNECTOR_ID}/sync",
            headers=_oa_admin_headers(client),
        )

    assert resp.status_code == 202
    assert "workflow_id" in resp.json()


@pytest.mark.asyncio
async def test_sync_trigger_starts_temporal_workflow(client):
    """Sync trigger must start HRMSSyncWorkflow via Temporal — not in HTTP path."""
    client.app.state.temporal_client = AsyncMock()
    with patch("routers.hrms_config.HRMSSyncService") as MockSvc:
        mock_svc = MockSvc.return_value
        mock_svc.load_connector_config = AsyncMock(return_value=MOCK_CONFIG)

        await client.post(
            f"/v1/hrms/config/{CONNECTOR_ID}/sync",
            headers=_oa_admin_headers(client),
        )

    client.app.state.temporal_client.start_workflow.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_trigger_paused_returns_409(client):
    """Cannot trigger sync on a PAUSED connector."""
    paused_config = {**MOCK_CONFIG, "status": "PAUSED"}
    with patch("routers.hrms_config.HRMSSyncService") as MockSvc:
        mock_svc = MockSvc.return_value
        mock_svc.load_connector_config = AsyncMock(return_value=paused_config)

        resp = await client.post(
            f"/v1/hrms/config/{CONNECTOR_ID}/sync",
            headers=_oa_admin_headers(client),
        )

    assert resp.status_code == 409
