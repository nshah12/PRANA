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

from routers.pipeline import refresh_insight


def test_refresh_insight_uses_insight_llm_client_not_extraction_client():
    source = inspect.getsource(refresh_insight)

    assert "insight_llm_client" in source, \
        "refresh_insight must pass app.state.insight_llm_client to CareerInsightService"
    assert "llm_client=request.app.state.llm_client" not in source, \
        "refresh_insight must not use the extraction client (app.state.llm_client) for insights"
