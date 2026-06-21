"""
Tests for the manifest-driven Stage04Extract.

Tests are split into logical groups:
  - OCR format dispatch (unit, no LLM)
  - Manifest-driven extraction (mock LLM)
  - AUTO_DETECT path (mock LLM + manifests)
  - AutoDetectFailed path
  - NIK redaction before LLM call
  - Unsupported format rejection
  - Legacy fallback when no manifest
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Optional

from pipeline.stage04_extract import Stage04Extract, Stage04Result, AutoDetectFailed, AUTO_DETECT_MIN_SCORE
from manifest.manifest_client import ManifestData


# ── Helpers ────────────────────────────────────────────────────────────────────

def _manifest(
    doc_type="SALARY_SLIP",
    required_fields=None,
    identity_fields=None,
    optional_fields=None,
    classification_signals=None,
    supported_formats=None,
    confidence_threshold=0.75,
) -> ManifestData:
    return ManifestData(
        manifest_id="m-001",
        tenant_id=None,
        doc_type=doc_type,
        required_fields=required_fields or ["employee_name", "net_pay"],
        identity_fields=identity_fields or ["pan_number", "employee_id"],
        optional_fields=optional_fields or ["designation"],
        classification_signals=classification_signals or [["net_pay", "pay_period_month"]],
        confidence_threshold=confidence_threshold,
        supported_formats=supported_formats or ["pdf", "docx", "jpeg", "jpg", "png"],
        is_tenant_override=False,
    )


def _llm_response(fields=None, confidence=0.92):
    """Synthetic LLM JSON output."""
    base = {
        "overall_confidence": confidence,
        "employee_name": {"value": "Rahul Kumar", "confidence": 0.95},
        "net_pay": {"value": 75000, "confidence": 0.90},
    }
    if fields:
        base.update(fields)
    return json.dumps(base)


def _make_stage04(llm_response_text=None, manifests=None):
    mock_llm = AsyncMock()
    mock_llm.complete.return_value = llm_response_text or _llm_response()

    mock_manifest_client = AsyncMock()
    if manifests is not None:
        mock_manifest_client.list_all.return_value = manifests
    else:
        mock_manifest_client.list_all.return_value = [_manifest()]

    svc = Stage04Extract(
        llm_client=mock_llm,
        manifest_client=mock_manifest_client,
    )
    return svc, mock_llm, mock_manifest_client


# ── OCR format dispatch ────────────────────────────────────────────────────────

def test_ocr_pdf_returns_text():
    """PDF OCR must return non-empty string from PyMuPDF."""
    import fitz
    doc = fitz.open()  # empty PDF
    page = doc.new_page()
    page.insert_text((50, 100), "SALARY SLIP NET PAY 50000")
    pdf_bytes = doc.tobytes()
    doc.close()

    svc, _, _ = _make_stage04()
    text = svc._ocr_pdf(pdf_bytes)
    assert "SALARY SLIP" in text or "50000" in text


def test_ocr_dispatches_by_extension():
    svc, _, _ = _make_stage04()
    with patch.object(svc, "_ocr_pdf", return_value="pdf text") as mock_pdf:
        text, fmt = svc._ocr(b"bytes", "pdf")
        mock_pdf.assert_called_once()
        assert fmt == "pdf"


def test_ocr_unknown_extension_falls_back_to_textract():
    svc, _, _ = _make_stage04()
    with patch.object(svc, "_textract_ocr", return_value="textract text") as mock_tx:
        text, fmt = svc._ocr(b"bytes", "rtf")  # unsupported
        mock_tx.assert_called_once()
        assert fmt == "textract"


def test_ocr_primary_failure_uses_textract_fallback():
    svc, _, _ = _make_stage04()
    with patch.object(svc, "_ocr_pdf", side_effect=RuntimeError("corrupt")):
        with patch.object(svc, "_textract_ocr", return_value="fallback") as mock_tx:
            text, fmt = svc._ocr(b"bytes", "pdf")
            assert text == "fallback"
            assert fmt == "textract"


def test_ocr_xlsx_dispatches():
    svc, _, _ = _make_stage04()
    with patch.object(svc, "_ocr_xlsx", return_value="sheet data") as mock_xl:
        text, fmt = svc._ocr(b"bytes", "xlsx")
        mock_xl.assert_called_once()
        assert fmt == "xlsx"


def test_ocr_image_dispatches():
    svc, _, _ = _make_stage04()
    with patch.object(svc, "_ocr_image", return_value="image text") as mock_img:
        text, fmt = svc._ocr(b"bytes", "png")
        mock_img.assert_called_once()
        assert fmt == "image"


# ── NIK / PAN redaction ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pan_redacted_before_llm_call():
    """Raw PAN must never reach the LLM — must be replaced with [NIK_REDACTED]."""
    svc, mock_llm, mock_mc = _make_stage04()
    manifest = _manifest()
    mock_mc.resolve.return_value = manifest

    pan_text = "Employee PAN: ABCDE1234F salary slip march"
    with patch.object(svc, "_ocr_pdf", return_value=pan_text):
        with patch.object(svc, "_extract_with_manifest", return_value=Stage04Result(
            extracted_fields={}, overall_confidence=0.9,
            low_confidence_fields=[], doc_type="SALARY_SLIP",
            manifest_id="m-001", format_used="pdf", auto_detected=False,
        )) as mock_extract:
            await svc.run(
                file_bytes=b"fake_pdf",
                ext="pdf",
                doc_type="SALARY_SLIP",
                tenant_id="t-001",
            )
            # The redacted text passed to _extract_with_manifest must not contain PAN
            call_args = mock_extract.call_args
            redacted_text = call_args[0][1] if call_args[0] else call_args[1].get("redacted_text", "")
            assert "ABCDE1234F" not in redacted_text
            assert "[NIK_REDACTED]" in redacted_text


# ── Manifest-driven extraction (declared doc_type) ─────────────────────────────

@pytest.mark.asyncio
async def test_declared_doc_type_uses_manifest():
    svc, mock_llm, mock_mc = _make_stage04()
    manifest = _manifest(doc_type="SALARY_SLIP")
    mock_mc.resolve.return_value = manifest

    with patch.object(svc, "_ocr_pdf", return_value="salary slip text"):
        result = await svc.run(
            file_bytes=b"bytes",
            ext="pdf",
            doc_type="SALARY_SLIP",
            tenant_id="t-001",
        )

    assert isinstance(result, Stage04Result)
    assert result.doc_type == "SALARY_SLIP"
    assert result.auto_detected is False


@pytest.mark.asyncio
async def test_low_confidence_fields_detected():
    """Fields below confidence_threshold must appear in low_confidence_fields."""
    svc, mock_llm, mock_mc = _make_stage04(
        llm_response_text=json.dumps({
            "overall_confidence": 0.80,
            "employee_name": {"value": "Rahul", "confidence": 0.85},
            "net_pay": {"value": 50000, "confidence": 0.60},  # below 0.75 threshold
        })
    )
    manifest = _manifest(
        required_fields=["employee_name", "net_pay"],
        confidence_threshold=0.75,
    )
    mock_mc.resolve.return_value = manifest

    with patch.object(svc, "_ocr_pdf", return_value="salary text"):
        result = await svc.run(b"bytes", "pdf", "SALARY_SLIP", "t-001")

    assert "net_pay" in result.low_confidence_fields
    assert "employee_name" not in result.low_confidence_fields


@pytest.mark.asyncio
async def test_unsupported_format_returns_auto_detect_failed():
    """Manifest says pdf+docx only; sending xlsx must return AutoDetectFailed."""
    svc, _, mock_mc = _make_stage04()
    manifest = _manifest(supported_formats=["pdf", "docx"])
    mock_mc.resolve.return_value = manifest

    with patch.object(svc, "_ocr_xlsx", return_value="spreadsheet data"):
        result = await svc.run(b"bytes", "xlsx", "SALARY_SLIP", "t-001")

    assert isinstance(result, AutoDetectFailed)
    assert result.best_guess_doc_type == "SALARY_SLIP"


# ── AUTO_DETECT path ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_detect_classifies_best_manifest():
    """AUTO_DETECT: probe → score → full extraction with winner."""
    salary_manifest = _manifest(
        doc_type="SALARY_SLIP",
        classification_signals=[["net_pay", "pay_period_month"]],
    )
    form16_manifest = _manifest(
        doc_type="FORM_16",
        classification_signals=[["financial_year", "tds_deducted"]],
    )

    # Probe response → matches salary_slip signals
    probe_resp = json.dumps({
        "overall_confidence": 0.0,
        "net_pay": {"value": 50000, "confidence": 0.9},
        "pay_period_month": {"value": "March", "confidence": 0.85},
        "financial_year": None,
        "tds_deducted": None,
    })
    full_resp = _llm_response(confidence=0.88)

    mock_llm = AsyncMock()
    mock_llm.complete.side_effect = [probe_resp, full_resp]

    mock_mc = AsyncMock()
    mock_mc.list_all.return_value = [salary_manifest, form16_manifest]

    svc = Stage04Extract(llm_client=mock_llm, manifest_client=mock_mc)

    with patch.object(svc, "_ocr_pdf", return_value="March salary slip net pay 50000"):
        result = await svc.run(b"bytes", "pdf", "AUTO_DETECT", "t-001")

    assert isinstance(result, Stage04Result)
    assert result.doc_type == "SALARY_SLIP"
    assert result.auto_detected is True


@pytest.mark.asyncio
async def test_auto_detect_returns_failed_when_no_match():
    """AUTO_DETECT: no manifest scores above threshold → AutoDetectFailed."""
    manifest_with_no_match = _manifest(
        doc_type="SALARY_SLIP",
        classification_signals=[["net_pay", "uan_number"]],
    )

    probe_resp = json.dumps({"overall_confidence": 0.0})  # empty probe result

    mock_llm = AsyncMock()
    mock_llm.complete.return_value = probe_resp

    mock_mc = AsyncMock()
    mock_mc.list_all.return_value = [manifest_with_no_match]

    svc = Stage04Extract(llm_client=mock_llm, manifest_client=mock_mc)

    with patch.object(svc, "_ocr_pdf", return_value="some random text"):
        result = await svc.run(b"bytes", "pdf", "AUTO_DETECT", "t-001")

    assert isinstance(result, AutoDetectFailed)


@pytest.mark.asyncio
async def test_auto_detect_skips_unsupported_format_manifests():
    """AUTO_DETECT should not select a manifest that doesn't support the file's format."""
    pdf_only_manifest = _manifest(
        doc_type="FORM_16",
        classification_signals=[["financial_year", "tds_deducted"]],
        supported_formats=["pdf"],
    )

    probe_resp = json.dumps({
        "overall_confidence": 0.0,
        "financial_year": {"value": "2023-24", "confidence": 0.9},
        "tds_deducted": {"value": 20000, "confidence": 0.85},
    })

    mock_llm = AsyncMock()
    mock_llm.complete.return_value = probe_resp

    mock_mc = AsyncMock()
    mock_mc.list_all.return_value = [pdf_only_manifest]

    svc = Stage04Extract(llm_client=mock_llm, manifest_client=mock_mc)

    # File is XLSX — FORM_16 manifest doesn't support it
    with patch.object(svc, "_ocr_xlsx", return_value="financial year 2023-24"):
        result = await svc.run(b"bytes", "xlsx", "AUTO_DETECT", "t-001")

    assert isinstance(result, AutoDetectFailed)


# ── Legacy fallback ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_falls_back_to_legacy_when_no_manifest():
    """When manifest_client returns ValueError, use legacy ExtractionService."""
    svc, mock_llm, mock_mc = _make_stage04()
    mock_mc.resolve.side_effect = ValueError("No manifest for SALARY_SLIP")

    with patch.object(svc, "_ocr_pdf", return_value="salary text"):
        with patch.object(svc, "_legacy_extract", return_value=Stage04Result(
            extracted_fields={"employee_name": {"value": "A", "confidence": 0.9}},
            overall_confidence=0.9,
            low_confidence_fields=[],
            doc_type="SALARY_SLIP",
            manifest_id="legacy",
            format_used="pdf",
            auto_detected=False,
        )) as mock_legacy:
            result = await svc.run(b"bytes", "pdf", "SALARY_SLIP", "t-001")
            mock_legacy.assert_called_once()
            assert result.manifest_id == "legacy"
