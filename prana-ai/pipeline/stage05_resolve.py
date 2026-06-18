"""
Stage 05 — Identity Resolution
Runs the 4-level resolution ladder. Returns employee_uuid or raises for exception queue.
No LLM — pure algorithmic matching.
"""
from dataclasses import dataclass
from typing import Optional

import asyncpg

from resolution.resolution_service import ResolutionService, ResolutionMethod
from resolution.fuzzy_service import FuzzyService
from llm_client import EmbeddingClient, QdrantClient


@dataclass
class Stage05Result:
    employee_uuid: Optional[str]
    method: str
    confidence: float
    needs_exception: bool
    exception_type: Optional[str]   # NO_MATCH | MULTIPLE_CANDIDATES | LOW_CONFIDENCE
    candidates: list                # top-3 for exception queue context


class Stage05Resolve:

    def __init__(
        self,
        db: asyncpg.Connection,
        embedding_client: EmbeddingClient,
        qdrant_client: QdrantClient | None = None,
    ):
        fuzzy = FuzzyService(db)
        self._svc = ResolutionService(db, embedding_client, fuzzy, qdrant_client)

    async def run(
        self,
        pan_token: str,
        tenant_id: str,
        extracted_fields: dict,
    ) -> Stage05Result:
        result = await self._svc.resolve(
            tenant_id=tenant_id,
            pan_token=pan_token,
            extracted_fields=extracted_fields,
        )

        if result.method == ResolutionMethod.UNRESOLVED:
            return Stage05Result(
                employee_uuid=None,
                method=result.method.value,
                confidence=0.0,
                needs_exception=True,
                exception_type="NO_MATCH",
                candidates=result.candidates,
            )

        if len(result.candidates) > 1 and result.confidence < 0.88:
            return Stage05Result(
                employee_uuid=None,
                method=result.method.value,
                confidence=result.confidence,
                needs_exception=True,
                exception_type="MULTIPLE_CANDIDATES",
                candidates=result.candidates,
            )

        return Stage05Result(
            employee_uuid=result.employee_uuid,
            method=result.method.value,
            confidence=result.confidence,
            needs_exception=False,
            exception_type=None,
            candidates=result.candidates,
        )


