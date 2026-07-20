"""Tests for services/error_threshold_service.py — promotion rules (§5 of
prana-docs/ERROR_OBSERVABILITY_DESIGN.md).

Classification now delegates to SeverityPolicyService (domain=ERROR_OBSERVABILITY),
reading the rule set from severity_classification_rule instead of hardcoded Python
constants — see prana-docs/SEVERITY_SLA_POLICY_DESIGN.md. These tests mock the DB
to return the same rule set seeded by migration 041, to prove the classification
OUTCOME is unchanged by the refactor.
"""
import datetime
from unittest.mock import AsyncMock, patch

import pytest

from services.error_threshold_service import ErrorThresholdService

NOW = datetime.datetime(2026, 7, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)

# Mirrors migration 041's domain=ERROR_OBSERVABILITY seed, in priority order.
_ERROR_OBS_RULES = [
    {"match_type": "PREFIX", "match_value": "/auth/", "occurrence_threshold": None,
     "occurrence_threshold_max": None, "window_minutes": None, "severity": "P1"},
    {"match_type": "PREFIX", "match_value": "/totp/", "occurrence_threshold": None,
     "occurrence_threshold_max": None, "window_minutes": None, "severity": "P1"},
    {"match_type": "EXACT", "match_value": "AuthConsumer", "occurrence_threshold": None,
     "occurrence_threshold_max": None, "window_minutes": None, "severity": "P1"},
    {"match_type": "EXACT", "match_value": "verify_audit_integrity", "occurrence_threshold": None,
     "occurrence_threshold_max": None, "window_minutes": None, "severity": "P1"},
    {"match_type": "PREFIX", "match_value": "/v1/dpdp/", "occurrence_threshold": 3,
     "occurrence_threshold_max": None, "window_minutes": 10, "severity": "P2"},
    {"match_type": "PREFIX", "match_value": "/v1/ingest/", "occurrence_threshold": 3,
     "occurrence_threshold_max": None, "window_minutes": 10, "severity": "P2"},
    {"match_type": "DEFAULT", "match_value": None, "occurrence_threshold": 1,
     "occurrence_threshold_max": 1, "window_minutes": None, "severity": "P2"},
    {"match_type": "DEFAULT", "match_value": None, "occurrence_threshold": 10,
     "occurrence_threshold_max": None, "window_minutes": 15, "severity": "P3"},
]


def _row(source_detail, occurrence_count, first_seen_at=NOW, last_seen_at=NOW, error_id="e-1"):
    return {
        "error_id": error_id, "source_detail": source_detail,
        "occurrence_count": occurrence_count,
        "first_seen_at": first_seen_at, "last_seen_at": last_seen_at,
    }


def _svc_with_rules():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=_ERROR_OBS_RULES)
    return ErrorThresholdService(db)


@pytest.mark.asyncio
@pytest.mark.parametrize("source_detail", [
    "/auth/employee/login", "/auth/org/login", "/auth/admin/login",
    "/totp/setup/init", "AuthConsumer", "verify_audit_integrity",
])
async def test_security_path_promotes_to_p1_on_first_occurrence(source_detail):
    svc = _svc_with_rules()
    assert await svc._classify(_row(source_detail, occurrence_count=1)) == "P1"


@pytest.mark.asyncio
async def test_non_security_path_single_occurrence_does_not_get_p1():
    svc = _svc_with_rules()
    assert await svc._classify(_row("/v1/cfo/anomalies", occurrence_count=1)) != "P1"


@pytest.mark.asyncio
@pytest.mark.parametrize("source_detail", ["/v1/dpdp/erasure-request", "/v1/ingest/upload"])
async def test_compliance_path_needs_three_occurrences_within_10_minutes(source_detail):
    svc = _svc_with_rules()
    within_window = NOW + datetime.timedelta(minutes=5)
    assert await svc._classify(_row(source_detail, 3, NOW, within_window)) == "P2"
    assert await svc._classify(_row(source_detail, 2, NOW, within_window)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("source_detail", ["/v1/dpdp/erasure-request", "/v1/ingest/upload"])
async def test_compliance_path_outside_10_minute_window_not_promoted(source_detail):
    svc = _svc_with_rules()
    outside_window = NOW + datetime.timedelta(minutes=30)
    assert await svc._classify(_row(source_detail, 3, NOW, outside_window)) is None


@pytest.mark.asyncio
async def test_novel_fingerprint_promotes_to_p2_on_first_occurrence():
    svc = _svc_with_rules()
    assert await svc._classify(_row("/v1/cfo/anomalies", occurrence_count=1)) == "P2"


@pytest.mark.asyncio
async def test_recurring_non_security_error_needs_ten_occurrences_within_15_minutes():
    svc = _svc_with_rules()
    within_window = NOW + datetime.timedelta(minutes=10)
    assert await svc._classify(_row("/v1/cfo/anomalies", 10, NOW, within_window)) == "P3"
    assert await svc._classify(_row("/v1/cfo/anomalies", 9, NOW, within_window)) is None


@pytest.mark.asyncio
async def test_recurring_non_security_error_outside_window_not_promoted():
    svc = _svc_with_rules()
    outside_window = NOW + datetime.timedelta(minutes=45)
    assert await svc._classify(_row("/v1/cfo/anomalies", 10, NOW, outside_window)) is None


@pytest.mark.asyncio
async def test_between_two_and_nine_occurrences_stays_unpromoted():
    svc = _svc_with_rules()
    assert await svc._classify(_row("/v1/cfo/anomalies", 5, NOW, NOW)) is None


def _mixed_fetch(error_rows):
    """db.fetch side_effect: first call (error_event scan) returns error_rows,
    every subsequent call (SeverityPolicyService rule lookups) returns the
    ERROR_OBSERVABILITY rule set."""
    calls = {"n": 0}

    async def _fetch(sql, *args):
        calls["n"] += 1
        if calls["n"] == 1:
            return error_rows
        return _ERROR_OBS_RULES

    return _fetch


@pytest.mark.asyncio
async def test_evaluate_promotions_promotes_qualifying_rows_and_skips_others():
    db = AsyncMock()
    error_rows = [
        _row("/auth/employee/login", 1, error_id="e-security"),
        _row("/v1/cfo/anomalies", 3, error_id="e-quiet"),
    ]
    db.fetch = AsyncMock(side_effect=_mixed_fetch(error_rows))
    svc = ErrorThresholdService(db)

    with patch.object(svc, "promote_to_incident_via_error_observability", new_callable=AsyncMock) as mock_promote:
        mock_promote.return_value = "incident-1"
        result = await svc.evaluate_promotions()

    mock_promote.assert_awaited_once_with(error_id="e-security", severity="P1")
    assert result["evaluated"] == 2
    assert len(result["promoted"]) == 1
    assert result["promoted"][0]["error_id"] == "e-security"
    assert result["promoted"][0]["incident_id"] == "incident-1"


@pytest.mark.asyncio
async def test_evaluate_promotions_only_scans_unlinked_open_rows():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    svc = ErrorThresholdService(db)

    await svc.evaluate_promotions()

    sql = db.fetch.call_args.args[0]
    assert "linked_incident_id IS NULL" in sql
    assert "'NEW'" in sql and "'ACKNOWLEDGED'" in sql
