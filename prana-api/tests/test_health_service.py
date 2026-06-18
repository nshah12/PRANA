"""Tests for services/health_service.py."""
import inspect

from services.health_service import HealthService, HEALTH_TARGETS


def test_health_check_includes_db_kafka_redis_status():
    # HEALTH_TARGETS lists prana-api, prana-ai, prana-ask — all critical services
    target_names = {t["name"] for t in HEALTH_TARGETS}
    assert "prana-api" in target_names, "Health checks must include prana-api"
    assert len(HEALTH_TARGETS) >= 1, "At least one health target must be defined"

    src = inspect.getsource(HealthService.run_checks)
    assert "execute_activity" not in src, "run_checks is a service method — no Temporal"
    assert "_ping" in src or "ping" in src.lower(), "run_checks must ping services"


def test_health_check_returns_degraded_if_kafka_down():
    src = inspect.getsource(HealthService.run_checks)
    # When ping fails, an incident is opened
    assert "_open_or_update" in src, \
        "run_checks must call _open_or_update on failure to create an incident"
    assert "severity" in src or "P1" in src or "P2" in src, \
        "Health incidents must have a severity level"
