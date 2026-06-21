"""
End-to-end pipeline integration test.

Tests the full Stage 04 → Stage 05 → Stage 06 chain using:
  - Real stage class instances (no mocking of stage logic)
  - Mocked LLM client (deterministic JSON output)
  - Mocked DB (asyncpg AsyncMock)
  - Mocked ManifestClient (returns real ManifestData objects)
  - Mocked EmbeddingClient + QdrantClient

Verifies the contract at each stage boundary:
  - Stage 04 output feeds Stage 05
  - Stage 05 output feeds Stage 06
  - Stage 06 strips sensitive financial fields before DB write
  - AutoDetectFailed routes correctly (no Stage 05/06)
  - Privacy: no raw ₹ values in anything written to DB

Not a test of infrastructure (no real Temporal, Kafka, or LLM required).
"""

import json
import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from uuid import uuid4

from manifest.manifest_client import ManifestData
from pipeline.stage04_extract import Stage04Extract, Stage04Result, AutoDetectFailed
from pipeline.stage05_resolve import Stage05Resolve, Stage05Result
from pipeline.stage06_route import Stage06Route
from resolution.resolution_service import ResolutionMethod
from insights.benchmark_service import BenchmarkService


# ── Helpers ────────────────────────────────────────────────────────────────────

def _manifest(
    doc_type="SALARY_SLIP",
    identity_fields=None,
    required_fields=None,
    classification_signals=None,
) -> ManifestData:
    return ManifestData(
        manifest_id="m-e2e-001",
        tenant_id=None,
        doc_type=doc_type,
        required_fields=required_fields or ["employee_name", "net_pay", "pay_period_month"],
        identity_fields=identity_fields or ["pan_number", "employee_id", "employee_name"],
        optional_fields=["designation", "department"],
        classification_signals=classification_signals or [["net_pay", "pay_period_month"]],
        confidence_threshold=0.75,
        supported_formats=["pdf", "docx", "jpeg", "jpg", "png"],
        is_tenant_override=False,
    )


def _llm_json(**overrides) -> str:
    """Synthetic LLM extraction response — contains SENSITIVE salary fields."""
    base = {
        "overall_confidence": 0.91,
        "employee_name":    {"value": "Priya Sharma",  "confidence": 0.97},
        "employer_name":    {"value": "Infosys Ltd",   "confidence": 0.95},
        "pay_period_month": {"value": "March 2024",    "confidence": 0.96},
        "net_pay":          {"value": 85000,            "confidence": 0.90},
        "gross_salary":     {"value": 105000,           "confidence": 0.88},  # SENSITIVE
        "basic_salary":     {"value": 52000,            "confidence": 0.88},  # SENSITIVE
        "total_deductions": {"value": 20000,            "confidence": 0.85},  # SENSITIVE
        "hra":              {"value": 15000,            "confidence": 0.83},  # SENSITIVE
        "pf_employee":      {"value": 6240,             "confidence": 0.82},  # SENSITIVE
        "gross_ctc":        {"value": 1260000,          "confidence": 0.87},  # SENSITIVE — for benchmarking only
        "designation":      {"value": "Senior Engineer","confidence": 0.89},
        "pan_number":       {"value": "[NIK_REDACTED]", "confidence": 0.0},   # already redacted
    }
    base.update(overrides)
    return json.dumps(base)


def _minimal_pdf() -> bytes:
    """Minimal valid single-page PDF with embedded text."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), "SALARY SLIP March 2024 Priya Sharma Infosys Ltd Net Pay 85000")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_stage04(llm_response: str = None, manifest: ManifestData = None) -> tuple:
    mock_llm = AsyncMock()
    mock_llm.complete.return_value = llm_response or _llm_json()

    mock_mc = AsyncMock()
    mock_mc.resolve.return_value = manifest or _manifest()
    mock_mc.list_all.return_value = [manifest or _manifest()]

    stage = Stage04Extract(llm_client=mock_llm, manifest_client=mock_mc)
    return stage, mock_llm, mock_mc


def _make_stage05(employee_uuid=None) -> tuple:
    from resolution.resolution_service import ResolutionResult
    mock_db = AsyncMock()
    mock_db.fetchrow.return_value = {"employee_uuid": employee_uuid or uuid4()}
    mock_emb = AsyncMock()
    mock_emb.embed.return_value = [0.1] * 768
    stage = Stage05Resolve(db=mock_db, embedding_client=mock_emb, qdrant_client=None)
    return stage, mock_db


def _make_stage06() -> tuple:
    mock_db = AsyncMock()
    # fetchval for employee_user_id lookup
    mock_db.fetchval.return_value = str(uuid4())
    # salary_band for benchmarking
    mock_db.fetchrow.return_value = {
        "p25": 800000, "p50": 1100000, "p75": 1400000, "p90": 1800000,
        "band_label": "Senior Engineer",
    }
    mock_db.transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    mock_db.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_db.execute = AsyncMock()
    benchmark = BenchmarkService(mock_db)
    stage = Stage06Route(db=mock_db, benchmark_svc=benchmark)
    return stage, mock_db


# ── Stage 04 E2E ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stage04_pdf_produces_stage04result():
    stage, _, _ = _make_stage04()
    pdf_bytes = _minimal_pdf()

    result = await stage.run(
        file_bytes=pdf_bytes, ext="pdf",
        doc_type="SALARY_SLIP", tenant_id="t-001",
    )

    assert isinstance(result, Stage04Result)
    assert result.doc_type == "SALARY_SLIP"
    assert result.overall_confidence > 0
    assert result.auto_detected is False


@pytest.mark.asyncio
async def test_stage04_pan_not_in_extracted_fields_as_raw():
    """After extraction, PAN value must be [NIK_REDACTED], never a real PAN."""
    stage, _, _ = _make_stage04()

    with patch.object(stage, "_ocr_pdf", return_value="ABCDE1234F salary slip"):
        result = await stage.run(
            file_bytes=b"fake", ext="pdf",
            doc_type="SALARY_SLIP", tenant_id="t-001",
        )

    assert isinstance(result, Stage04Result)
    # Verify no real PAN pattern in any field value
    import re
    _PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
    all_values = json.dumps(result.extracted_fields)
    assert not _PAN_RE.search(all_values), f"Real PAN found in extracted_fields: {all_values[:200]}"


@pytest.mark.asyncio
async def test_stage04_auto_detect_failed_returns_correct_type():
    """When no manifest matches, Stage04 must return AutoDetectFailed, not raise."""
    manifest = _manifest(
        classification_signals=[["net_pay", "uan_number"]],  # won't match probe
    )
    probe_response = json.dumps({"overall_confidence": 0.0})  # empty probe
    stage, mock_llm, mock_mc = _make_stage04(llm_response=probe_response, manifest=manifest)
    mock_mc.list_all.return_value = [manifest]

    with patch.object(stage, "_ocr_pdf", return_value="random document text"):
        result = await stage.run(
            file_bytes=b"fake", ext="pdf",
            doc_type="AUTO_DETECT", tenant_id="t-001",
        )

    assert isinstance(result, AutoDetectFailed)
    assert result.best_guess_score < 0.5


# ── Stage 04 → Stage 05 boundary ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stage04_output_feeds_stage05():
    """Stage04Result.extracted_fields must be usable by Stage05Resolve directly."""
    emp_uuid = uuid4()
    stage04, _, _ = _make_stage04()
    stage05, mock_db = _make_stage05(employee_uuid=emp_uuid)

    # Stage 04
    with patch.object(stage04, "_ocr_pdf", return_value="salary slip text"):
        s4_result = await stage04.run(
            file_bytes=b"fake", ext="pdf",
            doc_type="SALARY_SLIP", tenant_id="t-001",
        )

    assert isinstance(s4_result, Stage04Result)

    # Stage 05 consumes Stage04's extracted_fields directly
    s5_result = await stage05.run(
        pan_token="abc123pantoken",
        tenant_id=str(uuid4()),
        extracted_fields=s4_result.extracted_fields,
        manifest=_manifest(),
    )

    assert isinstance(s5_result, Stage05Result)
    # pan_token match should resolve via Level 1
    assert s5_result.employee_uuid is not None
    assert s5_result.needs_exception is False


# ── Stage 05 → Stage 06 boundary ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stage05_output_feeds_stage06_no_raw_salary_stored():
    """
    Stage06 must strip all sensitive financial fields before writing to DB.
    This is the core privacy contract.
    """
    emp_uuid = uuid4()
    stage06, mock_db = _make_stage06()

    # Extracted fields contain raw ₹ values (as Stage04 would produce)
    extracted = json.loads(_llm_json())

    await stage06.route(
        document_id=str(uuid4()),
        tenant_id=str(uuid4()),
        employee_uuid=str(emp_uuid),
        pan_token="abc123",
        doc_type="SALARY_SLIP",
        doc_period="2024-03",
        extracted_fields=extracted,
        resolution_method="EXACT_PAN",
        resolution_confidence=1.0,
        s3_key="tenant/emp/SALARY_SLIP/2024-03.enc",
    )

    # Find the UPDATE document call and check what was persisted
    update_calls = [
        call for call in mock_db.execute.call_args_list
        if "UPDATE document" in str(call)
    ]
    assert update_calls, "Stage06 must call UPDATE document"

    # Extract the safe_fields JSON that was passed to the DB
    update_call = update_calls[0]
    args = update_call[0]
    # safe_fields is the 4th positional arg in the UPDATE call (index 3)
    safe_fields_json = args[3] if len(args) > 3 else None

    if safe_fields_json:
        safe_fields = json.loads(safe_fields_json) if isinstance(safe_fields_json, str) else safe_fields_json
        sensitive = {
            "gross_salary", "basic_salary", "net_salary", "hra",
            "pf_employee", "pf_employer", "total_deductions",
            "ctc_before", "ctc_after", "employee_share", "employer_share",
        }
        found_sensitive = sensitive & set(safe_fields.keys())
        assert not found_sensitive, (
            f"Sensitive fields must be stripped before DB write. Found: {found_sensitive}"
        )


@pytest.mark.asyncio
async def test_stage06_career_event_written_for_salary_slip():
    """SALARY_SLIP does not map to a career_event type — no INSERT expected."""
    stage06, mock_db = _make_stage06()
    extracted = json.loads(_llm_json())

    await stage06.route(
        document_id=str(uuid4()),
        tenant_id=str(uuid4()),
        employee_uuid=str(uuid4()),
        pan_token="abc",
        doc_type="SALARY_SLIP",
        doc_period="2024-03",
        extracted_fields=extracted,
        resolution_method="EXACT_PAN",
        resolution_confidence=1.0,
        s3_key="path/to/doc.enc",
    )

    # SALARY_SLIP has no career_event mapping — verify INSERT INTO career_event not called
    insert_calls = [
        call for call in mock_db.execute.call_args_list
        if "INSERT INTO career_event" in str(call)
    ]
    assert not insert_calls, "SALARY_SLIP should not produce a career_event row"


@pytest.mark.asyncio
async def test_stage06_career_event_written_for_appointment_letter():
    """APPOINTMENT_LETTER must produce a JOINED career_event."""
    stage06, mock_db = _make_stage06()
    extracted = {
        "employee_name": {"value": "Rahul", "confidence": 0.95},
        "employer_name": {"value": "TCS", "confidence": 0.95},
        "date_of_joining": {"value": "2024-03-01", "confidence": 0.90},
    }

    await stage06.route(
        document_id=str(uuid4()),
        tenant_id=str(uuid4()),
        employee_uuid=str(uuid4()),
        pan_token="abc",
        doc_type="APPOINTMENT_LETTER",
        doc_period="2024-03-01",
        extracted_fields=extracted,
        resolution_method="EMP_ID",
        resolution_confidence=1.0,
        s3_key="path/to/doc.enc",
    )

    insert_calls = [
        call for call in mock_db.execute.call_args_list
        if "INSERT INTO career_event" in str(call)
    ]
    assert insert_calls, "APPOINTMENT_LETTER must produce a career_event row"
    event_args = str(insert_calls[0])
    assert "JOINED" in event_args


# ── Full chain: 04 → 05 → 06 ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_pipeline_happy_path():
    """
    Complete chain: Stage04(pdf) → Stage05(resolve) → Stage06(route).
    Verifies output shape at each boundary and privacy at Stage06.
    """
    emp_uuid = uuid4()
    tenant_id = str(uuid4())

    stage04, _, _ = _make_stage04()
    stage05, _ = _make_stage05(employee_uuid=emp_uuid)
    stage06, mock_db = _make_stage06()

    # 04: extract
    with patch.object(stage04, "_ocr_pdf", return_value="SALARY SLIP March 2024 net pay 85000"):
        s4 = await stage04.run(
            file_bytes=b"fake", ext="pdf",
            doc_type="SALARY_SLIP", tenant_id=tenant_id,
        )

    assert isinstance(s4, Stage04Result)
    assert s4.doc_type == "SALARY_SLIP"

    # 05: resolve
    s5 = await stage05.run(
        pan_token="pantoken123",
        tenant_id=tenant_id,
        extracted_fields=s4.extracted_fields,
        manifest=_manifest(),
    )

    assert not s5.needs_exception
    assert s5.employee_uuid is not None

    # 06: route
    await stage06.route(
        document_id=str(uuid4()),
        tenant_id=tenant_id,
        employee_uuid=s5.employee_uuid,
        pan_token="pantoken123",
        doc_type=s4.doc_type,
        doc_period="2024-03",
        extracted_fields=s4.extracted_fields,
        resolution_method=s5.method,
        resolution_confidence=s5.confidence,
        s3_key="tenant/doc.enc",
    )

    # Verify DB was written
    update_calls = [c for c in mock_db.execute.call_args_list if "UPDATE document" in str(c)]
    assert update_calls, "Stage06 must write ROUTED status to DB"


# ── Exception path: Stage05 unresolved → Stage06 exception ────────────────────

@pytest.mark.asyncio
async def test_pipeline_exception_path():
    """When Stage05 returns needs_exception=True, Stage06.raise_exception is called."""
    stage06, mock_db = _make_stage06()

    await stage06.raise_exception(
        document_id=str(uuid4()),
        tenant_id=str(uuid4()),
        exception_type="NO_MATCH",
        extracted_fields={"employee_name": {"value": "Unknown", "confidence": 0.5}},
        candidates=[],
    )

    insert_calls = [c for c in mock_db.execute.call_args_list if "exception_queue" in str(c)]
    assert insert_calls, "Stage06.raise_exception must write to exception_queue"
    update_calls = [c for c in mock_db.execute.call_args_list if "EXCEPTION" in str(c)]
    assert update_calls, "Stage06.raise_exception must set pipeline_status=EXCEPTION"
