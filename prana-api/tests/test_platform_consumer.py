"""Tests for PlatformConsumer — prana.platform.events"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp


@pytest.fixture
def consumer():
    from kafka.consumers.platform_consumer import PlatformConsumer
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    return PlatformConsumer(settings)


@pytest.mark.asyncio
async def test_worker_crashed_posts_to_webhook(consumer):
    event = {"event_type": "WORKER_CRASHED", "service": "prana-api", "reason": "OOM"}
    with patch.dict("os.environ", {"OPS_ALERT_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session.post = AsyncMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=MagicMock(status=200)), __aexit__=AsyncMock()))
            await consumer._handle(event)
            mock_session.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_check_failed_posts_to_webhook(consumer):
    event = {"event_type": "HEALTH_CHECK_FAILED", "service": "prana-api"}
    with patch.dict("os.environ", {"OPS_ALERT_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session.post = AsyncMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=MagicMock(status=200)), __aexit__=AsyncMock()))
            await consumer._handle(event)
            mock_session.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_webhook_url_does_not_crash(consumer):
    event = {"event_type": "WORKER_CRASHED", "service": "prana-api"}
    with patch.dict("os.environ", {}, clear=True):
        await consumer._handle(event)  # must not raise even without webhook URL


@pytest.mark.asyncio
async def test_worker_started_is_logged_not_alerted(consumer):
    """WORKER_STARTED is informational — should not fire the ops webhook."""
    event = {"event_type": "WORKER_STARTED", "service": "prana-api"}
    with patch.dict("os.environ", {"OPS_ALERT_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await consumer._handle(event)
            mock_session.post.assert_not_awaited()
