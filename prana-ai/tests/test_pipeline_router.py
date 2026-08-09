"""
Structural test for routers/pipeline.py's refresh_insight endpoint.

Covers: insight generation must use app.state.insight_llm_client (Llama,
config.insight_llm_model), not app.state.llm_client (Qwen, the extraction
model). Before this fix, main.py only ever constructed one shared
LLMClient — hardcoded to the extraction model — and refresh_insight passed
that same client into CareerInsightService, so every insight/RAG call
silently ran against the wrong model.

No HTTP test harness exists for prana-ai's FastAPI routers (no conftest.py,
no TestClient usage anywhere in tests/) - following the same source-inspection
convention prana-api/tests/test_tenant.py already uses for Temporal workflows.
"""
import inspect

from routers.pipeline import refresh_insight, career_insight, skill_gap


def test_refresh_insight_uses_insight_llm_client_not_extraction_client():
    source = inspect.getsource(refresh_insight)

    assert "insight_llm_client" in source, \
        "refresh_insight must pass app.state.insight_llm_client to CareerInsightService"
    assert "llm_client=request.app.state.llm_client" not in source, \
        "refresh_insight must not use the extraction client (app.state.llm_client) for insights"


def test_career_insight_uses_insight_llm_client_not_extraction_client():
    """Same regression class as refresh_insight above — CareerInsightWorkflow's
    aggregated narrative must use the Llama insight model, not Qwen."""
    source = inspect.getsource(career_insight)

    assert "insight_llm_client" in source, \
        "career_insight must pass app.state.insight_llm_client to CareerNarrativeService"
    assert "llm_client=request.app.state.llm_client" not in source, \
        "career_insight must not use the extraction client (app.state.llm_client)"


def test_career_insight_calls_career_narrative_service():
    source = inspect.getsource(career_insight)
    assert "CareerNarrativeService" in source
    assert "build_narrative" in source


def test_skill_gap_uses_insight_llm_client_not_extraction_client():
    """Same regression class as refresh_insight/career_insight above —
    SkillGapWorkflow's suggestions must use the Llama insight model, not Qwen."""
    source = inspect.getsource(skill_gap)

    assert "insight_llm_client" in source, \
        "skill_gap must pass app.state.insight_llm_client to SkillGapService"
    assert "llm_client=request.app.state.llm_client" not in source, \
        "skill_gap must not use the extraction client (app.state.llm_client)"


def test_skill_gap_calls_skill_gap_service():
    source = inspect.getsource(skill_gap)
    assert "SkillGapService" in source
    assert "build_skill_gap" in source
