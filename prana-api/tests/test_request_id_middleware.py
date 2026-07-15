"""Tests for middleware/request_id.py — RequestIDMiddleware."""
import pytest
from fastapi import FastAPI, Request
from httpx import AsyncClient, ASGITransport

from middleware.request_id import RequestIDMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/echo")
    async def echo(request: Request):
        return {"request_id": request.state.request_id}

    return app


@pytest.mark.asyncio
async def test_generates_a_request_id_when_none_supplied():
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/echo")

    assert resp.status_code == 200
    body_id = resp.json()["request_id"]
    header_id = resp.headers["X-Request-ID"]
    assert body_id == header_id
    assert len(body_id) == 36  # UUID4 string length


@pytest.mark.asyncio
async def test_honours_an_incoming_x_request_id_header():
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/echo", headers={"X-Request-ID": "caller-supplied-id-123"})

    assert resp.json()["request_id"] == "caller-supplied-id-123"
    assert resp.headers["X-Request-ID"] == "caller-supplied-id-123"


@pytest.mark.asyncio
async def test_different_requests_get_different_ids():
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.get("/echo")
        r2 = await client.get("/echo")

    assert r1.json()["request_id"] != r2.json()["request_id"]
