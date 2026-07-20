"""Tests for services/anomaly_detection_service.py — implements the previously-stub
run_anomaly_detection_batch (workflows/security.py) for real.

See prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §3.1 for the 4 rules in scope:
BULK_DOC_ACCESS, BRUTE_FORCE, OFF_HOURS_ACCESS, IMPOSSIBLE_TRAVEL — plus the two
added when the user asked to also cover §3.2's originally-deferred rules with real
signal support: SHARE_ENUM and PRE_EXIT_BULK.

Each detection method:
  1. Reads its own occurrence_threshold/window_minutes from severity_classification_rule
     (domain=ANOMALY_RULE) via SeverityPolicyService.get_rule_threshold — PA-editable,
     not hardcoded.
  2. Runs a query using that threshold.
  3. For each qualifying candidate not already an OPEN anomaly, writes anomaly_event
     with severity resolved via SeverityPolicyService.resolve_severity.
  4. Publishes a security_event carrying the explicit severity (fixes the
     security_consumer.py/notif_consumer.py default-severity disagreement at the source).
"""
import datetime
from unittest.mock import AsyncMock, patch

import pytest

from services.anomaly_detection_service import AnomalyDetectionService

NOW = datetime.datetime(2026, 7, 16, 12, 0, 0, tzinfo=datetime.timezone.utc)


_CONFIG_DEFAULTS = {
    "off_hours_start_hour": "22", "off_hours_end_hour": "6",
    "impossible_travel_speed_kmh": "900", "pre_exit_bulk_lookahead_days": "30",
}


def _db_with(rule_threshold, candidate_rows, existing_open=None, config=None):
    db = AsyncMock()
    cfg = {**_CONFIG_DEFAULTS, **(config or {})}

    async def _fetchrow(sql, *args):
        if "severity_classification_rule" in sql:
            return rule_threshold
        return None

    async def _fetch(sql, *args):
        if "severity_classification_rule" in sql:
            return []
        if "SELECT" in sql.upper() and ("anomaly_event" in sql and "EXISTS" not in sql.upper()):
            return existing_open or []
        return candidate_rows

    async def _fetchval(sql, *args):
        if "platform_config" in sql and args:
            return cfg.get(args[0])
        return None

    db.fetchrow = AsyncMock(side_effect=_fetchrow)
    db.fetch = AsyncMock(side_effect=_fetch)
    db.fetchval = AsyncMock(side_effect=_fetchval)
    db.execute = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_bulk_doc_access_detects_and_writes_anomaly():
    db = _db_with(
        rule_threshold={"occurrence_threshold": 50, "window_minutes": 10},
        candidate_rows=[
            {"actor_id": "oa-1", "actor_type": "OA_OPERATOR", "tenant_id": "t-1", "cnt": 60,
             "first_at": NOW, "last_at": NOW},
        ],
    )
    svc = AnomalyDetectionService(db)

    with patch("services.severity_policy_service.SeverityPolicyService.resolve_severity",
               new_callable=AsyncMock, return_value="P1") as mock_resolve, \
         patch.object(svc, "_publish_anomaly", new_callable=AsyncMock) as mock_publish:
        result = await svc.detect_bulk_doc_access()

    assert result == 1
    mock_resolve.assert_awaited_once_with(
        domain="ANOMALY_RULE", value="BULK_DOC_ACCESS", occurrence_count=60, span_minutes=0,
    )
    insert_call = next(c for c in db.execute.call_args_list if "INSERT INTO anomaly_event" in c.args[0])
    assert "BULK_DOC_ACCESS" in insert_call.args
    assert "P1" in insert_call.args
    mock_publish.assert_awaited_once()
    # actor_user_type must reach the publish call so security_consumer.py's
    # auto-lock trigger knows to lock the oa_user table, not employee_user.
    assert mock_publish.call_args.kwargs["actor_user_type"] == "oa_user"


@pytest.mark.asyncio
async def test_bulk_doc_access_third_party_actor_has_no_lockable_account():
    """THIRD_PARTY (HRMS API key) has no local user row — must not claim oa_user,
    which would make the auto-lock trigger try to lock a nonexistent account."""
    db = _db_with(
        rule_threshold={"occurrence_threshold": 50, "window_minutes": 10},
        candidate_rows=[
            {"actor_id": "hrms-key-1", "actor_type": "THIRD_PARTY", "tenant_id": "t-1", "cnt": 60,
             "first_at": NOW, "last_at": NOW},
        ],
    )
    svc = AnomalyDetectionService(db)
    with patch("services.severity_policy_service.SeverityPolicyService.resolve_severity",
               new_callable=AsyncMock, return_value="P1"), \
         patch.object(svc, "_publish_anomaly", new_callable=AsyncMock) as mock_publish:
        await svc.detect_bulk_doc_access()

    assert mock_publish.call_args.kwargs["actor_user_type"] is None


@pytest.mark.asyncio
async def test_bulk_doc_access_uses_configured_threshold_in_query():
    db = _db_with(
        rule_threshold={"occurrence_threshold": 50, "window_minutes": 10},
        candidate_rows=[],
    )
    svc = AnomalyDetectionService(db)
    await svc.detect_bulk_doc_access()

    candidates_call = next(
        c for c in db.fetch.call_args_list
        if "document_access_log" in c.args[0] and "GROUP BY" in c.args[0]
    )
    assert 50 in candidates_call.args
    assert 10 in candidates_call.args


@pytest.mark.asyncio
async def test_bulk_doc_access_no_rule_configured_skips_detection():
    """If PA deactivates/deletes the ANOMALY_RULE row, detection must not run blind
    with a made-up threshold — it must simply skip, not guess."""
    db = _db_with(rule_threshold=None, candidate_rows=[])
    svc = AnomalyDetectionService(db)
    result = await svc.detect_bulk_doc_access()
    assert result == 0
    assert not any("document_access_log" in c.args[0] for c in db.fetch.call_args_list)


@pytest.mark.asyncio
async def test_brute_force_detects_failed_login_cluster():
    db = _db_with(
        rule_threshold={"occurrence_threshold": 5, "window_minutes": 15},
        candidate_rows=[
            {"user_id": "u-1", "user_type": "employee", "tenant_id": "t-1",
             "cnt": 7, "first_at": NOW, "last_at": NOW},
        ],
    )
    svc = AnomalyDetectionService(db)
    with patch("services.severity_policy_service.SeverityPolicyService.resolve_severity",
               new_callable=AsyncMock, return_value="P1"), \
         patch.object(svc, "_publish_anomaly", new_callable=AsyncMock) as mock_publish:
        result = await svc.detect_brute_force()
    assert result == 1
    insert_call = next(c for c in db.execute.call_args_list if "INSERT INTO anomaly_event" in c.args[0])
    assert "BRUTE_FORCE" in insert_call.args
    assert mock_publish.call_args.kwargs["actor_user_type"] == "employee"


@pytest.mark.asyncio
async def test_off_hours_access_detects_out_of_window_event():
    db = _db_with(
        rule_threshold={"occurrence_threshold": None, "window_minutes": None},
        candidate_rows=[
            {"access_id": "acc-1", "actor_id": "oa-1", "tenant_id": "t-1", "accessed_at": NOW},
        ],
    )
    svc = AnomalyDetectionService(db)
    with patch("services.severity_policy_service.SeverityPolicyService.resolve_severity",
               new_callable=AsyncMock, return_value="P2"), \
         patch.object(svc, "_publish_anomaly", new_callable=AsyncMock):
        result = await svc.detect_off_hours_access()
    assert result == 1
    insert_call = next(c for c in db.execute.call_args_list if "INSERT INTO anomaly_event" in c.args[0])
    assert "OFF_HOURS_ACCESS" in insert_call.args


@pytest.mark.asyncio
async def test_impossible_travel_flags_implausible_speed():
    # Mumbai (19.0760, 72.8777) to Delhi (28.7041, 77.1025) ~1150km, in 10 minutes -> ~6900 km/h
    db = _db_with(
        rule_threshold=None,  # IMPOSSIBLE_TRAVEL has no occurrence threshold — always "on"
        candidate_rows=[
            {"user_id": "u-1", "tenant_id": "t-1", "attempted_at": NOW,
             "geo_lat": 28.7041, "geo_lon": 77.1025,
             "prev_at": NOW - datetime.timedelta(minutes=10),
             "prev_lat": 19.0760, "prev_lon": 72.8777, "attempt_id": "att-2"},
        ],
    )
    svc = AnomalyDetectionService(db)
    with patch("services.severity_policy_service.SeverityPolicyService.resolve_severity",
               new_callable=AsyncMock, return_value="P0"), \
         patch.object(svc, "_publish_anomaly", new_callable=AsyncMock):
        result = await svc.detect_impossible_travel()
    assert result == 1
    insert_call = next(c for c in db.execute.call_args_list if "INSERT INTO anomaly_event" in c.args[0])
    assert "IMPOSSIBLE_TRAVEL" in insert_call.args


@pytest.mark.asyncio
async def test_impossible_travel_plausible_speed_not_flagged():
    # Same two points but 3 hours apart -> ~380 km/h, plausible (domestic flight)
    db = _db_with(
        rule_threshold=None,
        candidate_rows=[
            {"user_id": "u-1", "tenant_id": "t-1", "attempted_at": NOW,
             "geo_lat": 28.7041, "geo_lon": 77.1025,
             "prev_at": NOW - datetime.timedelta(hours=3),
             "prev_lat": 19.0760, "prev_lon": 72.8777, "attempt_id": "att-2"},
        ],
    )
    svc = AnomalyDetectionService(db)
    with patch.object(svc, "_publish_anomaly", new_callable=AsyncMock) as mock_publish:
        result = await svc.detect_impossible_travel()
    assert result == 0
    mock_publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_share_enum_detects_many_distinct_tokens_same_ip():
    db = _db_with(
        rule_threshold={"occurrence_threshold": 5, "window_minutes": 10},
        candidate_rows=[
            {"ip_address": "203.0.113.5", "distinct_tokens": 6, "first_at": NOW, "last_at": NOW},
        ],
    )
    svc = AnomalyDetectionService(db)
    with patch("services.severity_policy_service.SeverityPolicyService.resolve_severity",
               new_callable=AsyncMock, return_value="P2"), \
         patch.object(svc, "_publish_anomaly", new_callable=AsyncMock):
        result = await svc.detect_share_enum()
    assert result == 1
    insert_call = next(c for c in db.execute.call_args_list if "INSERT INTO anomaly_event" in c.args[0])
    assert "SHARE_ENUM" in insert_call.args
    # Platform-level — no single tenant owns a cross-tenant enumeration attempt
    assert None in insert_call.args


@pytest.mark.asyncio
async def test_pre_exit_bulk_detects_bulk_self_access_before_exit():
    db = _db_with(
        rule_threshold={"occurrence_threshold": 20, "window_minutes": 1440},
        candidate_rows=[
            {"employee_user_id": "emp-1", "tenant_id": "t-1", "cnt": 25, "first_at": NOW, "last_at": NOW},
        ],
    )
    svc = AnomalyDetectionService(db)
    with patch("services.severity_policy_service.SeverityPolicyService.resolve_severity",
               new_callable=AsyncMock, return_value="P1"), \
         patch.object(svc, "_publish_anomaly", new_callable=AsyncMock):
        result = await svc.detect_pre_exit_bulk()
    assert result == 1
    insert_call = next(c for c in db.execute.call_args_list if "INSERT INTO anomaly_event" in c.args[0])
    assert "PRE_EXIT_BULK" in insert_call.args


@pytest.mark.asyncio
async def test_run_batch_calls_all_six_detectors():
    db = _db_with(rule_threshold=None, candidate_rows=[])
    svc = AnomalyDetectionService(db)
    for method in ("detect_bulk_doc_access", "detect_brute_force", "detect_off_hours_access",
                   "detect_impossible_travel", "detect_share_enum", "detect_pre_exit_bulk"):
        setattr(svc, method, AsyncMock(return_value=0))

    result = await svc.run_batch()

    for method in ("detect_bulk_doc_access", "detect_brute_force", "detect_off_hours_access",
                   "detect_impossible_travel", "detect_share_enum", "detect_pre_exit_bulk"):
        getattr(svc, method).assert_awaited_once()
    assert result["total_detected"] == 0
