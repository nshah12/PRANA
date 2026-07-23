"""Tests for services/analytics_service.py — implements the previously-stub
activities in workflows/intelligence.py.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.analytics_service import AnalyticsService


def _db(fetch_return=None, fetchrow_return=None):
    db = AsyncMock()
    db.fetch.return_value = fetch_return or []
    db.fetchrow.return_value = fetchrow_return
    return db


# ── build_career_insight / build_skill_gap_analysis — known prana-ai gap ────

@pytest.mark.asyncio
async def test_build_career_insight_raises_clear_not_implemented_error():
    """Fails loudly with an actionable message rather than silently returning
    empty data — no prana-ai endpoint exists for this yet."""
    with pytest.raises(NotImplementedError, match="prana-ai"):
        await AnalyticsService(_db()).build_career_insight(employee_uuid="emp-1")


@pytest.mark.asyncio
async def test_build_skill_gap_analysis_raises_clear_not_implemented_error():
    with pytest.raises(NotImplementedError, match="prana-ai"):
        await AnalyticsService(_db()).build_skill_gap_analysis(employee_uuid="emp-1")


# ── build_market_comp — does NOT need prana-ai (embedded dataset) ──────────

@pytest.mark.asyncio
async def test_build_market_comp_uses_salary_band_not_llm():
    db = _db(fetchrow_return={"grade": "L3", "department": "Engineering"})
    with patch("services.benchmarking_service.BenchmarkingService.get_market_median",
               new_callable=AsyncMock, return_value={"suppressed": False, "p50": 1200000}) as mock_median:
        result = await AnalyticsService(db).build_market_comp(employee_uuid="emp-1")
    mock_median.assert_awaited_once_with(grade="L3", department="Engineering")
    assert result == {"insights": {"market_comp": {"suppressed": False, "p50": 1200000}}}


@pytest.mark.asyncio
async def test_build_market_comp_returns_empty_insights_when_employee_not_found():
    db = _db(fetchrow_return=None)
    result = await AnalyticsService(db).build_market_comp(employee_uuid="missing")
    assert result == {"insights": {}}


@pytest.mark.asyncio
async def test_write_market_comp_writes_to_insights_key():
    """Regression guard: build_market_comp's result key must match what
    write_market_comp reads (workflows/intelligence.py merges the two dicts
    across an execute_activity boundary — a mismatched key means the computed
    market_comp data silently never reaches employee_insight)."""
    db = _db()
    await AnalyticsService(db).write_market_comp(
        employee_uuid="emp-1", tenant_id="t-1", insights={"market_comp": {"p50": 100}},
    )
    insert_call = db.execute.call_args
    assert "MARKET_COMP" in insert_call.args
    assert {"market_comp": {"p50": 100}} in insert_call.args


# ── score_vault_completeness ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_vault_completeness_all_three_categories_present():
    db = _db(fetch_return=[{"doc_type": "OFFER_LETTER"}, {"doc_type": "SALARY_SLIP"}, {"doc_type": "FORM_16"}])
    result = await AnalyticsService(db).score_vault_completeness(employee_uuid="emp-1")
    assert result == {"vault_completeness": 100}


@pytest.mark.asyncio
async def test_score_vault_completeness_partial():
    db = _db(fetch_return=[{"doc_type": "SALARY_SLIP"}])
    result = await AnalyticsService(db).score_vault_completeness(employee_uuid="emp-1")
    assert result == {"vault_completeness": 33}


@pytest.mark.asyncio
async def test_score_vault_completeness_zero_when_no_documents():
    db = _db(fetch_return=[])
    result = await AnalyticsService(db).score_vault_completeness(employee_uuid="emp-1")
    assert result == {"vault_completeness": 0}


@pytest.mark.asyncio
async def test_write_vault_completeness_updates_employee_master():
    db = _db()
    await AnalyticsService(db).write_vault_completeness(employee_uuid="emp-1", vault_completeness=75)
    db.execute.assert_awaited_once()
    assert db.execute.call_args.args[1] == 75
    assert db.execute.call_args.args[2] == "emp-1"


# ── record_anomaly_ack ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_anomaly_ack_resolves_when_acked():
    db = _db()
    await AnalyticsService(db).record_anomaly_ack(
        anomaly_id="anom-1", acked=True, note="reviewed", acknowledged_by="cfo-1",
    )
    call = db.execute.call_args
    assert call.args[1] == "RESOLVED"
    assert call.args[2] == "cfo-1"


@pytest.mark.asyncio
async def test_record_anomaly_ack_stays_open_when_sla_breached_unacked():
    db = _db()
    await AnalyticsService(db).record_anomaly_ack(
        anomaly_id="anom-1", acked=False, note="", acknowledged_by=None,
    )
    assert db.execute.call_args.args[1] == "OPEN"


# ── digests ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_digest_skips_inactive_roles():
    db = _db()
    with patch("services.digest_service.DigestService.get_config", new_callable=AsyncMock,
               return_value={"active": False, "schedules": {"weekly": {"enabled": True}}, "recipients": []}):
        result = await AnalyticsService(db).build_digest(tenant_id="t-1", digest_type="weekly")
    assert result["data"] == {}


@pytest.mark.asyncio
async def test_build_digest_includes_active_configured_roles():
    db = _db()
    config = {"active": True, "schedules": {"weekly": {"enabled": True}}, "recipients": ["chro-1"]}
    with patch("services.digest_service.DigestService.get_config", new_callable=AsyncMock, return_value=config), \
         patch("services.digest_service.DigestService.build_chro_digest", new_callable=AsyncMock,
               return_value={"docs_processed": 5}), \
         patch("services.digest_service.DigestService.build_cfo_digest", new_callable=AsyncMock,
               return_value={"docs_processed": 5}), \
         patch("services.digest_service.DigestService.build_ciso_digest", new_callable=AsyncMock,
               return_value={"docs_processed": 5}):
        result = await AnalyticsService(db).build_digest(tenant_id="t-1", digest_type="weekly")
    assert "chro" in result["data"]
    assert result["data"]["chro"]["recipients"] == ["chro-1"]


@pytest.mark.asyncio
async def test_send_digest_email_notifies_each_recipient():
    db = _db()
    db.fetchval.return_value = "chro@acme.example"
    kafka = AsyncMock()
    await AnalyticsService(db, kafka=kafka).send_digest_email(
        tenant_id="t-1", digest_type="weekly",
        data={"chro": {"recipients": ["chro-1", "chro-2"], "content": {"a": 1}}},
    )
    assert kafka.communication_requested.await_count == 2
    # Regression: EmailConsumer requires recipient_email or it silently skips —
    # this used to publish only a bare recipient_id (an oa_user_id) with no email
    # lookup at all, so every digest email was dropped. Content also used to sit
    # under a dead "payload" key that EmailConsumer/NotificationService never read.
    first_call = kafka.communication_requested.call_args_list[0][0][0]
    assert first_call["recipient_email"] == "chro@acme.example"
    assert first_call["template_data"] == {"a": 1}
    assert "payload" not in first_call


@pytest.mark.asyncio
async def test_send_digest_email_skips_recipient_email_gracefully_when_not_found():
    db = _db()
    db.fetchval.return_value = None
    kafka = AsyncMock()
    await AnalyticsService(db, kafka=kafka).send_digest_email(
        tenant_id="t-1", digest_type="weekly",
        data={"chro": {"recipients": ["chro-gone"], "content": {}}},
    )
    kafka.communication_requested.assert_awaited_once()
    assert "recipient_email" not in kafka.communication_requested.call_args[0][0]


# ── peer benchmark ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_peer_benchmark_delegates_to_benchmarking_service():
    db = _db()
    with patch("services.benchmarking_service.BenchmarkingService.get_market_median",
               new_callable=AsyncMock, return_value={"suppressed": False, "p50": 900000}) as mock_median:
        result = await AnalyticsService(db).build_peer_benchmark(
            tenant_id="t-1", grade="L2", department="Sales",
        )
    mock_median.assert_awaited_once_with(grade="L2", department="Sales")
    assert result["band_label"] == "L2:Sales"


@pytest.mark.asyncio
async def test_write_peer_benchmark_updates_existing_row_when_present():
    db = AsyncMock()
    db.execute.return_value = "UPDATE 1"
    await AnalyticsService(db).write_peer_benchmark(
        tenant_id="t-1", band_label="L2:Sales", cache_value={"p50": 900000},
    )
    db.execute.assert_awaited_once()
    assert "UPDATE insight_cache" in db.execute.call_args.args[0]


@pytest.mark.asyncio
async def test_write_peer_benchmark_inserts_when_no_existing_row():
    """Regression guard: insight_cache's unique index includes a nullable
    period_month, which Postgres/YugabyteDB treats as distinct-per-NULL by
    default — an ON CONFLICT there would never match an existing NULL-period
    row and would either silently duplicate rows or error, depending on driver
    behavior. This uses an explicit update-then-insert instead."""
    db = AsyncMock()
    db.execute.side_effect = ["UPDATE 0", None]
    await AnalyticsService(db).write_peer_benchmark(
        tenant_id="t-1", band_label="L2:Sales", cache_value={"p50": 900000},
    )
    assert db.execute.await_count == 2
    assert "INSERT INTO insight_cache" in db.execute.call_args_list[1].args[0]
