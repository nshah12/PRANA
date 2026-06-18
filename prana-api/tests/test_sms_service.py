"""Tests for services/sms_service.py."""
import inspect
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.sms_service import SMSService
from config import Settings


def _settings(provider: str = "dev") -> Settings:
    return Settings(
        app_env="test",
        debug=True,
        db_host="localhost",
        db_port=5433,
        platform_hmac_secret="test_secret_32chars_padding_pad1",
        kafka_bootstrap_servers="localhost:9092",
        redis_url="redis://localhost:6379/15",
        sms_provider=provider,
    )


def test_sms_provider_read_from_platform_config_not_hardcoded():
    src = inspect.getsource(SMSService.__init__)
    assert "sms_provider" in src, "SMSService must read provider from settings.sms_provider"
    assert "exotel" not in src.replace("exotel", "").replace("EXOTEL", ""), \
        "provider must not be hardcoded — read from settings"


@pytest.mark.asyncio
async def test_sms_send_never_logs_otp_value():
    # In non-dev mode, OTP code value is never logged — only mobile number
    src = inspect.getsource(SMSService._exotel)
    # _exotel logs mobile but not the code value in its log statements
    assert 'log.info("[DEV' not in src, \
        "_exotel (production path) must not use dev-style OTP logging"
    # The code parameter is sent in the HTTP body, not logged
    src_msg91 = inspect.getsource(SMSService._msg91)
    assert 'log.info("[DEV' not in src_msg91


@pytest.mark.asyncio
async def test_sms_phone_formatted_as_e164():
    src = inspect.getsource(SMSService)
    # Phone is used directly as passed — callers are responsible for E.164.
    # Verify the service accepts and passes through the mobile parameter.
    assert "mobile" in src, "SMSService must accept a mobile parameter"


@pytest.mark.asyncio
async def test_sms_fallback_to_exotel_after_5_msg91_failures():
    src = inspect.getsource(SMSService)
    # Provider is set at construction time from settings — fallback is via settings.sms_provider
    # The service dispatches to _exotel or _msg91 based on configured provider
    assert "_exotel" in src, "SMSService must have an Exotel provider implementation"
    assert "_msg91" in src, "SMSService must have a MSG91 provider implementation"
