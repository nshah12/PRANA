"""
prana-ask FastAPI server — Ask PRANA employee chatbot.

Single endpoint:
  POST /ask  { query: str }   → { answer: str }

Authentication: X-Prana-Ask-Secret header (internal; called by prana-api only after JWT validation).
employee_user_id is taken from the X-Employee-ID header (set by prana-api from JWT claims —
never accepted from the request body).

Rate limit: 20 queries / employee / hour (enforced by prana-api before proxying here).
"""

import asyncpg
import redis.asyncio as redis
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import get_settings
from llm_client import LLMClient, EmbeddingClient, QdrantClient
from ask_service import AskService
from context_builder import ContextBuilder
from conversation_store import ConversationStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()

    app.state.llm_client = LLMClient(
        base_url=s.llm_base_url,
        model=s.ask_llm_model,
        api_key=s.llm_api_key or None,
        timeout=s.llm_timeout,
    )
    app.state.embedding_client = EmbeddingClient(
        base_url=s.embedding_base_url,
        model=s.embedding_model,
        api_key=s.embedding_api_key or None,
    )
    app.state.qdrant_client = QdrantClient(
        url=s.qdrant_url,
        api_key=s.qdrant_api_key or None,
    )

    try:
        app.state.db_pool = await asyncpg.create_pool(s.db_dsn, min_size=2, max_size=8)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("DB unavailable at startup (%s) — /ask will return empty context", e)
        app.state.db_pool = None

    app.state.redis = redis.from_url(s.redis_url, decode_responses=True)
    app.state.conversation_store = ConversationStore(app.state.redis)

    yield

    if app.state.db_pool:
        await app.state.db_pool.close()
    await app.state.redis.aclose()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="PRANA Ask",
        version="0.1.0",
        docs_url="/docs" if s.debug else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"error": "INTERNAL_ERROR"})

    @app.get("/health", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    # ── Auth guard ────────────────────────────────────────────────────────────

    async def require_internal(request: Request):
        token = request.headers.get("X-Prana-Ask-Secret")
        if token != get_settings().api_secret:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="UNAUTHORIZED")

    # ── Ask endpoint ──────────────────────────────────────────────────────────

    class AskRequest(BaseModel):
        query: str
        session_id: str | None = None   # omit for stateless; include for multi-turn

    class AskResponse(BaseModel):
        answer: str
        session_id: str | None = None

    @app.post("/ask", response_model=AskResponse, dependencies=[Depends(require_internal)])
    async def ask(body: AskRequest, request: Request):
        # employee_user_id set by prana-api from JWT claims — never from request body
        employee_id_header = request.headers.get("X-Employee-ID")
        if not employee_id_header:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MISSING_EMPLOYEE_ID")
        try:
            employee_user_id = UUID(employee_id_header)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_EMPLOYEE_ID")

        query = (body.query or "").strip()
        if not query:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="EMPTY_QUERY")
        if len(query) > 1000:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="QUERY_TOO_LONG")

        db = request.app.state.db_pool
        ctx_builder = ContextBuilder(
            db=db,
            embedding_client=request.app.state.embedding_client,
            qdrant_client=request.app.state.qdrant_client,
        )
        svc = AskService(llm=request.app.state.llm_client, context_builder=ctx_builder)
        conv_store: ConversationStore = request.app.state.conversation_store

        # Load prior history when session_id is provided
        session_id = body.session_id
        history = None
        if session_id:
            history = await conv_store.get_history(employee_user_id, session_id)

        answer = await svc.answer(
            employee_user_id=employee_user_id,
            query=query,
            history=history if history else None,
        )

        # Persist turn — only post-processed (safe) response is stored
        if session_id:
            await conv_store.append(employee_user_id, session_id, query, answer)

        return AskResponse(answer=answer, session_id=session_id)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    s = get_settings()
    uvicorn.run("main:app", host=s.host, port=s.port, reload=s.debug)
