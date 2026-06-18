"""Tests for services/health_service.py — TDD stubs."""
import pytest


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_health_check_includes_db_kafka_redis_status():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_health_check_returns_degraded_if_kafka_down():
    raise NotImplementedError
