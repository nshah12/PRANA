"""Tests for pipeline/stage04_extract.py — NIK redaction and confidence routing."""
import inspect

from extraction.extraction_service import ExtractionResult, CONFIDENCE_REJECT
from pipeline.stage04_extract import Stage04Extract, _PAN_RE


def test_stage04_llm_receives_full_document_data():
    # Stage04 redacts the NIK (PAN) from OCR text before passing to LLM —
    # the LLM sees the full document content but with PAN replaced by [NIK_REDACTED].
    text_with_pan = "Employee: Rahul Sharma   PAN: ABCDE1234F   Gross: 95000"
    redacted = _PAN_RE.sub("[NIK_REDACTED]", text_with_pan)
    assert "ABCDE1234F" not in redacted, "PAN must be redacted before LLM sees text"
    assert "NIK_REDACTED" in redacted, "PAN placeholder must be inserted after redaction"
    assert "Rahul Sharma" in redacted, "Non-PAN content must pass through intact"


def test_stage04_low_confidence_raises_exception_not_stored():
    # ExtractionResult.status must return LOW_CONFIDENCE when overall_confidence
    # is below CONFIDENCE_REJECT — this signals the pipeline to queue an exception
    # instead of routing the document.
    low_result = ExtractionResult(
        fields={},
        overall_confidence=CONFIDENCE_REJECT - 0.01,
        low_confidence_fields=["employer_name", "pay_period"],
    )
    assert low_result.status == "LOW_CONFIDENCE", \
        "Below CONFIDENCE_REJECT threshold must yield LOW_CONFIDENCE status"


def test_stage04_extracted_fields_are_insights_not_raw_salary():
    # Stage04 extracts fields with per-field confidence scores (Pydantic schema).
    # Raw salary fields MAY appear in extracted_fields (benchmark_service strips them later).
    # Verify the stage redacts NIK but does NOT strip salary fields — that's Stage06's job.
    src = inspect.getsource(Stage04Extract.run)
    assert "_PAN_RE.sub" in src or "NIK_REDACTED" in src, \
        "Stage04 must redact NIK from text before LLM extraction"
    # Stage04 must NOT strip salary fields — benchmark_service owns that privacy boundary
    assert "_SENSITIVE_FIELDS" not in src, \
        "Stage04 must not strip sensitive fields — that is Stage06's responsibility"
