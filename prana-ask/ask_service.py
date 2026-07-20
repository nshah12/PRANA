"""
AskService — Ask PRANA employee-facing RAG agent.

Scope boundary: employee_user_id from JWT is the hard limit.
The agent ONLY accesses data belonging to the querying employee — never cross it.

Post-process guard: every LLM response is scanned for ₹ amounts and PAN patterns
before being returned. If found → refuse + log. Never return raw financial data.
"""

import re
import logging
from uuid import UUID

from llm_client import LLMClient
from context_builder import ContextBuilder

log = logging.getLogger(__name__)

# Hard blocks — if LLM response matches these, refuse and log
_BLOCK_PATTERNS = [
    re.compile(r"₹\s*[\d,]+"),             # raw rupee amounts
    re.compile(r"Rs\.?\s*[\d,]+"),          # Rs. amounts
    re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),  # PAN pattern
]

SYSTEM = """You are Ask PRANA, an AI career advisor for the employee whose data you have been given.
Answer questions about their career, documents, and professional history.

Rules you MUST follow:
- NEVER reveal raw salary amounts, CTC figures, PAN numbers, or exact financial figures
- Express compensation only as trends, percentile rankings, or qualitative labels (e.g. "above market", "grew 12% year-on-year")
- Answer ONLY from the provided context — do not invent or guess missing data
- If the information is not in the context, say clearly: "I don't have that information in your vault yet"
- Keep responses concise and conversational — this is a mobile chat interface"""


class AskService:
    def __init__(self, llm: LLMClient, context_builder: ContextBuilder):
        self._llm = llm
        self._ctx = context_builder

    async def answer(
        self,
        employee_user_id: UUID,
        query: str,
        history: list[dict] | None = None,
    ) -> str:
        """
        Answer an employee's natural language question about their career data.

        employee_user_id: from JWT — hard scope boundary, never override from request body.
        history: prior turns from ConversationStore; None means stateless call.
        """
        context = await self._ctx.build(employee_user_id, query)

        # Inject context only into the first user turn so it isn't duplicated
        first_user_content = f"""Employee's career context:
{context}

Employee's question: {query}"""

        if history:
            # Replay prior turns then append current query with fresh RAG context injected
            messages = list(history) + [{"role": "user", "content": first_user_content}]
            user_prompt = first_user_content
        else:
            messages = None
            user_prompt = first_user_content

        response = await self._llm.complete(
            system=SYSTEM,
            user=user_prompt,
            messages=messages,
            temperature=0.3,  # slight creativity for natural language, not 0.0
            max_tokens=512,
        )

        # Post-process guard — block if response leaks financial data
        for pattern in _BLOCK_PATTERNS:
            if pattern.search(response):
                log.error(
                    "ask_prana response blocked: contains sensitive pattern",
                    extra={"employee_user_id": str(employee_user_id), "pattern": pattern.pattern},
                )
                return "I'm unable to answer that question right now. Please contact support if this continues."

        return response
