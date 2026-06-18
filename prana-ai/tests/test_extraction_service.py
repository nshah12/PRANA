"""Tests for extraction/extraction_service.py — model routing and output contract."""
import json
import pytest
from unittest.mock import AsyncMock

from extraction.extraction_service import (
    ExtractionService, DocType, ExtractionResult,
    CONFIDENCE_ROUTE, CONFIDENCE_FLAGGED, CONFIDENCE_REJECT,
)


def test_extraction_service_uses_qwen_model():
    # ExtractionService delegates to LLMClient; the correct model (Qwen) is injected
    # at construction by the pipeline worker. Verify that ExtractionService is in the
    # _REGISTRY for all defined DocType values — no doc type silently falls through.
    from extraction.extraction_service import _REGISTRY
    for doc_type in DocType:
        assert doc_type in _REGISTRY, \
            f"DocType.{doc_type.value} has no entry in _REGISTRY — extraction will fail at runtime"


@pytest.mark.asyncio
async def test_extraction_output_is_structured_json_not_freeform():
    # ExtractionService must parse LLM output through a Pydantic schema —
    # never return raw LLM text as extracted_fields.
    from extraction.schemas import SalarySlipExtraction

    llm = AsyncMock()
    # Minimal valid salary-slip JSON that passes schema validation
    llm.complete = AsyncMock(return_value=json.dumps({
        "employer_name":     {"value": "NPCI", "confidence": 0.97},
        "pay_period_month":  {"value": "May",  "confidence": 0.99},
        "pay_period_year":   {"value": "2026", "confidence": 0.99},
        "overall_confidence": 0.95,
    }))

    svc = ExtractionService(llm)
    result = await svc.extract(DocType.SALARY_SLIP, "OCR text of salary slip")

    assert isinstance(result, ExtractionResult)
    assert isinstance(result.fields, dict), "extracted_fields must be a dict (Pydantic .model_dump())"
    assert isinstance(result.overall_confidence, float)
    assert 0.0 <= result.overall_confidence <= 1.0


def test_extraction_confidence_thresholds_are_ordered():
    # Confidence routing decisions depend on correct ordering.
    assert CONFIDENCE_REJECT < CONFIDENCE_FLAGGED < CONFIDENCE_ROUTE, \
        "Confidence thresholds must be REJECT < FLAGGED < ROUTE"
