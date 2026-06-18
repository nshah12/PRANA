"""
Stage 06 privacy boundary tests.

Verifies that sensitive raw financial fields are stripped from extracted_fields
before any DB write. The pipeline's main privacy guarantee is enforced here.
"""
import json
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from pipeline.stage06_route import Stage06Route, _SENSITIVE_FIELDS


def _make_extracted(include_sensitive=True):
    fields = {
        "employee_name": {"value": "Priya Mehta", "confidence": 0.97},
        "designation":   {"value": "Senior Engineer", "confidence": 0.95},
        "employer_name": {"value": "Infosys Ltd", "confidence": 0.96},
    }
    if include_sensitive:
        fields.update({
            "gross_salary":    {"value": "95000", "confidence": 0.93},
            "basic_salary":    {"value": "47500", "confidence": 0.93},
            "net_salary":      {"value": "82000", "confidence": 0.92},
            "hra":             {"value": "9500",  "confidence": 0.91},
            "pf_employee":     {"value": "5700",  "confidence": 0.90},
            "total_deductions":{"value": "13000", "confidence": 0.90},
        })
    return fields


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value="emp-user-uuid-001")
    db.execute = AsyncMock()
    db.transaction = MagicMock(
        return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
    )
    return db


@pytest.fixture
def mock_benchmark():
    svc = AsyncMock()
    svc.build_career_context = AsyncMock(return_value={"salary_band": "P70"})
    return svc


@pytest.mark.asyncio
async def test_sensitive_fields_stripped_before_db_write(mock_db, mock_benchmark):
    """extracted_fields written to DB must never contain raw financial fields."""
    stage = Stage06Route(db=mock_db, benchmark_svc=mock_benchmark)

    await stage.route(
        document_id="doc-001",
        tenant_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        employee_uuid="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        pan_token="pan_tok_abc123",
        doc_type="SALARY_SLIP",
        doc_period="2024-03",
        extracted_fields=_make_extracted(include_sensitive=True),
        resolution_method="PAN_EXACT",
        resolution_confidence=0.99,
        s3_key="docs/tenant-001/doc-001.pdf",
    )

    # Find the UPDATE document call and parse the extracted_fields arg
    update_call = None
    for c in mock_db.execute.call_args_list:
        args = c[0]
        if args and "UPDATE document" in str(args[0]):
            update_call = args
            break

    assert update_call is not None, "UPDATE document was not called"

    # extracted_fields is the 4th positional arg (after doc_id, emp_uuid, pan_token)
    # Position may vary — find the JSONB arg
    stored = None
    for arg in update_call:
        try:
            parsed = json.loads(arg)
            if isinstance(parsed, dict) and "employee_name" in parsed:
                stored = parsed
                break
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

    assert stored is not None, "Could not find extracted_fields JSON in DB call"

    for field in _SENSITIVE_FIELDS:
        assert field not in stored, \
            f"Sensitive field '{field}' leaked into DB write"


@pytest.mark.asyncio
async def test_safe_fields_retained_after_strip(mock_db, mock_benchmark):
    """Non-sensitive fields (name, designation) must survive the strip."""
    stage = Stage06Route(db=mock_db, benchmark_svc=mock_benchmark)

    await stage.route(
        document_id="doc-002",
        tenant_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        employee_uuid="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        pan_token="pan_tok_abc123",
        doc_type="SALARY_SLIP",
        doc_period="2024-03",
        extracted_fields=_make_extracted(include_sensitive=True),
        resolution_method="PAN_EXACT",
        resolution_confidence=0.99,
        s3_key="docs/tenant-001/doc-002.pdf",
    )

    stored = None
    for c in mock_db.execute.call_args_list:
        for arg in c[0]:
            try:
                parsed = json.loads(arg)
                if isinstance(parsed, dict) and "employee_name" in parsed:
                    stored = parsed
                    break
            except (TypeError, ValueError, json.JSONDecodeError):
                continue

    assert stored is not None
    assert "employee_name" in stored
    assert "designation" in stored


@pytest.mark.asyncio
async def test_benchmark_called_before_strip(mock_db, mock_benchmark):
    """BenchmarkService must receive the full extracted_fields including salary fields."""
    stage = Stage06Route(db=mock_db, benchmark_svc=mock_benchmark)
    fields = _make_extracted(include_sensitive=True)

    await stage.route(
        document_id="doc-003",
        tenant_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        employee_uuid="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        pan_token="pan_tok_abc123",
        doc_type="SALARY_SLIP",
        doc_period="2024-03",
        extracted_fields=fields,
        resolution_method="PAN_EXACT",
        resolution_confidence=0.99,
        s3_key="docs/tenant-001/doc-003.pdf",
    )

    mock_benchmark.build_career_context.assert_called_once()
    called_fields = mock_benchmark.build_career_context.call_args[1].get(
        "extracted_fields",
        mock_benchmark.build_career_context.call_args[0][2]
        if len(mock_benchmark.build_career_context.call_args[0]) > 2 else None,
    )
    if called_fields is None:
        # keyword arg not found — check positional
        called_fields = mock_benchmark.build_career_context.call_args[0][-1]

    assert "gross_salary" in called_fields, \
        "BenchmarkService was NOT given salary fields — strip happened too early"


@pytest.mark.asyncio
async def test_raise_exception_also_strips_sensitive_fields(mock_db, mock_benchmark):
    """raise_exception path must also strip raw financials before writing to exception_queue."""
    stage = Stage06Route(db=mock_db, benchmark_svc=mock_benchmark)

    await stage.raise_exception(
        document_id="doc-004",
        tenant_id="tenant-001",
        exception_type="LOW_CONFIDENCE",
        extracted_fields=_make_extracted(include_sensitive=True),
        candidates=[],
    )

    stored = None
    for c in mock_db.execute.call_args_list:
        for arg in c[0]:
            try:
                parsed = json.loads(arg)
                if isinstance(parsed, dict) and "employee_name" in parsed:
                    stored = parsed
                    break
            except (TypeError, ValueError, json.JSONDecodeError):
                continue

    assert stored is not None, "Could not find extracted_fields in exception_queue insert"
    for field in _SENSITIVE_FIELDS:
        assert field not in stored, \
            f"Sensitive field '{field}' leaked into exception_queue"
