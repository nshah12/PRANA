"""
CareerInsightService — generates per-document insight text and upserts into Qdrant.

Privacy contract:
  - Input is benchmarked data only (percentiles, qualitative labels) — never raw ₹
  - LLM receives growth index and peer percentile bands, not salary figures
  - Output (insight_text) is stored in document.insight_text — also no raw amounts
"""
from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID

import asyncpg
import httpx

from llm_client import LLMClient, EmbeddingClient, QdrantClient

log = logging.getLogger(__name__)

_INSIGHT_SYSTEM = """You are a career intelligence assistant for PRANA.
Generate a concise, encouraging 2–3 sentence career insight from the provided benchmarked data.
RULES:
- Never mention specific salary amounts (₹, LPA, CTC, etc.)
- Use growth indices, percentile bands, and qualitative labels only
- Be factual, positive, and actionable
- Write in second person ("Your salary growth…")
- Output plain text only — no JSON, no markdown
"""


class CareerInsightService:

    def __init__(
        self,
        db: asyncpg.Connection,
        llm_client: LLMClient,
        embedding_client: EmbeddingClient,
        qdrant_client: QdrantClient,
    ):
        self._db = db
        self._llm = llm_client
        self._embed = embedding_client
        self._qdrant = qdrant_client

    async def refresh_for_document(
        self,
        document_id: str,
        employee_uuid: str,
        doc_type: str,
        doc_period: Optional[str],
        benchmarks: dict,
    ) -> None:
        """
        Generate insight text for one document and upsert into Qdrant.
        Called by InsightRefreshWorkflow after stage06 ROUTED.
        """
        insight_text = await self._generate_insight(doc_type, doc_period, benchmarks)

        # Store in document row (no raw figures — insight only)
        await self._db.execute(
            "UPDATE document SET insight_text=$2 WHERE document_id=$1",
            document_id, insight_text,
        )

        # Embed and upsert into Qdrant employee collection
        await self._upsert_vector(document_id, employee_uuid, doc_type, doc_period, insight_text, benchmarks)

    async def _generate_insight(
        self,
        doc_type: str,
        doc_period: Optional[str],
        benchmarks: dict,
    ) -> str:
        period_str = f" for period {doc_period}" if doc_period else ""
        user_msg = (
            f"Document type: {doc_type}{period_str}\n"
            f"Benchmarked career data: {json.dumps(benchmarks, ensure_ascii=False)}\n\n"
            "Generate a brief career insight from this data."
        )
        try:
            return await self._llm.complete(
                system=_INSIGHT_SYSTEM,
                user=user_msg,
                max_tokens=200,
                temperature=0.3,
            )
        except Exception as exc:
            log.warning("LLM insight generation failed: %s", exc)
            # Fallback: structured non-LLM text
            return _fallback_insight(doc_type, benchmarks)

    async def _upsert_vector(
        self,
        document_id: str,
        employee_uuid: str,
        doc_type: str,
        doc_period: Optional[str],
        insight_text: str,
        benchmarks: dict,
    ) -> None:
        collection = f"employee_{employee_uuid.replace('-', '')}"
        embed_text = f"{doc_type} {doc_period or ''}: {insight_text}"
        try:
            vector = await self._embed.embed(embed_text)
            await self._qdrant.upsert(
                collection=collection,
                point_id=document_id,
                vector=vector,
                payload={
                    "document_id": document_id,
                    "doc_type": doc_type,
                    "doc_period": doc_period,
                    "insight_text": insight_text,
                    "benchmarks": benchmarks,
                },
            )
        except Exception as exc:
            log.warning("Qdrant upsert failed for %s: %s", document_id, exc)


def _fallback_insight(doc_type: str, benchmarks: dict) -> str:
    pct = benchmarks.get("salary_percentile_band", "")
    growth = benchmarks.get("growth_index")
    parts = [f"Document type: {doc_type}."]
    if growth:
        parts.append(f"Your salary growth index stands at {growth}.")
    if pct:
        parts.append(f"Your compensation is in the {pct} band among peers.")
    return " ".join(parts)
