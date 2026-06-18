"""Tests for routers/public.py and the /health endpoint."""
import pytest


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_public_endpoints_require_no_auth(client):
    # /public/contact can be called without any auth token
    resp = await client.post(
        "/public/contact",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "message": "Hello PRANA",
            "company": "Test Corp",
        },
    )
    # 201 created or 500 (DB mock returns None but no auth required)
    assert resp.status_code != 401, "Public contact endpoint must not require auth"
    assert resp.status_code != 403, "Public contact endpoint must not require auth"
