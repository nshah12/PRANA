"""
RED tests for pipeline/errors.py — PipelineError StrEnum + PipelineException.

Run: cd prana-ai && pytest tests/test_pipeline_errors.py -v
All tests must FAIL until errors.py is implemented.
"""
import pytest


# ── imports (will fail until errors.py exists) ────────────────────────────────

def test_pipeline_error_enum_importable():
    """PipelineError must be importable as a StrEnum."""
    from pipeline.errors import PipelineError
    assert issubclass(PipelineError, str)


def test_pipeline_exception_importable():
    """PipelineException must be importable from pipeline.errors."""
    from pipeline.errors import PipelineException
    assert issubclass(PipelineException, Exception)


# ── Error code coverage — at least one code per stage ────────────────────────

def test_s01_ingest_codes_exist():
    from pipeline.errors import PipelineError
    assert hasattr(PipelineError, "S01_INGEST_FILE_MISSING")
    assert hasattr(PipelineError, "S01_INGEST_SIZE_EXCEEDED")
    assert hasattr(PipelineError, "S01_INGEST_EXT_REJECTED")
    assert hasattr(PipelineError, "S01_INGEST_S3_UPLOAD_FAILED")
    assert hasattr(PipelineError, "S01_INGEST_DB_INSERT_FAILED")


def test_s02_encrypt_codes_exist():
    from pipeline.errors import PipelineError
    assert hasattr(PipelineError, "S02_ENCRYPT_KMS_UNAVAILABLE")
    assert hasattr(PipelineError, "S02_ENCRYPT_KMS_PERMISSION_DENIED")
    assert hasattr(PipelineError, "S02_ENCRYPT_FF3_INIT_FAILED")
    assert hasattr(PipelineError, "S02_ENCRYPT_FF3_PAN_FAILED")
    assert hasattr(PipelineError, "S02_ENCRYPT_AES_FAILED")
    assert hasattr(PipelineError, "S02_ENCRYPT_S3_UPLOAD_FAILED")
    assert hasattr(PipelineError, "S02_ENCRYPT_OCR_TESSERACT_FAILED")
    assert hasattr(PipelineError, "S02_ENCRYPT_OCR_TEXTRACT_FAILED")
    assert hasattr(PipelineError, "S02_ENCRYPT_PAN_NOT_FOUND")
    assert hasattr(PipelineError, "S02_ENCRYPT_MULTIPLE_PANS")


def test_s03_scan_codes_exist():
    from pipeline.errors import PipelineError
    assert hasattr(PipelineError, "S03_SCAN_CLAMD_UNAVAILABLE")
    assert hasattr(PipelineError, "S03_SCAN_CLAMD_TIMEOUT")
    assert hasattr(PipelineError, "S03_SCAN_VIRUS_DETECTED")
    assert hasattr(PipelineError, "S03_SCAN_NSFW_EXPLICIT")
    assert hasattr(PipelineError, "S03_SCAN_NSFW_SUGGESTIVE")
    assert hasattr(PipelineError, "S03_SCAN_PHOTODNA_UNAVAILABLE")
    assert hasattr(PipelineError, "S03_SCAN_CSAM_DETECTED")
    assert hasattr(PipelineError, "S03_SCAN_FORMAT_UNSUPPORTED")


def test_s04_extract_codes_exist():
    from pipeline.errors import PipelineError
    assert hasattr(PipelineError, "S04_EXTRACT_PDF_FAILED")
    assert hasattr(PipelineError, "S04_EXTRACT_DOCX_FAILED")
    assert hasattr(PipelineError, "S04_EXTRACT_XLSX_FAILED")
    assert hasattr(PipelineError, "S04_EXTRACT_OCR_TESSERACT_UNAVAILABLE")
    assert hasattr(PipelineError, "S04_EXTRACT_OCR_TESSERACT_TIMEOUT")
    assert hasattr(PipelineError, "S04_EXTRACT_OCR_TEXTRACT_UNAVAILABLE")
    assert hasattr(PipelineError, "S04_EXTRACT_OCR_TEXTRACT_QUOTA")
    assert hasattr(PipelineError, "S04_EXTRACT_OCR_BLANK_OUTPUT")
    assert hasattr(PipelineError, "S04_EXTRACT_OCR_LOW_CONFIDENCE")
    assert hasattr(PipelineError, "S04_EXTRACT_PASSWORD_PROTECTED")
    assert hasattr(PipelineError, "S04_EXTRACT_MANIFEST_NOT_FOUND")
    assert hasattr(PipelineError, "S04_EXTRACT_LLM_UNAVAILABLE")
    assert hasattr(PipelineError, "S04_EXTRACT_LLM_TIMEOUT")
    assert hasattr(PipelineError, "S04_EXTRACT_LLM_JSON_INVALID")
    assert hasattr(PipelineError, "S04_EXTRACT_LLM_SCHEMA_INVALID")
    assert hasattr(PipelineError, "S04_EXTRACT_LOW_CONFIDENCE")
    assert hasattr(PipelineError, "S04_EXTRACT_AUTODETECT_FAILED")
    assert hasattr(PipelineError, "S04_EXTRACT_CORRUPTED")
    assert hasattr(PipelineError, "S04_EXTRACT_DARK_IMAGE")


def test_s05_resolve_codes_exist():
    from pipeline.errors import PipelineError
    assert hasattr(PipelineError, "S05_RESOLVE_CROSS_TENANT")
    assert hasattr(PipelineError, "S05_RESOLVE_L1_DB_ERROR")
    assert hasattr(PipelineError, "S05_RESOLVE_L3_MULTIPLE_CANDIDATES")
    assert hasattr(PipelineError, "S05_RESOLVE_L4_EMBEDDING_FAILED")
    assert hasattr(PipelineError, "S05_RESOLVE_L4_QDRANT_UNAVAILABLE")
    assert hasattr(PipelineError, "S05_RESOLVE_UNRESOLVED")
    assert hasattr(PipelineError, "S05_RESOLVE_MANIFEST_FETCH_FAILED")


def test_s06_route_codes_exist():
    from pipeline.errors import PipelineError
    assert hasattr(PipelineError, "S06_ROUTE_DB_TRANSACTION_FAILED")
    assert hasattr(PipelineError, "S06_ROUTE_S3_MOVE_FAILED")
    assert hasattr(PipelineError, "S06_ROUTE_ALREADY_TERMINAL")
    assert hasattr(PipelineError, "S06_ROUTE_EXCEPTION_QUEUE_FAILED")
    assert hasattr(PipelineError, "S06_ROUTE_INTERNAL_CALLBACK_FAILED")
    assert hasattr(PipelineError, "S06_ROUTE_LEGAL_HOLD_BLOCK")


def test_infra_codes_exist():
    from pipeline.errors import PipelineError
    assert hasattr(PipelineError, "INFRA_DB_UNAVAILABLE")
    assert hasattr(PipelineError, "INFRA_REDIS_UNAVAILABLE")
    assert hasattr(PipelineError, "INFRA_S3_UNAVAILABLE")
    assert hasattr(PipelineError, "INFRA_KMS_UNAVAILABLE")
    assert hasattr(PipelineError, "INFRA_LLM_URL_MISSING")
    assert hasattr(PipelineError, "INFRA_QDRANT_UNAVAILABLE")
    assert hasattr(PipelineError, "INFRA_CONFIG_MISSING")


# ── PipelineException structure ───────────────────────────────────────────────

def test_pipeline_exception_carries_code_and_stage():
    from pipeline.errors import PipelineError, PipelineException
    exc = PipelineException(
        code=PipelineError.S04_EXTRACT_LLM_TIMEOUT,
        stage="stage04",
        message="LLM call timed out after 120s",
    )
    assert exc.code == PipelineError.S04_EXTRACT_LLM_TIMEOUT
    assert exc.stage == "stage04"
    assert "timed out" in exc.message
    assert str(exc) == f"[stage04] {PipelineError.S04_EXTRACT_LLM_TIMEOUT}: LLM call timed out after 120s"


def test_pipeline_exception_retryable_default():
    """Exceptions are retryable by default — Temporal will retry them."""
    from pipeline.errors import PipelineError, PipelineException
    exc = PipelineException(code=PipelineError.INFRA_DB_UNAVAILABLE, stage="stage06", message="pool timeout")
    assert exc.retryable is True


def test_pipeline_exception_non_retryable():
    """CSAM / cross-tenant / LOW_CONFIDENCE are non-retryable — Temporal must not retry."""
    from pipeline.errors import PipelineError, PipelineException
    for code in (
        PipelineError.S03_SCAN_CSAM_DETECTED,
        PipelineError.S05_RESOLVE_CROSS_TENANT,
        PipelineError.S04_EXTRACT_PASSWORD_PROTECTED,
        PipelineError.S06_ROUTE_LEGAL_HOLD_BLOCK,
    ):
        exc = PipelineException(code=code, stage="stage", message="test")
        assert exc.retryable is False, f"{code} should be non-retryable"


def test_pipeline_exception_retryable_false_explicit():
    """Caller can override retryable flag."""
    from pipeline.errors import PipelineError, PipelineException
    exc = PipelineException(
        code=PipelineError.S04_EXTRACT_OCR_BLANK_OUTPUT,
        stage="stage04",
        message="blank",
        retryable=False,
    )
    assert exc.retryable is False


def test_pipeline_exception_inherits_from_exception():
    from pipeline.errors import PipelineException, PipelineError
    exc = PipelineException(code=PipelineError.INFRA_S3_UNAVAILABLE, stage="s1", message="s3 down")
    assert isinstance(exc, Exception)
    with pytest.raises(PipelineException):
        raise exc


def test_pipeline_error_values_are_strings():
    """StrEnum — every value must be a non-empty string (usable in HTTP error bodies)."""
    from pipeline.errors import PipelineError
    for member in PipelineError:
        assert isinstance(member.value, str)
        assert len(member.value) > 0


def test_pipeline_error_value_matches_name():
    """Each error code's value must equal its name for easy JSON serialization."""
    from pipeline.errors import PipelineError
    for member in PipelineError:
        assert member.value == member.name, (
            f"PipelineError.{member.name} has value {member.value!r}; expected {member.name!r}"
        )


def test_to_http_dict():
    """PipelineException.to_http_dict() must return the shape prana-api expects."""
    from pipeline.errors import PipelineError, PipelineException
    exc = PipelineException(
        code=PipelineError.S04_EXTRACT_LLM_TIMEOUT,
        stage="stage04",
        message="timeout",
        retryable=True,
    )
    d = exc.to_http_dict()
    assert d["error"] == "S04_EXTRACT_LLM_TIMEOUT"
    assert d["stage"] == "stage04"
    assert d["message"] == "timeout"
    assert d["retryable"] is True
