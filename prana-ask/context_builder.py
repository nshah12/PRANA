"""
ContextBuilder — assembles RAG context for an Ask PRANA query.

Retrieves career data scoped strictly to the querying employee.
Returns a privacy-safe context string — no raw ₹, no PAN, benchmarks only.
"""

import logging
from uuid import UUID

log = logging.getLogger(__name__)

# Max tokens to include in context (Llama 3.1 8B context window is large,
# but we cap at 6000 to control cost and keep responses focused)
MAX_CONTEXT_TOKENS = 6000

# Qdrant collection name pattern (one collection per employee)
_COLLECTION = "employee_{employee_user_id}"

# Minimum cosine similarity for a doc to be included as relevant
_SIMILARITY_THRESHOLD = 0.30

# Top-K results from Qdrant per query
_TOP_K = 5


class ContextBuilder:
    def __init__(self, db, embedding_client, qdrant_client=None):
        self._db = db
        self._emb = embedding_client
        self._qdrant = qdrant_client

    async def build(self, employee_user_id: UUID, query: str) -> str:
        """
        Build a privacy-safe context string for the RAG query.

        Retrieves:
        1. Career timeline (employer name from tenant table, role, date ranges)
        2. Pre-generated career insights (cached, no LLM re-call needed)
        3. Vault completeness summary (what docs are available)
        4. Relevant document summaries via embedding similarity (Qdrant)

        Returns: plain-text context safe to pass to LLM (no raw ₹, no PAN).
        """
        sections: list[str] = []

        # 1. Career timeline
        timeline = await self._career_timeline(employee_user_id)
        if timeline:
            sections.append("## Career Timeline\n" + timeline)

        # 2. Pre-generated insights (benchmark percentiles, growth trends)
        insights = await self._cached_insights(employee_user_id)
        if insights:
            sections.append("## Career Insights\n" + insights)

        # 3. Vault summary (doc types available, date ranges)
        vault = await self._vault_summary(employee_user_id)
        if vault:
            sections.append("## Available Documents\n" + vault)

        # 4. Relevant documents for this specific query (embedding similarity)
        relevant = await self._relevant_docs(employee_user_id, query)
        if relevant:
            sections.append("## Relevant Document Extracts\n" + relevant)

        return "\n\n".join(sections) or "No career data available yet."

    async def _career_timeline(self, employee_user_id: UUID) -> str:
        if not self._db:
            return ""
        try:
            rows = await self._db.fetch(
                """SELECT t.tenant_name AS employer_name,
                          em.designation, em.department, em.doj, em.dol, em.location
                   FROM employee_master em
                   JOIN tenant t ON t.tenant_id = em.tenant_id
                   WHERE em.employee_user_id = $1
                   ORDER BY em.doj ASC""",
                employee_user_id,
            )
        except Exception as e:
            log.warning("career_timeline query failed: %s", e)
            return ""

        if not rows:
            return ""

        lines = []
        for row in rows:
            end = str(row["dol"]) if row["dol"] else "Present"
            dept = f", {row['department']}" if row["department"] else ""
            loc = f", {row['location']}" if row["location"] else ""
            lines.append(
                f"- {row['employer_name']}: {row['designation']}{dept} "
                f"({row['doj']} → {end}){loc}"
            )
        return "\n".join(lines)

    async def _cached_insights(self, employee_user_id: UUID) -> str:
        if not self._db:
            return ""
        try:
            rows = await self._db.fetch(
                """SELECT event_type, insight_text, event_date
                   FROM career_event
                   WHERE employee_user_id = $1
                     AND insight_text IS NOT NULL
                   ORDER BY event_date DESC
                   LIMIT 20""",
                employee_user_id,
            )
        except Exception as e:
            log.warning("cached_insights query failed: %s", e)
            return ""

        if not rows:
            return ""
        return "\n".join(
            f"- [{row['event_date']}] {row['event_type']}: {row['insight_text']}"
            for row in rows
        )

    async def _vault_summary(self, employee_user_id: UUID) -> str:
        if not self._db:
            return ""
        try:
            rows = await self._db.fetch(
                """SELECT d.doc_type,
                          COUNT(*) AS count,
                          MIN(d.doc_period) AS earliest,
                          MAX(d.doc_period) AS latest
                   FROM document d
                   JOIN employee_master em ON em.employee_uuid = d.employee_uuid
                   WHERE em.employee_user_id = $1
                     AND d.pipeline_status = 'ROUTED'
                     AND d.is_deleted = FALSE
                   GROUP BY d.doc_type
                   ORDER BY d.doc_type""",
                employee_user_id,
            )
        except Exception as e:
            log.warning("vault_summary query failed: %s", e)
            return ""

        if not rows:
            return ""
        return "\n".join(
            f"- {row['doc_type']}: {row['count']} document(s), {row['earliest']} to {row['latest']}"
            for row in rows
        )

    async def _relevant_docs(self, employee_user_id: UUID, query: str) -> str:
        """
        Embed the query and search the per-employee Qdrant collection for similar
        career_event insight_text vectors.

        Collection: employee_{employee_user_id}
        Each point payload: { insight_text, doc_type, event_date }

        Returns "" gracefully if Qdrant is unavailable or the collection is empty.
        """
        if not self._qdrant:
            return ""

        try:
            query_vector = await self._emb.embed(query)
        except Exception as e:
            log.warning("embedding query failed, skipping vector search: %s", e)
            return ""

        collection = f"employee_{employee_user_id}"
        try:
            results = await self._qdrant.search(
                collection=collection,
                query_vector=query_vector,
                top_k=_TOP_K,
                score_threshold=_SIMILARITY_THRESHOLD,
            )
        except Exception as e:
            log.warning("qdrant search failed for %s: %s", collection, e)
            return ""

        if not results:
            return ""

        lines = []
        for payload in results:
            date = payload.get("event_date", "")
            doc_type = payload.get("doc_type", "")
            text = payload.get("insight_text", "")
            lines.append(f"- [{date}] {doc_type}: {text}")

        return "\n".join(lines)
