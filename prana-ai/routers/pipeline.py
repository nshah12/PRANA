"""
Pipeline stage endpoints — called by Temporal activities in prana-api.

All endpoints accept base64-encoded file bytes where raw binary is needed,
or plain JSON for metadata-only stages.

Stage 03 (scan)    — sync, no LLM
Stage 04 (extract) — async, LLM call, slowest (~30–90s for 14B model)
Stage 05 (resolve) — async, embedding + DB queries
Stage 06 (route)   — async, DB writes, must run after 05 succeeds
"""

import base64
import json
from typing import Optional

import asyncpg
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from pipeline.stage03_scan import Stage03Scan, ScanOutcome
from pipeline.stage04_extract import Stage04Extract
from pipeline.stage05_resolve import Stage05Resolve
from pipeline.stage06_route import Stage06Route
from insights.benchmark_service import BenchmarkService
from insights.career_insight_service import CareerInsightService
from llm_client import EmbeddingClient

router = APIRouter()


# ── Stage 03 — Scan ───────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    file_b64: str       # base64-encoded raw bytes
    ext: str            # pdf | docx | jpg | png

class ScanResponse(BaseModel):
    virus_status:  str
    nsfw_status:   str
    csam_detected: bool
    threat_name:   Optional[str] = None


@router.post("/scan", response_model=ScanResponse)
async def scan(body: ScanRequest, request: Request):
    stage: Stage03Scan = request.app.state.stage03

    try:
        file_bytes = base64.b64decode(body.file_b64)
    except Exception:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="INVALID_BASE64")

    result = stage.run(file_bytes, body.ext.lower())

    return ScanResponse(
        virus_status=result.virus_status,
        nsfw_status=result.nsfw_status,
        csam_detected=result.csam_detected,
        threat_name=result.threat_name,
    )


# ── Stage 04 — Extract ────────────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    file_b64:   str
    ext:        str
    doc_type:   str
    doc_period: Optional[str] = None   # "2024-03" | "FY:2024-25" | ISO date

class ExtractResponse(BaseModel):
    extracted_fields:     dict
    overall_confidence:   float
    low_confidence_fields: list[str]


@router.post("/extract", response_model=ExtractResponse)
async def extract(body: ExtractRequest, request: Request):
    stage: Stage04Extract = request.app.state.stage04

    try:
        file_bytes = base64.b64decode(body.file_b64)
    except Exception:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="INVALID_BASE64")

    try:
        result = await stage.run(
            file_bytes=file_bytes,
            ext=body.ext.lower(),
            doc_type=body.doc_type,
            doc_period=body.doc_period,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return ExtractResponse(**result)


# ── Stage 05 — Resolve ────────────────────────────────────────────────────────

class ResolveRequest(BaseModel):
    pan_token:        str
    tenant_id:        str
    extracted_fields: dict

class ResolveResponse(BaseModel):
    employee_uuid:    Optional[str]
    method:           str
    confidence:       float
    needs_exception:  bool
    exception_type:   Optional[str] = None
    candidates:       list


@router.post("/resolve", response_model=ResolveResponse)
async def resolve(body: ResolveRequest, request: Request):
    if not request.app.state.db_pool:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DB_UNAVAILABLE")
    embedding_client: EmbeddingClient = request.app.state.embedding_client

    qdrant_client = getattr(request.app.state, "qdrant_client", None)
    async with request.app.state.db_pool.acquire() as db:
        stage = Stage05Resolve(db=db, embedding_client=embedding_client, qdrant_client=qdrant_client)
        result = await stage.run(
            pan_token=body.pan_token,
            tenant_id=body.tenant_id,
            extracted_fields=body.extracted_fields,
        )

    return ResolveResponse(
        employee_uuid=result.employee_uuid,
        method=result.method,
        confidence=result.confidence,
        needs_exception=result.needs_exception,
        exception_type=result.exception_type,
        candidates=result.candidates,
    )


# ── Stage 06 — Route ──────────────────────────────────────────────────────────

class RouteRequest(BaseModel):
    document_id:          str
    tenant_id:            str
    employee_uuid:        str
    pan_token:            str
    doc_type:             str
    doc_period:           Optional[str] = None
    extracted_fields:     dict
    resolution_method:    str
    resolution_confidence: float
    s3_key:               str

class ExceptionRequest(BaseModel):
    document_id:      str
    tenant_id:        str
    exception_type:   str     # NO_MATCH | MULTIPLE_CANDIDATES | LOW_CONFIDENCE
    extracted_fields: dict
    candidates:       list


@router.post("/route", status_code=status.HTTP_204_NO_CONTENT)
async def route(body: RouteRequest, request: Request):
    """
    Mark document ROUTED, write career_event, update vault_completeness.
    Called only after Stage 05 returns a resolved employee_uuid.
    """
    if not request.app.state.db_pool:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DB_UNAVAILABLE")
    async with request.app.state.db_pool.acquire() as db:
        benchmark_svc = BenchmarkService(db)
        stage = Stage06Route(db=db, benchmark_svc=benchmark_svc)
        await stage.route(
            document_id=body.document_id,
            tenant_id=body.tenant_id,
            employee_uuid=body.employee_uuid,
            pan_token=body.pan_token,
            doc_type=body.doc_type,
            doc_period=body.doc_period,
            extracted_fields=body.extracted_fields,
            resolution_method=body.resolution_method,
            resolution_confidence=body.resolution_confidence,
            s3_key=body.s3_key,
        )


@router.post("/exception", status_code=status.HTTP_204_NO_CONTENT)
async def raise_exception(body: ExceptionRequest, request: Request):
    """
    Mark document EXCEPTION and write exception_queue row.
    Called when Stage 05 returns needs_exception=True.
    """
    if not request.app.state.db_pool:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DB_UNAVAILABLE")
    async with request.app.state.db_pool.acquire() as db:
        benchmark_svc = BenchmarkService(db)
        stage = Stage06Route(db=db, benchmark_svc=benchmark_svc)
        await stage.raise_exception(
            document_id=body.document_id,
            tenant_id=body.tenant_id,
            exception_type=body.exception_type,
            extracted_fields=body.extracted_fields,
            candidates=body.candidates,
        )


# ── Insight Refresh ────────────────────────────────────────────────────────────

class RefreshInsightRequest(BaseModel):
    document_id:  str
    employee_uuid: str
    doc_type:     str
    doc_period:   Optional[str] = None
    benchmarks:   dict = {}


@router.post("/refresh-insight", status_code=status.HTTP_204_NO_CONTENT)
async def refresh_insight(body: RefreshInsightRequest, request: Request):
    """
    Generate LLM insight text for a ROUTED document and upsert embedding into Qdrant.
    Called by InsightRefreshWorkflow (prana-api) after stage06 ROUTED.
    Privacy: benchmarks contains percentiles only — no raw ₹ values.
    """
    if not request.app.state.db_pool:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DB_UNAVAILABLE")
    async with request.app.state.db_pool.acquire() as db:
        svc = CareerInsightService(
            db=db,
            llm_client=request.app.state.llm_client,
            embedding_client=request.app.state.embedding_client,
            qdrant_client=request.app.state.qdrant_client,
        )
        await svc.refresh_for_document(
            document_id=body.document_id,
            employee_uuid=body.employee_uuid,
            doc_type=body.doc_type,
            doc_period=body.doc_period,
            benchmarks=body.benchmarks,
        )
