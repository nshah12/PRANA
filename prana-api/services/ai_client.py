"""
HTTP client for prana-ai pipeline stages.
Called by Temporal activity functions in prana-api/workflows/.
Uses the shared secret in X-Prana-AI-Secret header (internal VPC traffic only).
"""

import base64
from typing import Optional

import httpx

from config import get_settings


class AiPipelineClient:
    """Thin async HTTP client over the prana-ai FastAPI service."""

    def __init__(self):
        s = get_settings()
        self._base = s.ai_service_url.rstrip("/")
        self._secret = s.ai_service_secret
        self._timeout = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=5.0)

    def _headers(self) -> dict:
        return {"X-Prana-AI-Secret": self._secret, "Content-Type": "application/json"}

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
            resp.raise_for_status()
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
            resp.raise_for_status()
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
            resp.raise_for_status()

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
            resp.raise_for_status()
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
            resp.raise_for_status()

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
            resp.raise_for_status()

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
            resp.raise_for_status()
