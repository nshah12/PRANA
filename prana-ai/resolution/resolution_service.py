"""
ResolutionService — Stage 05 of the DocumentPipelineWorkflow.

4-level identity resolution ladder. Stop at first successful level.
No LLM — pure algorithmic matching.

Level 1: pan_token exact match          (O(1) indexed lookup)
Level 2: employee_id exact match        (only if document has emp_id field)
Level 3: fuzzy name + DOJ match         (rapidfuzz token_sort_ratio >= 88)
Level 4: embedding cosine similarity    (BAAI/bge-m3, threshold >= 0.92)

Unresolved → write to exception_queue, wait up to 7 days for OA-Admin signal.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from llm_client import QdrantClient

log = logging.getLogger(__name__)


class ResolutionMethod(str, Enum):
    EXACT_PAN   = "EXACT_PAN"
    EMP_ID      = "EMP_ID"
    FUZZY_NAME  = "FUZZY_NAME"
    EMBEDDING   = "EMBEDDING"
    UNRESOLVED  = "UNRESOLVED"


@dataclass
class ResolutionResult:
    employee_uuid: UUID | None
    method: ResolutionMethod
    confidence: float        # 1.0 for exact, fuzzy score / cosine for approximate
    candidates: list[dict]   # top-3 embedding candidates stored for audit even when resolved


class ResolutionService:
    """
    Orchestrates the 4-level identity resolution ladder.

    Dependencies injected via constructor — no global state.
    """

    def __init__(self, db, embedding_client, fuzzy_service, qdrant_client: "QdrantClient | None" = None):
        self._db = db
        self._emb = embedding_client
        self._fuzzy = fuzzy_service
        self._qdrant = qdrant_client

    async def resolve(
        self,
        tenant_id: UUID,
        pan_token: str | None,
        extracted_fields: dict,
    ) -> ResolutionResult:
        """
        Attempt to resolve extracted document fields to an employee_master row.

        pan_token: HMAC-SHA256(PAN, platform_secret) — computed in Stage 02.
        extracted_fields: validated output from ExtractionService.
        """

        # Level 1 — pan_token exact match
        if pan_token:
            result = await self._match_pan_token(tenant_id, pan_token)
            if result:
                return ResolutionResult(result, ResolutionMethod.EXACT_PAN, 1.0, [])

        # Level 2 — employee_id exact match
        emp_id = _field_value(extracted_fields, "employee_id")
        if emp_id:
            result = await self._match_employee_id(tenant_id, emp_id)
            if result:
                return ResolutionResult(result, ResolutionMethod.EMP_ID, 1.0, [])

        # Level 3 — fuzzy name + DOJ
        name = _field_value(extracted_fields, "employee_name")
        doj  = _field_value(extracted_fields, "date_of_joining")
        if name:
            result, score = await self._fuzzy.match(tenant_id, name, doj)
            if result:
                return ResolutionResult(result, ResolutionMethod.FUZZY_NAME, score / 100, [])

        # Level 4 — embedding cosine similarity
        candidates = await self._match_embedding(tenant_id, extracted_fields)
        if candidates and candidates[0]["score"] >= 0.92:
            return ResolutionResult(
                candidates[0]["employee_uuid"],
                ResolutionMethod.EMBEDDING,
                candidates[0]["score"],
                candidates,
            )

        # Unresolved
        log.warning("identity resolution failed", extra={"tenant_id": str(tenant_id), "name": name})
        return ResolutionResult(None, ResolutionMethod.UNRESOLVED, 0.0, candidates or [])

    async def _match_pan_token(self, tenant_id: UUID, pan_token: str) -> UUID | None:
        row = await self._db.fetchrow(
            """SELECT em.employee_uuid
               FROM employee_master em
               JOIN employee_user eu ON eu.employee_user_id = em.employee_user_id
               WHERE eu.pan_token = $1 AND em.tenant_id = $2 AND em.dol IS NULL""",
            pan_token, tenant_id,
        )
        return row["employee_uuid"] if row else None

    async def _match_employee_id(self, tenant_id: UUID, employee_id: str) -> UUID | None:
        row = await self._db.fetchrow(
            "SELECT employee_uuid FROM employee_master WHERE employee_id=$1 AND tenant_id=$2",
            employee_id, tenant_id,
        )
        return row["employee_uuid"] if row else None

    async def _match_embedding(self, tenant_id: UUID, extracted_fields: dict) -> list[dict]:
        name        = _field_value(extracted_fields, "employee_name") or ""
        designation = _field_value(extracted_fields, "designation") or ""
        department  = _field_value(extracted_fields, "department") or ""
        query_text  = f"{name} {designation} {department}".strip()

        if not query_text:
            return []

        vector = await self._emb.embed(query_text)
        # Qdrant search — returns top-3 results above 0.85 (wider net, threshold applied above)
        return await self._search_vector_store(tenant_id, vector, limit=3, score_threshold=0.85)

    async def _search_vector_store(
        self, tenant_id: UUID, vector: list[float], limit: int, score_threshold: float
    ) -> list[dict]:
        if not self._qdrant:
            log.warning("Qdrant not configured — Level 4 resolution unavailable")
            return []

        collection = f"tenant_{str(tenant_id).replace('-', '')}"
        hits = await self._qdrant.search(
            collection=collection,
            vector=vector,
            limit=limit,
            filter_={"must": [{"key": "score_threshold", "range": {"gte": score_threshold}}]},
        )
        return [
            {
                "employee_uuid": h["payload"].get("employee_uuid"),
                "score": h["score"],
                "display_name": h["payload"].get("display_name", ""),
            }
            for h in hits
            if h["score"] >= score_threshold
        ]


def _field_value(extracted_fields: dict, key: str) -> str | None:
    field = extracted_fields.get(key, {})
    if isinstance(field, dict):
        return field.get("value")
    return None
