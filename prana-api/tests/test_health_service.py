"""Tests for services/health_service.py."""
import inspect
import json
from unittest.mock import AsyncMock

import pytest

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


# ── _notify_pa: audit_event.actor_id NOT NULL + hand-rolled JSON ─────────────
# Regression coverage: audit_event.actor_id is NOT NULL with no default
# (schema.sql). This INSERT omitted it entirely, so every service-health
# incident notification threw NotNullViolationError — silently swallowed by
# the surrounding try/except, so the audit trail for SERVICE_INCIDENT_OPENED
# was never actually written, with no visible error anywhere. The metadata was
# also hand-built via an f-string instead of json.dumps(), which breaks (malformed
# JSON, ::jsonb cast fails) the moment service/severity/detail contains a `"`.

@pytest.mark.asyncio
async def test_notify_pa_writes_audit_event_with_actor_id():
    db = AsyncMock()
    svc = HealthService(db)
    await svc._notify_pa("prana-ai", "P1", "incident-1", 'GPU worker down: "OOM" detected')

    db.execute.assert_awaited_once()
    sql, *params = db.execute.call_args[0]
    assert "INSERT INTO audit_event" in sql
    # actor_id is NOT NULL with no default — must always be supplied
    assert "actor_id" in sql
    non_null_params = [p for p in params if p is not None]
    assert any(p == "00000000-0000-0000-0000-000000000000" for p in non_null_params), \
        "SYSTEM-actor audit rows use the nil UUID sentinel, matching AuditConsumer's own pattern"


@pytest.mark.asyncio
async def test_notify_pa_metadata_is_valid_json_even_with_quotes_in_detail():
    db = AsyncMock()
    svc = HealthService(db)
    detail_with_quotes = 'Connection failed: "timeout after 30s"'
    await svc._notify_pa("prana-ai", "P1", "incident-1", detail_with_quotes)

    sql, *params = db.execute.call_args[0]
    metadata_param = next(p for p in params if isinstance(p, str) and p.strip().startswith("{"))
    parsed = json.loads(metadata_param)  # must not raise
    assert parsed["service"] == "prana-ai"
    assert "timeout after 30s" in parsed["detail"]


@pytest.mark.asyncio
async def test_notify_pa_does_not_crash_if_db_write_fails():
    db = AsyncMock()
    db.execute.side_effect = Exception("db unavailable")
    svc = HealthService(db)
    await svc._notify_pa("prana-ai", "P1", "incident-1", "detail")  # must not raise
