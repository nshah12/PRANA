"""
prana-ai FastAPI server — GPU worker exposing pipeline stage endpoints.

Endpoints called by Temporal activities in prana-api:
  POST /pipeline/scan     — Stage 03: virus + NSFW scan
  POST /pipeline/extract  — Stage 04: OCR + LLM extraction
  POST /pipeline/resolve  — Stage 05: identity resolution
  POST /pipeline/route    — Stage 06: DB write + career event (needs DB)
  GET  /health            — liveness probe

Authentication: shared secret in X-Prana-AI-Secret header (internal traffic only,
not exposed outside the VPC — no mTLS needed on the internal load balancer path).
"""

import asyncpg
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from config import get_settings
from llm_client import LLMClient, EmbeddingClient, QdrantClient
from pipeline.stage03_scan import Stage03Scan
from pipeline.stage04_extract import Stage04Extract
from pipeline.stage05_resolve import Stage05Resolve
from pipeline.stage06_route import Stage06Route
from insights.benchmark_service import BenchmarkService


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()

    # Shared LLM clients — one httpx session per worker process
    app.state.llm_client = LLMClient(
        base_url=s.llm_base_url,
        model=s.extraction_llm_model,
        api_key=s.llm_api_key or None,
        timeout=s.llm_timeout,
    )
    app.state.embedding_client = EmbeddingClient(
        base_url=s.embedding_base_url,
        model=s.embedding_model,
        api_key=s.embedding_api_key or None,
    )

    # Stage instances (stateless except for shared clients)
    app.state.qdrant_client = QdrantClient(
        base_url=s.qdrant_url,
        api_key=s.qdrant_api_key or None,
    )

    app.state.stage03 = Stage03Scan(clamd_socket=s.clamd_socket)
    app.state.stage04 = Stage04Extract(
        llm_client=app.state.llm_client,
        aws_region=s.aws_region,
    )

    # DB pool for resolution + routing stages — optional at startup (not needed for scan/extract)
    try:
        app.state.db_pool = await asyncpg.create_pool(s.db_dsn, min_size=2, max_size=8)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("DB unavailable at startup (%s) — resolve/route endpoints will fail", e)
        app.state.db_pool = None

    yield

    if app.state.db_pool:
        await app.state.db_pool.close()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="PRANA AI",
        version="0.1.0",
        docs_url="/docs" if s.debug else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # ── Auth guard — internal shared secret ───────────────────────────────────

    async def require_internal(request: Request):
        token = request.headers.get("X-Prana-AI-Secret")
        if token != get_settings().api_secret:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="UNAUTHORIZED")

    Internal = Depends(require_internal)

    # ── Unhandled exceptions — never leak stack traces ────────────────────────

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_ERROR", "detail": str(exc)},
        )

    # ── Health ────────────────────────────────────────────────────────────────

    @app.get("/health", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    # ── Pipeline routes ───────────────────────────────────────────────────────

    from routers import pipeline
    app.include_router(pipeline.router, prefix="/pipeline", dependencies=[Internal])

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    s = get_settings()
    uvicorn.run("main:app", host=s.host, port=s.port, reload=s.debug)
