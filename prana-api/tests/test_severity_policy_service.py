"""Tests for services/severity_policy_service.py — the generic rule evaluator +
SLA lookup that replaces hardcoded severity/SLA constants across
incident_service.py, error_threshold_service.py, health_service.py, and the
scattered anomaly-severity literals. See prana-docs/SEVERITY_SLA_POLICY_DESIGN.md.
"""
import uuid
from unittest.mock import AsyncMock

import pytest

from services.severity_policy_service import SeverityPolicyService


def _rule(domain, match_type, match_value, severity, priority=100,
          occurrence_threshold=None, occurrence_threshold_max=None, window_minutes=None,
          is_active=True):
    return {
        "domain": domain, "match_type": match_type, "match_value": match_value,
        "occurrence_threshold": occurrence_threshold,
        "occurrence_threshold_max": occurrence_threshold_max,
        "window_minutes": window_minutes, "severity": severity, "priority": priority,
        "is_active": is_active,
    }


# ── resolve_severity — PREFIX / EXACT matching ──────────────────────────────

@pytest.mark.asyncio
async def test_prefix_match_wins_no_threshold():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[_rule("ERROR_OBSERVABILITY", "PREFIX", "/auth/", "P1", 10)])
    svc = SeverityPolicyService(db)
    result = await svc.resolve_severity(domain="ERROR_OBSERVABILITY", value="/auth/employee/login")
    assert result == "P1"


@pytest.mark.asyncio
async def test_prefix_no_match_falls_through_to_default():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        _rule("ERROR_OBSERVABILITY", "PREFIX", "/auth/", "P1", 10),
        _rule("ERROR_OBSERVABILITY", "DEFAULT", None, "P3", 99),
    ])
    svc = SeverityPolicyService(db)
    result = await svc.resolve_severity(domain="ERROR_OBSERVABILITY", value="/v1/cfo/anomalies")
    assert result == "P3"


@pytest.mark.asyncio
async def test_exact_match():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[_rule("ERROR_OBSERVABILITY", "EXACT", "AuthConsumer", "P1", 10)])
    svc = SeverityPolicyService(db)
    assert await svc.resolve_severity(domain="ERROR_OBSERVABILITY", value="AuthConsumer") == "P1"
    assert await svc.resolve_severity(domain="ERROR_OBSERVABILITY", value="NotifConsumer") is None


# ── resolve_severity — threshold semantics (the tricky part) ───────────────

@pytest.mark.asyncio
async def test_specific_rule_matched_but_threshold_unmet_is_terminal():
    """A PREFIX/EXACT rule that matches the value but whose occurrence/window condition
    fails must NOT fall through to a later DEFAULT rule — this reproduces
    error_threshold_service.py's original 'compliance path under threshold returns None,
    does not become a novel-bug P2' behavior."""
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        _rule("ERROR_OBSERVABILITY", "PREFIX", "/v1/dpdp/", "P2", 20, occurrence_threshold=3, window_minutes=10),
        _rule("ERROR_OBSERVABILITY", "DEFAULT", None, "P2", 90, occurrence_threshold=1, occurrence_threshold_max=1),
        _rule("ERROR_OBSERVABILITY", "DEFAULT", None, "P3", 95, occurrence_threshold=10, window_minutes=15),
    ])
    svc = SeverityPolicyService(db)
    result = await svc.resolve_severity(
        domain="ERROR_OBSERVABILITY", value="/v1/dpdp/erasure-request",
        occurrence_count=1, span_minutes=0,
    )
    assert result is None  # NOT "P2" via the novel-bug DEFAULT fallback


@pytest.mark.asyncio
async def test_specific_rule_matched_and_threshold_met():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        _rule("ERROR_OBSERVABILITY", "PREFIX", "/v1/dpdp/", "P2", 20, occurrence_threshold=3, window_minutes=10),
    ])
    svc = SeverityPolicyService(db)
    result = await svc.resolve_severity(
        domain="ERROR_OBSERVABILITY", value="/v1/dpdp/erasure-request",
        occurrence_count=3, span_minutes=5,
    )
    assert result == "P2"


@pytest.mark.asyncio
async def test_specific_rule_threshold_met_but_window_exceeded_is_terminal():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        _rule("ERROR_OBSERVABILITY", "PREFIX", "/v1/dpdp/", "P2", 20, occurrence_threshold=3, window_minutes=10),
        _rule("ERROR_OBSERVABILITY", "DEFAULT", None, "P3", 99),
    ])
    svc = SeverityPolicyService(db)
    result = await svc.resolve_severity(
        domain="ERROR_OBSERVABILITY", value="/v1/dpdp/erasure-request",
        occurrence_count=3, span_minutes=30,
    )
    assert result is None


@pytest.mark.asyncio
async def test_wildcard_default_rule_unmet_condition_falls_through():
    """Unlike specific PREFIX/EXACT rules, a DEFAULT (wildcard) rule that doesn't satisfy
    its own condition should fall through to the NEXT rule — this is what lets the
    novel-bug (exactly 1st occurrence) and noise (10th+ occurrence) DEFAULT rules cascade."""
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        _rule("ERROR_OBSERVABILITY", "DEFAULT", None, "P2", 90, occurrence_threshold=1, occurrence_threshold_max=1),
        _rule("ERROR_OBSERVABILITY", "DEFAULT", None, "P3", 95, occurrence_threshold=10, window_minutes=15),
    ])
    svc = SeverityPolicyService(db)
    # occurrence_count=5 doesn't match either exactly-1 or >=10 -> no match at all
    result = await svc.resolve_severity(
        domain="ERROR_OBSERVABILITY", value="/v1/cfo/anomalies", occurrence_count=5, span_minutes=5,
    )
    assert result is None


@pytest.mark.asyncio
async def test_novel_bug_first_occurrence_via_exact_max_semantics():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        _rule("ERROR_OBSERVABILITY", "DEFAULT", None, "P2", 90, occurrence_threshold=1, occurrence_threshold_max=1),
        _rule("ERROR_OBSERVABILITY", "DEFAULT", None, "P3", 95, occurrence_threshold=10, window_minutes=15),
    ])
    svc = SeverityPolicyService(db)
    result = await svc.resolve_severity(
        domain="ERROR_OBSERVABILITY", value="/v1/cfo/anomalies", occurrence_count=1, span_minutes=0,
    )
    assert result == "P2"


@pytest.mark.asyncio
async def test_noise_recurrence_falls_through_to_second_default():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        _rule("ERROR_OBSERVABILITY", "DEFAULT", None, "P2", 90, occurrence_threshold=1, occurrence_threshold_max=1),
        _rule("ERROR_OBSERVABILITY", "DEFAULT", None, "P3", 95, occurrence_threshold=10, window_minutes=15),
    ])
    svc = SeverityPolicyService(db)
    result = await svc.resolve_severity(
        domain="ERROR_OBSERVABILITY", value="/v1/cfo/anomalies", occurrence_count=10, span_minutes=10,
    )
    assert result == "P3"


@pytest.mark.asyncio
async def test_no_rules_match_returns_none():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    svc = SeverityPolicyService(db)
    result = await svc.resolve_severity(domain="ERROR_OBSERVABILITY", value="/anything")
    assert result is None


@pytest.mark.asyncio
async def test_inactive_rules_excluded_by_query():
    """The SQL itself filters is_active=TRUE — verify the query shape."""
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    svc = SeverityPolicyService(db)
    await svc.resolve_severity(domain="HEALTH_CHECK", value="prana-api")
    sql = db.fetch.call_args.args[0]
    assert "is_active" in sql
    assert "ORDER BY priority" in sql


# ── ANOMALY_RULE domain — the P3/P2 consumer-disagreement fix ──────────────

@pytest.mark.asyncio
async def test_anomaly_rule_exact_match_and_default_fallback():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        _rule("ANOMALY_RULE", "EXACT", "CROSS_TENANT_UPLOAD_ATTEMPT", "P0", 10),
        _rule("ANOMALY_RULE", "DEFAULT", None, "P3", 99),
    ])
    svc = SeverityPolicyService(db)
    assert await svc.resolve_severity(domain="ANOMALY_RULE", value="CROSS_TENANT_UPLOAD_ATTEMPT") == "P0"
    assert await svc.resolve_severity(domain="ANOMALY_RULE", value="SOME_FUTURE_RULE") == "P3"


# ── get_sla ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_sla_returns_minutes_and_auto_create():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"sla_minutes": 30, "auto_create_incident": True})
    svc = SeverityPolicyService(db)
    result = await svc.get_sla(severity="P0")
    assert result == {"sla_minutes": 30, "auto_create_incident": True}


@pytest.mark.asyncio
async def test_get_sla_missing_severity_returns_none():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=None)
    svc = SeverityPolicyService(db)
    result = await svc.get_sla(severity="P9")
    assert result is None


@pytest.mark.asyncio
async def test_get_rule_threshold_returns_occurrence_and_window():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"occurrence_threshold": 50, "window_minutes": 10})
    svc = SeverityPolicyService(db)
    result = await svc.get_rule_threshold(domain="ANOMALY_RULE", match_value="BULK_DOC_ACCESS")
    assert result == {"occurrence_threshold": 50, "window_minutes": 10}
    sql, *args = db.fetchrow.call_args.args
    assert "match_type = 'EXACT'" in sql
    assert "ANOMALY_RULE" in args and "BULK_DOC_ACCESS" in args


@pytest.mark.asyncio
async def test_get_rule_threshold_missing_rule_returns_none():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=None)
    svc = SeverityPolicyService(db)
    result = await svc.get_rule_threshold(domain="ANOMALY_RULE", match_value="NOT_A_REAL_RULE")
    assert result is None


@pytest.mark.asyncio
async def test_get_all_sla_policies():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        {"severity": "P0", "sla_minutes": 30, "auto_create_incident": True, "description": "x",
         "updated_by": None, "updated_at": None},
    ])
    svc = SeverityPolicyService(db)
    result = await svc.get_all_sla_policies()
    assert len(result) == 1
    assert result[0]["severity"] == "P0"


# ── update_sla_policy — PA config editing (prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §5) ──

@pytest.mark.asyncio
async def test_update_sla_policy_updates_and_returns_row():
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=1)
    db.fetchrow = AsyncMock(return_value={
        "severity": "P1", "sla_minutes": 60, "auto_create_incident": True,
        "description": "updated", "updated_by": "pa-1", "updated_at": None,
    })
    svc = SeverityPolicyService(db)
    result = await svc.update_sla_policy(
        severity="P1", sla_minutes=60, auto_create_incident=True,
        description="updated", updated_by="pa-1",
    )
    assert result["sla_minutes"] == 60
    update_call = next(c for c in db.execute.call_args_list if "UPDATE sla_policy" in c.args[0])
    assert "P1" in update_call.args
    assert 60 in update_call.args
    assert "pa-1" in update_call.args


@pytest.mark.asyncio
async def test_update_sla_policy_unknown_severity_raises_value_error():
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=None)
    svc = SeverityPolicyService(db)
    with pytest.raises(ValueError):
        await svc.update_sla_policy(
            severity="P9", sla_minutes=60, auto_create_incident=None,
            description=None, updated_by="pa-1",
        )
    db.execute.assert_not_called()


# ── severity_classification_rule CRUD ───────────────────────────────────────

@pytest.mark.asyncio
async def test_list_severity_rules_filters_by_domain():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        {"rule_id": uuid.uuid4(), "domain": "ANOMALY_RULE", "match_type": "EXACT",
         "match_value": "BULK_DOC_ACCESS", "occurrence_threshold": 50,
         "occurrence_threshold_max": None, "window_minutes": 10, "severity": "P1",
         "priority": 10, "is_active": True, "description": None,
         "updated_by": None, "updated_at": None},
    ])
    svc = SeverityPolicyService(db)
    result = await svc.list_severity_rules(domain="ANOMALY_RULE")
    assert len(result) == 1
    assert result[0]["domain"] == "ANOMALY_RULE"
    sql, *args = db.fetch.call_args.args
    assert "ANOMALY_RULE" in args


@pytest.mark.asyncio
async def test_list_severity_rules_no_domain_lists_all():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    svc = SeverityPolicyService(db)
    await svc.list_severity_rules(domain=None)
    sql, *args = db.fetch.call_args.args
    assert args == []


@pytest.mark.asyncio
async def test_create_severity_rule_inserts_and_returns_row():
    new_id = uuid.uuid4()
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={
        "rule_id": new_id, "domain": "ANOMALY_RULE", "match_type": "EXACT",
        "match_value": "NEW_RULE", "occurrence_threshold": 5,
        "occurrence_threshold_max": None, "window_minutes": 15, "severity": "P2",
        "priority": 50, "is_active": True, "description": "test",
        "updated_by": "pa-1", "updated_at": None,
    })
    svc = SeverityPolicyService(db)
    result = await svc.create_severity_rule(
        domain="ANOMALY_RULE", match_type="EXACT", match_value="NEW_RULE",
        occurrence_threshold=5, occurrence_threshold_max=None, window_minutes=15,
        severity="P2", priority=50, description="test", updated_by="pa-1",
    )
    assert result["match_value"] == "NEW_RULE"
    insert_call = next(c for c in db.execute.call_args_list if "INSERT INTO severity_classification_rule" in c.args[0])
    assert "ANOMALY_RULE" in insert_call.args
    assert "NEW_RULE" in insert_call.args


@pytest.mark.asyncio
async def test_create_severity_rule_rejects_invalid_match_type():
    db = AsyncMock()
    svc = SeverityPolicyService(db)
    with pytest.raises(ValueError):
        await svc.create_severity_rule(
            domain="ANOMALY_RULE", match_type="FUZZY", match_value="X",
            occurrence_threshold=None, occurrence_threshold_max=None, window_minutes=None,
            severity="P2", priority=50, description=None, updated_by="pa-1",
        )
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_create_severity_rule_requires_match_value_unless_default():
    db = AsyncMock()
    svc = SeverityPolicyService(db)
    with pytest.raises(ValueError):
        await svc.create_severity_rule(
            domain="ANOMALY_RULE", match_type="EXACT", match_value=None,
            occurrence_threshold=None, occurrence_threshold_max=None, window_minutes=None,
            severity="P2", priority=50, description=None, updated_by="pa-1",
        )
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_update_severity_rule_updates_and_returns_row():
    rule_id = str(uuid.uuid4())
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=1)
    db.fetchrow = AsyncMock(return_value={
        "rule_id": rule_id, "domain": "ANOMALY_RULE", "match_type": "EXACT",
        "match_value": "BULK_DOC_ACCESS", "occurrence_threshold": 75,
        "occurrence_threshold_max": None, "window_minutes": 10, "severity": "P1",
        "priority": 10, "is_active": False, "description": None,
        "updated_by": "pa-1", "updated_at": None,
    })
    svc = SeverityPolicyService(db)
    result = await svc.update_severity_rule(
        rule_id=rule_id, occurrence_threshold=75, is_active=False, updated_by="pa-1",
    )
    assert result["occurrence_threshold"] == 75
    assert result["is_active"] is False
    update_call = next(c for c in db.execute.call_args_list if "UPDATE severity_classification_rule" in c.args[0])
    assert 75 in update_call.args
    assert False in update_call.args


@pytest.mark.asyncio
async def test_update_severity_rule_unknown_id_raises_value_error():
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=None)
    svc = SeverityPolicyService(db)
    with pytest.raises(ValueError):
        await svc.update_severity_rule(rule_id=str(uuid.uuid4()), updated_by="pa-1")
    db.execute.assert_not_called()
