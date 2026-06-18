"""
Shared pytest fixtures for prana-api tests.

Uses httpx.AsyncClient against the FastAPI app directly (no real network).
Uses MagicMock for DB, Redis, Kafka — tests cover request routing and service logic,
not infrastructure. Integration tests live in tests/integration/.

Fixtures:
  mock_settings  — Settings with test values
  mock_db        — AsyncMock asyncpg connection
  mock_redis     — AsyncMock Redis client
  mock_kafka     — AsyncMock Kafka producer
  app            — Configured FastAPI app with mocked infrastructure in state
  client         — httpx AsyncClient wrapping `app`

Tests that need to configure JWT (e.g. vault tests) should request the `app`
fixture and set app.state.jwt_service attributes before making requests.
"""
import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import create_app
from config import Settings


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        app_env="test",
        debug=True,
        db_host="localhost",
        db_port=5433,
        platform_hmac_secret="test_secret_32chars_padding_pad1",
        kafka_bootstrap_servers="localhost:9092",
        redis_url="redis://localhost:6379/15",
        sms_provider="dev",
    )


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=None)
    db.fetch = AsyncMock(return_value=[])
    db.fetchval = AsyncMock(return_value=None)
    db.execute = AsyncMock()
    db.transaction = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    return db


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    r.setex = AsyncMock()
    r.delete = AsyncMock()
    r.publish = AsyncMock()
    return r


@pytest.fixture
def mock_kafka():
    kafka = AsyncMock()
    kafka.publish = AsyncMock()
    return kafka


@pytest.fixture
def app(mock_settings, mock_db, mock_redis, mock_kafka):
    """
    Configured FastAPI app with mocked infrastructure.
    Request this fixture when you need to inspect or configure app.state
    (e.g. set jwt_service mock return values for authenticated endpoints).
    """
    from services.jwt_service import JWTService

    _app = create_app()
    _app.state.settings = mock_settings
    _app.state.redis = mock_redis
    _app.state.kafka_producer = mock_kafka
    _app.state.db_pool = AsyncMock()
    _app.state.db_pool.acquire = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_db),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    _app.state.temporal_client = None
    _app.state.kms_service = MagicMock()
    _app.state.s3 = MagicMock()

    jwt_mock = MagicMock(spec=JWTService)
    jwt_mock.decode = MagicMock(return_value={})
    jwt_mock.is_revoked = AsyncMock(return_value=True)  # default: deny — tests must opt in
    jwt_mock.issue = MagicMock(return_value="mock.jwt.token")
    jwt_mock.revoke = AsyncMock()
    _app.state.jwt_service = jwt_mock

    return _app


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """ASGI test client. Use `app` fixture for state access."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        c.app = app   # attach so tests can reach app.state
        yield c
