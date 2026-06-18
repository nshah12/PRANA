"""Tests for insights/benchmark_service.py — privacy boundary at the ₹→percentile conversion."""
import pytest
from unittest.mock import AsyncMock
from uuid import UUID

from insights.benchmark_service import BenchmarkService, _numeric, _get

_EMP  = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_TENA = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.mark.asyncio
async def test_benchmark_output_contains_no_raw_salary_figures():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={
        "p25": 800000, "p50": 1200000, "p75": 1600000, "p90": 2000000,
        "band_label": "Senior Engineer",
    })
    svc = BenchmarkService(db)
    extracted = {
        "gross_ctc": {"value": "1400000", "confidence": 0.95},
        "designation": {"value": "Senior Engineer", "confidence": 0.99},
    }
    ctx = await svc.build_career_context(_EMP, _TENA, extracted, "SALARY_SLIP")

    assert "compensation" in ctx
    comp = ctx["compensation"]
    # Output is percentile + qualitative label — never raw rupee amount
    assert "percentile" in comp
    assert "label" in comp
    assert isinstance(comp["percentile"], int)
    # Raw salary amount must NOT appear in output
    assert "1400000" not in str(ctx)
    assert "₹" not in str(ctx)


def test_benchmark_uses_insight_text_not_rupee_amounts():
    # _benchmark_salary returns a dict with "percentile" and "label" fields —
    # never "gross_salary", "ctc", "net_salary", or any raw ₹ value.
    import inspect
    from insights.benchmark_service import BenchmarkService as BS
    src = inspect.getsource(BS._benchmark_salary)
    assert "percentile" in src, "_benchmark_salary must return percentile ranking"
    assert "label" in src, "_benchmark_salary must return a qualitative label"
    # The output dict must never include raw salary keys
    assert "gross_salary" not in src
    assert "ctc" not in src.replace("gross_ctc", "").replace("ctc_old", "").replace("ctc_new", "").replace("ctc_annual", "")
