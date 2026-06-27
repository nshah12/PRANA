"""
RED tests for POST /v1/hrms/webhook/{connector_id}.

Webhook contract:
  1. Validate HMAC-SHA256 signature from X-PRANA-Webhook-Sig header
  2. Load connector config to find tenant_id + connector_key + webhook_secret
  3. Build adapter, call handle_webhook(payload)
  4. Publish HRMS_EMPLOYEE_SYNCED per returned employee record
  5. Return 200 {"received": true} immediately

Tests verify:
  - Valid signature + known connector → 200 + events published
  - Bad/missing signature → 401
  - Unknown connector_id → 404
  - Events published use kafka.employee_event() domain helper
"""
import hashlib
import hmac
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

TENANT_ID      = UUID("b0000000-0000-0000-0000-000000000001")
CONNECTOR_ID   = uuid4()
WEBHOOK_SECRET = "test_webhook_secret_32_chars_xx"

WEBHOOK_PAYLOAD = {
    "event":       "EMPLOYEE_UPDATED",
    "employee_id": "EMP001",
    "changed_at":  "2026-06-27T10:00:00Z",
    "fields":      {"designation": "Senior Engineer"},
}

MOCK_CONFIG = {
    "connector_id":    str(CONNECTOR_ID),
    "tenant_id":       TENANT_ID,
    "connector_key":   "darwinbox",
    "status":          "ACTIVE",
    "enc_credentials": b"enc",
    "kek_arn":         "arn:aws:kms:ap-south-1:123:key/test",
    "field_mapping":   {},
    "webhook_secret":  WEBHOOK_SECRET,
}

MOCK_EVENTS = [{"event_type": "EMPLOYEE_UPDATED", "employee_id": "EMP001",
                "designation": "Senior Engineer"}]


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def mock_kafka():
    kafka = AsyncMock()
    kafka.employee_event = AsyncMock()
    return kafka


@pytest.fixture
def mock_db():
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    cm   = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__  = AsyncMock(return_value=False)
    pool.acquire  = MagicMock(return_value=cm)
    return pool


@pytest.fixture
def client(mock_db, mock_kafka):
    from httpx import AsyncClient
    from main import app

    app.state.db_pool        = mock_db
    app.state.kafka_producer = mock_kafka
    return AsyncClient(app=app, base_url="http://test")


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_valid_signature_returns_200(client):
    body = json.dumps(WEBHOOK_PAYLOAD).encode()
    sig  = _sign(body, WEBHOOK_SECRET)

    mock_adapter = MagicMock()
    mock_adapter.handle_webhook = MagicMock(return_value=MOCK_EVENTS)

    with patch("routers.hrms_webhook._load_config_with_secret",
               new=AsyncMock(return_value=MOCK_CONFIG)), \
         patch("routers.hrms_webhook._get_svc") as mock_get_svc, \
         patch("boto3.client"):
        mock_svc = MagicMock()
        mock_svc.build_adapter = MagicMock(return_value=mock_adapter)
        mock_get_svc.return_value = mock_svc

        async with client as c:
            resp = await c.post(
                f"/v1/hrms/webhook/{CONNECTOR_ID}",
                content=body,
                headers={
                    "Content-Type":          "application/json",
                    "X-PRANA-Webhook-Sig":   sig,
                },
            )

    assert resp.status_code == 200
    assert resp.json()["received"] is True


@pytest.mark.asyncio
async def test_webhook_bad_signature_returns_401(client):
    body = json.dumps(WEBHOOK_PAYLOAD).encode()

    with patch("routers.hrms_webhook._load_config_with_secret",
               new=AsyncMock(return_value=MOCK_CONFIG)):
        async with client as c:
            resp = await c.post(
                f"/v1/hrms/webhook/{CONNECTOR_ID}",
                content=body,
                headers={
                    "Content-Type":        "application/json",
                    "X-PRANA-Webhook-Sig": "bad_signature",
                },
            )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_missing_signature_returns_401(client):
    body = json.dumps(WEBHOOK_PAYLOAD).encode()

    async with client as c:
        resp = await c.post(
            f"/v1/hrms/webhook/{CONNECTOR_ID}",
            content=body,
            headers={"Content-Type": "application/json"},
        )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_unknown_connector_returns_404(client):
    body = json.dumps(WEBHOOK_PAYLOAD).encode()
    sig  = _sign(body, WEBHOOK_SECRET)

    with patch("routers.hrms_webhook._load_config_with_secret",
               new=AsyncMock(return_value=None)):
        async with client as c:
            resp = await c.post(
                f"/v1/hrms/webhook/{uuid4()}",
                content=body,
                headers={
                    "Content-Type":        "application/json",
                    "X-PRANA-Webhook-Sig": sig,
                },
            )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_webhook_publishes_via_employee_event(client, mock_kafka):
    body = json.dumps(WEBHOOK_PAYLOAD).encode()
    sig  = _sign(body, WEBHOOK_SECRET)

    mock_adapter = MagicMock()
    mock_adapter.handle_webhook = MagicMock(return_value=MOCK_EVENTS)

    with patch("routers.hrms_webhook._load_config_with_secret",
               new=AsyncMock(return_value=MOCK_CONFIG)), \
         patch("routers.hrms_webhook._get_svc") as mock_get_svc, \
         patch("boto3.client"):
        mock_svc = MagicMock()
        mock_svc.build_adapter = MagicMock(return_value=mock_adapter)
        mock_get_svc.return_value = mock_svc

        async with client as c:
            await c.post(
                f"/v1/hrms/webhook/{CONNECTOR_ID}",
                content=body,
                headers={
                    "Content-Type":        "application/json",
                    "X-PRANA-Webhook-Sig": sig,
                },
            )

    mock_kafka.employee_event.assert_awaited()
    call_event = mock_kafka.employee_event.call_args[0][0]
    assert call_event["event_type"] == "HRMS_EMPLOYEE_SYNCED"
    assert call_event["source"]     == "WEBHOOK"
