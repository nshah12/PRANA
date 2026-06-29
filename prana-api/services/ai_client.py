"""
HTTP client for prana-ai pipeline stages.
Called by Temporal activity functions in prana-api/workflows/.
Uses the shared secret in X-Prana-AI-Secret header (internal VPC traffic only).

Error contract:
  prana-ai returns HTTP 422 for structured pipeline errors with body:
    {"error": "S04_EXTRACT_PASSWORD_PROTECTED", "stage": "stage04",
     "message": "...", "retryable": false}

  _check_response() interprets the retryable flag:
    retryable=false → ApplicationError(non_retryable=True)
                      Temporal fails the workflow immediately, no more retries.
    retryable=true  → PipelineRetryableError (a plain exception)
                      Temporal retries the activity per its RetryPolicy.
    other 4xx/5xx   → httpx.HTTPStatusError (Temporal retries as a generic failure)
"""

import base64
import logging
from typing import Optional

import httpx
from temporalio.exceptions import ApplicationError

from config import get_settings

log = logging.getLogger(__name__)


class PipelineRetryableError(Exception):
    """
    Raised when prana-ai returns 422 with retryable=true.
    Temporal treats this as a retryable activity failure.
    Carries the error code and stage for logging in the Temporal event history.
    """
    def __init__(self, code: str, stage: str, message: str) -> None:
        self.code = code
        self.stage = stage
        super().__init__(f"[{stage}] {code}: {message}")


class AiPipelineClient:
    """Thin async HTTP client over the prana-ai FastAPI service."""

    def __init__(self):
        s = get_settings()
        self._base = s.ai_service_url.rstrip("/")
        self._secret = s.ai_service_secret
        self._timeout = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=5.0)

    def _headers(self) -> dict:
        return {"X-Prana-AI-Secret": self._secret, "Content-Type": "application/json"}

    def _check_response(self, resp: httpx.Response) -> None:
        """
        Inspect the response and raise the appropriate exception type.

        422 from prana-ai = structured PipelineException:
          retryable=false → ApplicationError(non_retryable=True)
                            Temporal does NOT retry; workflow fails immediately.
          retryable=true  → PipelineRetryableError
                            Temporal retries the activity per RetryPolicy.

        Any other non-2xx → httpx.HTTPStatusError (Temporal retries as transient failure).
        2xx → no-op.
        """
        if resp.status_code == 422:
            try:
                body = resp.json()
            except Exception:
                resp.raise_for_status()
                return

            code = body.get("error", "UNKNOWN_PIPELINE_ERROR")
            stage = body.get("stage", "unknown")
            message = body.get("message", "")
            retryable = body.get("retryable", True)

            log.error(
                "prana-ai pipeline error stage=%s code=%s retryable=%s: %s",
                stage, code, retryable, message,
            )

            if not retryable:
                raise ApplicationError(
                    f"[{stage}] {code}: {message}",
                    non_retryable=True,
                )
            else:
                raise PipelineRetryableError(code=code, stage=stage, message=message)

        if not resp.is_success:
            resp.raise_for_status()

    async def scan(self, file_bytes: bytes, ext: str) -> dict:
        """Stage 03 — virus + NSFW scan."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base}/pipeline/scan",
                headers=self._headers(),
                json={
                    "file_b64": base64.b64encode(file_bytes).decode(),
                    "ext": ext,
                },
            )
            self._check_response(resp)
            return resp.json()

    async def extract(
        self,
        file_bytes: bytes,
        ext: str,
        doc_type: str,
        tenant_id: str,
        doc_period: Optional[str] = None,
    ) -> dict:
        """Stage 04 — OCR + LLM extraction. Slowest call (~30–120s).
        Returns dict with status='ok' or status='unclassified'."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base}/pipeline/extract",
                headers=self._headers(),
                json={
                    "file_b64": base64.b64encode(file_bytes).decode(),
                    "ext": ext,
                    "doc_type": doc_type,
                    "tenant_id": tenant_id,
                    "doc_period": doc_period,
                },
            )
            self._check_response(resp)
            return resp.json()

    async def write_unclassified(
        self,
        document_id: str,
        tenant_id: str,
        declared_doc_type: Optional[str],
        best_guess_doc_type: Optional[str],
        best_guess_score: float,
        partial_fields: dict,
        reason: str = "AUTO_DETECT_FAILED",
    ) -> None:
        """Stage 06 path — doc type could not be determined → unclassified_queue."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base}/pipeline/unclassified",
                headers=self._headers(),
                json={
                    "document_id": document_id,
                    "tenant_id": tenant_id,
                    "declared_doc_type": declared_doc_type,
                    "best_guess_doc_type": best_guess_doc_type,
                    "best_guess_score": best_guess_score,
                    "partial_fields": partial_fields,
                    "reason": reason,
                },
            )
            self._check_response(resp)

    async def resolve(
        self,
        pan_token: Optional[str],
        tenant_id: str,
        doc_type: str,
        extracted_fields: dict,
    ) -> dict:
        """Stage 05 — identity resolution (pan_token → employee_uuid)."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base}/pipeline/resolve",
                headers=self._headers(),
                json={
                    "pan_token": pan_token,
                    "tenant_id": tenant_id,
                    "doc_type": doc_type,
                    "extracted_fields": extracted_fields,
                },
            )
            self._check_response(resp)
            return resp.json()

    async def route(
        self,
        document_id: str,
        tenant_id: str,
        employee_uuid: str,
        pan_token: str,
        doc_type: str,
        doc_period: Optional[str],
        extracted_fields: dict,
        resolution_method: str,
        resolution_confidence: float,
        s3_key: str,
    ) -> None:
        """Stage 06 — write ROUTED status + career_event to DB."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base}/pipeline/route",
                headers=self._headers(),
                json={
                    "document_id": document_id,
                    "tenant_id": tenant_id,
                    "employee_uuid": employee_uuid,
                    "pan_token": pan_token,
                    "doc_type": doc_type,
                    "doc_period": doc_period,
                    "extracted_fields": extracted_fields,
                    "resolution_method": resolution_method,
                    "resolution_confidence": resolution_confidence,
                    "s3_key": s3_key,
                },
            )
            self._check_response(resp)

    async def raise_exception(
        self,
        document_id: str,
        tenant_id: str,
        exception_type: str,
        extracted_fields: dict,
        candidates: list,
    ) -> None:
        """Stage 06 — write EXCEPTION status + exception_queue row."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base}/pipeline/exception",
                headers=self._headers(),
                json={
                    "document_id": document_id,
                    "tenant_id": tenant_id,
                    "exception_type": exception_type,
                    "extracted_fields": extracted_fields,
                    "candidates": candidates,
                },
            )
            self._check_response(resp)

    async def refresh_insight(
        self,
        document_id: str,
        employee_uuid: str,
        doc_type: str,
        doc_period: Optional[str],
        benchmarks: dict,
    ) -> None:
        """InsightRefreshWorkflow — generate LLM insight and upsert into Qdrant."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base}/pipeline/refresh-insight",
                headers=self._headers(),
                json={
                    "document_id": document_id,
                    "employee_uuid": employee_uuid,
                    "doc_type": doc_type,
                    "doc_period": doc_period,
                    "benchmarks": benchmarks,
                },
            )
            self._check_response(resp)
