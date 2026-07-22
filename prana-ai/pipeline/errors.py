"""
Structured error taxonomy for the 6-stage PRANA AI pipeline.

Usage:
    raise PipelineException(
        code=PipelineError.S04_EXTRACT_LLM_TIMEOUT,
        stage="stage04",
        message=f"LLM call timed out after {timeout}s",
    )

Temporal integration:
    - retryable=True  → Temporal retries normally (default for infra/transient errors)
    - retryable=False → prana-api raises ApplicationError(non_retryable=True) after receiving
                        this code; Temporal fails the workflow immediately

HTTP shape (from prana-ai → prana-api):
    {"error": "S04_EXTRACT_LLM_TIMEOUT", "stage": "stage04",
     "message": "...", "retryable": true}
"""
from __future__ import annotations

from enum import StrEnum


# ── Non-retryable codes ───────────────────────────────────────────────────────
# These outcomes are terminal — retrying will not help.
# Temporal must fail the workflow run immediately on receiving them.

_NON_RETRYABLE: frozenset[str] = frozenset({
    # Safety — mandatory reporting / quarantine
    "S03_SCAN_VIRUS_DETECTED",
    "S03_SCAN_NSFW_EXPLICIT",
    "S03_SCAN_CSAM_DETECTED",
    # Security — cross-tenant is a critical anomaly, not a transient error
    "S05_RESOLVE_CROSS_TENANT",
    # Document state — retrying cannot decrypt or unlock
    "S04_EXTRACT_PASSWORD_PROTECTED",
    "S04_EXTRACT_CORRUPTED",
    # Compliance — legal hold blocks routing permanently until hold lifted
    "S06_ROUTE_LEGAL_HOLD_BLOCK",
    # Pipeline already in terminal state — idempotency guard
    "S06_ROUTE_ALREADY_TERMINAL",
    # OCR blank — no text in document; retrying won't produce text
    "S04_EXTRACT_OCR_BLANK_OUTPUT",
    # Dark/unreadable image — not transient
    "S04_EXTRACT_DARK_IMAGE",
})


class PipelineError(StrEnum):
    # ── Stage 01 — Ingest ──────────────────────────────────────────────────────
    S01_INGEST_FILE_MISSING         = "S01_INGEST_FILE_MISSING"
    S01_INGEST_SIZE_EXCEEDED        = "S01_INGEST_SIZE_EXCEEDED"
    S01_INGEST_EXT_REJECTED         = "S01_INGEST_EXT_REJECTED"
    S01_INGEST_S3_UPLOAD_FAILED     = "S01_INGEST_S3_UPLOAD_FAILED"
    S01_INGEST_DB_INSERT_FAILED     = "S01_INGEST_DB_INSERT_FAILED"

    # ── Stage 02 — Encrypt ─────────────────────────────────────────────────────
    S02_ENCRYPT_KMS_UNAVAILABLE     = "S02_ENCRYPT_KMS_UNAVAILABLE"
    S02_ENCRYPT_KMS_PERMISSION_DENIED = "S02_ENCRYPT_KMS_PERMISSION_DENIED"
    S02_ENCRYPT_FF3_INIT_FAILED     = "S02_ENCRYPT_FF3_INIT_FAILED"
    S02_ENCRYPT_FF3_PAN_FAILED      = "S02_ENCRYPT_FF3_PAN_FAILED"
    S02_ENCRYPT_AES_FAILED          = "S02_ENCRYPT_AES_FAILED"
    S02_ENCRYPT_S3_UPLOAD_FAILED    = "S02_ENCRYPT_S3_UPLOAD_FAILED"
    S02_ENCRYPT_S3_DELETE_FAILED    = "S02_ENCRYPT_S3_DELETE_FAILED"   # non-fatal, logged
    S02_ENCRYPT_OCR_TESSERACT_FAILED = "S02_ENCRYPT_OCR_TESSERACT_FAILED"
    S02_ENCRYPT_OCR_TEXTRACT_FAILED = "S02_ENCRYPT_OCR_TEXTRACT_FAILED"
    S02_ENCRYPT_PAN_NOT_FOUND       = "S02_ENCRYPT_PAN_NOT_FOUND"
    S02_ENCRYPT_MULTIPLE_PANS       = "S02_ENCRYPT_MULTIPLE_PANS"

    # ── Stage 03 — Safety scan ─────────────────────────────────────────────────
    S03_SCAN_CLAMD_UNAVAILABLE      = "S03_SCAN_CLAMD_UNAVAILABLE"
    S03_SCAN_CLAMD_TIMEOUT          = "S03_SCAN_CLAMD_TIMEOUT"
    S03_SCAN_CLAMD_ERROR            = "S03_SCAN_CLAMD_ERROR"
    S03_SCAN_VIRUS_DETECTED         = "S03_SCAN_VIRUS_DETECTED"        # non-retryable
    S03_SCAN_NUDENET_UNAVAILABLE    = "S03_SCAN_NUDENET_UNAVAILABLE"
    S03_SCAN_NUDENET_FAILED         = "S03_SCAN_NUDENET_FAILED"
    S03_SCAN_NSFW_EXPLICIT          = "S03_SCAN_NSFW_EXPLICIT"         # non-retryable
    S03_SCAN_NSFW_SUGGESTIVE        = "S03_SCAN_NSFW_SUGGESTIVE"       # review queue, not terminal
    S03_SCAN_PHOTODNA_UNAVAILABLE   = "S03_SCAN_PHOTODNA_UNAVAILABLE"
    S03_SCAN_PHOTODNA_ERROR         = "S03_SCAN_PHOTODNA_ERROR"
    S03_SCAN_CSAM_DETECTED          = "S03_SCAN_CSAM_DETECTED"         # non-retryable, mandatory report
    S03_SCAN_FORMAT_UNSUPPORTED     = "S03_SCAN_FORMAT_UNSUPPORTED"

    # ── Stage 04 — LLM Extraction ──────────────────────────────────────────────
    S04_EXTRACT_PDF_FAILED          = "S04_EXTRACT_PDF_FAILED"
    S04_EXTRACT_DOCX_FAILED         = "S04_EXTRACT_DOCX_FAILED"
    S04_EXTRACT_XLSX_FAILED         = "S04_EXTRACT_XLSX_FAILED"
    S04_EXTRACT_OCR_TESSERACT_UNAVAILABLE = "S04_EXTRACT_OCR_TESSERACT_UNAVAILABLE"
    S04_EXTRACT_OCR_TESSERACT_TIMEOUT     = "S04_EXTRACT_OCR_TESSERACT_TIMEOUT"
    S04_EXTRACT_OCR_TEXTRACT_UNAVAILABLE  = "S04_EXTRACT_OCR_TEXTRACT_UNAVAILABLE"
    S04_EXTRACT_OCR_TEXTRACT_QUOTA        = "S04_EXTRACT_OCR_TEXTRACT_QUOTA"
    S04_EXTRACT_OCR_BLANK_OUTPUT    = "S04_EXTRACT_OCR_BLANK_OUTPUT"   # non-retryable
    S04_EXTRACT_OCR_LOW_CONFIDENCE  = "S04_EXTRACT_OCR_LOW_CONFIDENCE"
    S04_EXTRACT_PASSWORD_PROTECTED  = "S04_EXTRACT_PASSWORD_PROTECTED" # non-retryable
    S04_EXTRACT_MANIFEST_NOT_FOUND  = "S04_EXTRACT_MANIFEST_NOT_FOUND"
    S04_EXTRACT_MANIFEST_BUILD_FAILED = "S04_EXTRACT_MANIFEST_BUILD_FAILED"
    S04_EXTRACT_LLM_UNAVAILABLE     = "S04_EXTRACT_LLM_UNAVAILABLE"
    S04_EXTRACT_LLM_TIMEOUT         = "S04_EXTRACT_LLM_TIMEOUT"
    S04_EXTRACT_LLM_JSON_INVALID    = "S04_EXTRACT_LLM_JSON_INVALID"
    S04_EXTRACT_LLM_SCHEMA_INVALID  = "S04_EXTRACT_LLM_SCHEMA_INVALID"
    S04_EXTRACT_LOW_CONFIDENCE      = "S04_EXTRACT_LOW_CONFIDENCE"     # routes to exception queue
    S04_EXTRACT_AUTODETECT_FAILED   = "S04_EXTRACT_AUTODETECT_FAILED"  # routes to unclassified queue
    S04_EXTRACT_LANGUAGE_UNSUPPORTED = "S04_EXTRACT_LANGUAGE_UNSUPPORTED"
    S04_EXTRACT_CORRUPTED           = "S04_EXTRACT_CORRUPTED"          # non-retryable
    S04_EXTRACT_DARK_IMAGE          = "S04_EXTRACT_DARK_IMAGE"         # non-retryable

    # ── Stage 05 — Identity Resolution ────────────────────────────────────────
    S05_RESOLVE_CROSS_TENANT        = "S05_RESOLVE_CROSS_TENANT"       # non-retryable, P0 anomaly
    S05_RESOLVE_L1_DB_ERROR         = "S05_RESOLVE_L1_DB_ERROR"
    S05_RESOLVE_L2_DB_ERROR         = "S05_RESOLVE_L2_DB_ERROR"
    S05_RESOLVE_L3_DB_ERROR         = "S05_RESOLVE_L3_DB_ERROR"
    S05_RESOLVE_L3_MULTIPLE_CANDIDATES = "S05_RESOLVE_L3_MULTIPLE_CANDIDATES"
    S05_RESOLVE_L4_EMBEDDING_FAILED = "S05_RESOLVE_L4_EMBEDDING_FAILED"
    S05_RESOLVE_L4_QDRANT_UNAVAILABLE = "S05_RESOLVE_L4_QDRANT_UNAVAILABLE"
    S05_RESOLVE_L4_QDRANT_ERROR     = "S05_RESOLVE_L4_QDRANT_ERROR"
    S05_RESOLVE_L4_MULTIPLE_CANDIDATES = "S05_RESOLVE_L4_MULTIPLE_CANDIDATES"
    S05_RESOLVE_UNRESOLVED          = "S05_RESOLVE_UNRESOLVED"         # routes to exception queue
    S05_RESOLVE_MANIFEST_FETCH_FAILED = "S05_RESOLVE_MANIFEST_FETCH_FAILED"
    S05_RESOLVE_EMBEDDING_GENERATION_FAILED = "S05_RESOLVE_EMBEDDING_GENERATION_FAILED"

    # ── Stage 06 — Route ──────────────────────────────────────────────────────
    S06_ROUTE_DB_TRANSACTION_FAILED = "S06_ROUTE_DB_TRANSACTION_FAILED"
    S06_ROUTE_S3_MOVE_FAILED        = "S06_ROUTE_S3_MOVE_FAILED"
    S06_ROUTE_KAFKA_PUBLISH_FAILED  = "S06_ROUTE_KAFKA_PUBLISH_FAILED" # non-fatal, logged
    S06_ROUTE_SENSITIVE_STRIP_FAILED = "S06_ROUTE_SENSITIVE_STRIP_FAILED"
    S06_ROUTE_BENCHMARK_FAILED      = "S06_ROUTE_BENCHMARK_FAILED"
    S06_ROUTE_EXCEPTION_QUEUE_FAILED = "S06_ROUTE_EXCEPTION_QUEUE_FAILED"
    S06_ROUTE_UNCLASSIFIED_QUEUE_FAILED = "S06_ROUTE_UNCLASSIFIED_QUEUE_FAILED"
    S06_ROUTE_INTERNAL_CALLBACK_FAILED  = "S06_ROUTE_INTERNAL_CALLBACK_FAILED"
    S06_ROUTE_ALREADY_TERMINAL      = "S06_ROUTE_ALREADY_TERMINAL"     # non-retryable
    S06_ROUTE_LEGAL_HOLD_BLOCK      = "S06_ROUTE_LEGAL_HOLD_BLOCK"     # non-retryable
    S06_ROUTE_VAULT_HEALTH_FAILED   = "S06_ROUTE_VAULT_HEALTH_FAILED"
    S06_ROUTE_CAREER_EVENT_UNKNOWN  = "S06_ROUTE_CAREER_EVENT_UNKNOWN"

    # ── Cross-stage / Infrastructure ──────────────────────────────────────────
    INFRA_DB_UNAVAILABLE            = "INFRA_DB_UNAVAILABLE"
    INFRA_REDIS_UNAVAILABLE         = "INFRA_REDIS_UNAVAILABLE"
    INFRA_KAFKA_UNAVAILABLE         = "INFRA_KAFKA_UNAVAILABLE"
    INFRA_S3_UNAVAILABLE            = "INFRA_S3_UNAVAILABLE"
    INFRA_KMS_UNAVAILABLE           = "INFRA_KMS_UNAVAILABLE"
    INFRA_LLM_URL_MISSING           = "INFRA_LLM_URL_MISSING"
    INFRA_QDRANT_UNAVAILABLE        = "INFRA_QDRANT_UNAVAILABLE"
    INFRA_CONFIG_MISSING            = "INFRA_CONFIG_MISSING"
    INFRA_CONFIG_INVALID            = "INFRA_CONFIG_INVALID"
    INFRA_WORKER_HEARTBEAT_FAILED   = "INFRA_WORKER_HEARTBEAT_FAILED"
    INFRA_INTERNAL_HTTP_FAILED      = "INFRA_INTERNAL_HTTP_FAILED"


class PipelineException(Exception):
    """
    Structured pipeline error.

    Temporal integration contract:
      - If retryable=True  → prana-api lets Temporal retry normally
      - If retryable=False → prana-api raises ApplicationError(non_retryable=True);
                             Temporal fails the workflow immediately

    HTTP contract (prana-ai → prana-api):
      422 Unprocessable Entity
      Body: PipelineException.to_http_dict()
    """

    def __init__(
        self,
        code: PipelineError,
        stage: str,
        message: str,
        retryable: bool | None = None,
    ) -> None:
        self.code = code
        self.stage = stage
        self.message = message
        # Auto-derive retryable from the non-retryable set unless caller overrides
        self.retryable: bool = (
            retryable
            if retryable is not None
            else code.value not in _NON_RETRYABLE
        )
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"[{self.stage}] {self.code.value}: {self.message}"

    def to_http_dict(self) -> dict:
        """Serialise to the shape prana-api/services/ai_client.py expects."""
        return {
            "error":     self.code.value,
            "stage":     self.stage,
            "message":   self.message,
            "retryable": self.retryable,
        }
