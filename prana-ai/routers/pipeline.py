"""
Pipeline stage endpoints — called by Temporal activities in prana-api.

All endpoints accept base64-encoded file bytes where raw binary is needed,
or plain JSON for metadata-only stages.

Stage 03 (scan)        — sync, no LLM
Stage 04 (extract)     — async, manifest-driven LLM extraction; returns
                          either Stage04Result or AutoDetectFailed (→ unclassified)
Stage 05 (resolve)     — async, manifest identity_fields-driven 4-level ladder
Stage 06 /route        — async, DB writes after successful resolution
Stage 06 /exception    — identity resolution failed → exception_queue
Stage 06 /unclassified — doc type unknown → unclassified_queue
"""

import base64
import json
import logging
from typing import Optional

import asyncpg
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from pipeline.stage03_scan import Stage03Scan
from pipeline.stage04_extract import Stage04Extract, Stage04Result, AutoDetectFailed
from pipeline.stage05_resolve import Stage05Resolve
from pipeline.stage06_route import Stage06Route
from insights.benchmark_service import BenchmarkService
from insights.career_insight_service import CareerInsightService
from manifest.manifest_client import ManifestClient
from llm_client import EmbeddingClient

log = logging.getLogger(__name__)
router = APIRouter()


# ── helpers ───────────────────────────────────────────────────────────────────

def _decode_b64(value: str, field: str) -> bytes:
    try:
        return base64.b64decode(value)
    except Exception:
        raise HTTPException(status_code=422, detail=f"INVALID_BASE64:{field}")

def _db(request: Request) -> asyncpg.Pool:
    pool = request.app.state.db_pool
    if not pool:
        raise HTTPException(status_code=503, detail="DB_UNAVAILABLE")
    return pool

def _manifests(request: Request) -> ManifestClient:
    return request.app.state.manifest_client


# ── Stage 03 — Scan ───────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    file_b64: str
    ext: str

class ScanResponse(BaseModel):
    virus_status:  str
    nsfw_status:   str
    csam_detected: bool
    threat_name:   Optional[str] = None


@router.post("/scan", response_model=ScanResponse)
async def scan(body: ScanRequest, request: Request):
    stage: Stage03Scan = request.app.state.stage03
    file_bytes = _decode_b64(body.file_b64, "file_b64")
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
    tenant_id:  str                    # needed for manifest lookup
    doc_period: Optional[str] = None

class ExtractResponse(BaseModel):
    status:               str          # "ok" | "unclassified"
    # populated when status == "ok"
    extracted_fields:     Optional[dict]       = None
    overall_confidence:   Optional[float]      = None
    low_confidence_fields: Optional[list[str]] = None
    doc_type:             Optional[str]        = None
    manifest_id:          Optional[str]        = None
    auto_detected:        Optional[bool]       = None
    # populated when status == "unclassified"
    best_guess_doc_type:  Optional[str]        = None
    best_guess_score:     Optional[float]      = None
    partial_fields:       Optional[dict]       = None


@router.post("/extract", response_model=ExtractResponse)
async def extract(body: ExtractRequest, request: Request):
    stage: Stage04Extract = request.app.state.stage04
    file_bytes = _decode_b64(body.file_b64, "file_b64")

    result = await stage.run(
        file_bytes=file_bytes,
        ext=body.ext.lower(),
        doc_type=body.doc_type,
        tenant_id=body.tenant_id,
        doc_period=body.doc_period,
    )

    if isinstance(result, AutoDetectFailed):
        log.info(
            "AUTO_DETECT failed: tenant=%s best_guess=%s score=%.2f",
            body.tenant_id, result.best_guess_doc_type, result.best_guess_score,
        )
        return ExtractResponse(
            status="unclassified",
            best_guess_doc_type=result.best_guess_doc_type,
            best_guess_score=result.best_guess_score,
            partial_fields=result.partial_fields,
        )

    return ExtractResponse(
        status="ok",
        extracted_fields=result.extracted_fields,
        overall_confidence=result.overall_confidence,
        low_confidence_fields=result.low_confidence_fields,
        doc_type=result.doc_type,
        manifest_id=result.manifest_id,
        auto_detected=result.auto_detected,
    )


# ── Stage 05 — Resolve ────────────────────────────────────────────────────────

class ResolveRequest(BaseModel):
    pan_token:        Optional[str]
    tenant_id:        str
    doc_type:         str              # used to fetch the correct manifest
    extracted_fields: dict

class ResolveResponse(BaseModel):
    employee_uuid:   Optional[str]
    method:          str
    confidence:      float
    needs_exception: bool
    exception_type:  Optional[str] = None
    candidates:      list


@router.post("/resolve", response_model=ResolveResponse)
async def resolve(body: ResolveRequest, request: Request):
    pool = _db(request)
    embedding_client: EmbeddingClient = request.app.state.embedding_client
    qdrant_client = getattr(request.app.state, "qdrant_client", None)
    manifest_client: ManifestClient = _manifests(request)

    # Fetch the manifest so Stage05 knows which identity signals to use
    try:
        manifest = await manifest_client.resolve(body.tenant_id, body.doc_type)
    except Exception as exc:
        log.warning("Manifest fetch failed for %s/%s: %s — using all identity levels", body.tenant_id, body.doc_type, exc)
        manifest = None

    async with pool.acquire() as db:
        stage = Stage05Resolve(db=db, embedding_client=embedding_client, qdrant_client=qdrant_client)
        result = await stage.run(
            pan_token=body.pan_token,
            tenant_id=body.tenant_id,
            extracted_fields=body.extracted_fields,
            manifest=manifest,
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
    document_id:           str
    tenant_id:             str
    employee_uuid:         str
    pan_token:             str
    doc_type:              str
    doc_period:            Optional[str] = None
    extracted_fields:      dict
    resolution_method:     str
    resolution_confidence: float
    s3_key:                str


@router.post("/route", status_code=status.HTTP_204_NO_CONTENT)
async def route(body: RouteRequest, request: Request):
    """Mark document ROUTED, write career_event, update vault_completeness."""
    pool = _db(request)
    async with pool.acquire() as db:
        stage = Stage06Route(db=db, benchmark_svc=BenchmarkService(db))
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


# ── Stage 06 — Exception (identity resolution failed) ────────────────────────

class ExceptionRequest(BaseModel):
    document_id:      str
    tenant_id:        str
    exception_type:   str     # NO_MATCH | MULTIPLE_CANDIDATES | LOW_CONFIDENCE
    extracted_fields: dict
    candidates:       list


@router.post("/exception", status_code=status.HTTP_204_NO_CONTENT)
async def raise_exception(body: ExceptionRequest, request: Request):
    """Write EXCEPTION status + exception_queue row (identity resolution failure)."""
    pool = _db(request)
    async with pool.acquire() as db:
        stage = Stage06Route(db=db, benchmark_svc=BenchmarkService(db))
        await stage.raise_exception(
            document_id=body.document_id,
            tenant_id=body.tenant_id,
            exception_type=body.exception_type,
            extracted_fields=body.extracted_fields,
            candidates=body.candidates,
        )


# ── Stage 06 — Unclassified (doc type unknown / AUTO_DETECT failed) ───────────

class UnclassifiedRequest(BaseModel):
    document_id:         str
    tenant_id:           str
    declared_doc_type:   Optional[str] = None   # what HRMS said (may be None)
    best_guess_doc_type: Optional[str] = None
    best_guess_score:    float = 0.0
    partial_fields:      dict = {}
    reason:              str = "AUTO_DETECT_FAILED"  # AUTO_DETECT_FAILED | FORMAT_UNSUPPORTED


@router.post("/unclassified", status_code=status.HTTP_204_NO_CONTENT)
async def write_unclassified(body: UnclassifiedRequest, request: Request):
    """
    Write UNCLASSIFIED status + unclassified_queue row.
    Called when Stage04 returns AutoDetectFailed.
    OA-Admin resolves via GET/POST /v1/unclassified in prana-api.
    """
    pool = _db(request)
    async with pool.acquire() as db:
        async with db.transaction():
            await db.execute(
                "UPDATE document SET pipeline_status='UNCLASSIFIED', updated_at=NOW() WHERE document_id=$1",
                body.document_id,
            )
            await db.execute(
                """
                INSERT INTO unclassified_queue
                  (document_id, tenant_id, reason, declared_doc_type,
                   best_guess_doc_type, best_guess_score, partial_fields, status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,'PENDING')
                ON CONFLICT (document_id) DO UPDATE SET
                  reason               = EXCLUDED.reason,
                  best_guess_doc_type  = EXCLUDED.best_guess_doc_type,
                  best_guess_score     = EXCLUDED.best_guess_score,
                  partial_fields       = EXCLUDED.partial_fields,
                  status               = 'PENDING',
                  updated_at           = NOW()
                """,
                body.document_id,
                body.tenant_id,
                body.reason,
                body.declared_doc_type,
                body.best_guess_doc_type,
                body.best_guess_score,
                json.dumps(body.partial_fields),
            )
    log.info(
        "unclassified: doc=%s tenant=%s reason=%s best_guess=%s",
        body.document_id, body.tenant_id, body.reason, body.best_guess_doc_type,
    )


# ── Insight Refresh ────────────────────────────────────────────────────────────

class RefreshInsightRequest(BaseModel):
    document_id:   str
    employee_uuid: str
    doc_type:      str
    doc_period:    Optional[str] = None
    benchmarks:    dict = {}


@router.post("/refresh-insight", status_code=status.HTTP_204_NO_CONTENT)
async def refresh_insight(body: RefreshInsightRequest, request: Request):
    """
    Generate LLM insight text for a ROUTED document and upsert embedding into Qdrant.
    Called by InsightRefreshWorkflow after stage06 ROUTED.
    Privacy: benchmarks contains percentiles only — no raw ₹ values.
    """
    pool = _db(request)
    async with pool.acquire() as db:
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
