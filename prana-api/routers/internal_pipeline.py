"""
Internal pipeline callback router — NOT exposed via Kong.
Called only by prana-ai (VPC-internal, port 8000 direct).
Mounted at /internal/pipeline/ in main.py.

Auth: X-Internal-Service: prana-ai header (checked before any DB call).
Kong routes do NOT include /internal/* — this is enforced in kong.yml.
SG rule: api_from_ai_internal in terraform/modules/networking/main.tf.
"""
import logging
import random
import string
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from errors import PranaError


log = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)

_ALLOWED_INTERNAL_SERVICES = {"prana-ai"}


def _gen_verification_code() -> str:
    """PRANA-XXXXXX-XXXXXX — 19 chars total, URL-safe, human-readable."""
    chars = string.ascii_uppercase + string.digits
    a = "".join(random.choices(chars, k=6))
    b = "".join(random.choices(chars, k=6))
    return f"PRANA-{a}-{b}"


def _require_internal(x_internal_service: Optional[str] = Header(default=None)):
    if x_internal_service not in _ALLOWED_INTERNAL_SERVICES:
        raise HTTPException(status_code=403, detail=PranaError.INTERNAL_ONLY)


# ── Models ────────────────────────────────────────────────────────────────────

class PipelineStagePayload(BaseModel):
    document_id: str
    tenant_id:   str
    stage:       str   # ENCRYPTING | SCANNING | EXTRACTING | RESOLVING | ROUTED | EXCEPTION | CSAM_HOLD
    status:      str   # IN_PROGRESS | COMPLETE | FAILED
    detail:      Optional[str] = None


class RoutedPayload(BaseModel):
    document_id:          str
    tenant_id:            str
    employee_uuid:        str
    pan_token:            str
    doc_type:             str
    doc_period:           Optional[str] = None
    resolution_method:    str
    resolution_confidence: float


class ExceptionPayload(BaseModel):
    document_id:    str
    tenant_id:      str
    exception_type: str   # UNRESOLVED | LOW_CONFIDENCE | CSAM_HOLD
    reason:         Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/stage", dependencies=[Depends(_require_internal)])
async def pipeline_stage_update(payload: PipelineStagePayload, request: Request):
    """
    prana-ai calls this at each pipeline stage transition.
    Publishes stage_changed event to prana.pipeline.events so SSEFanoutConsumer
    can push the update to the browser without prana-ai needing Kafka credentials.
    """
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        try:
            await kafka.stage_changed(
                document_id=payload.document_id,
                tenant_id=payload.tenant_id,
                stage=payload.stage,
                status=payload.status,
                detail=payload.detail,
            )
        except Exception:
            log.exception("stage_changed publish failed doc=%s stage=%s",
                          payload.document_id, payload.stage)

    return {"accepted": True}


@router.post("/routed", dependencies=[Depends(_require_internal)])
async def pipeline_routed(payload: RoutedPayload, request: Request):
    """
    prana-ai calls this after Stage06 commits the ROUTED state to its local DB.
    prana-api publishes DOC_ROUTED to prana.pipeline.events — triggers:
      - SSEFanoutConsumer → browser update
      - WorkflowConsumer  → VaultCompletenessWorkflow
      - AnalyticsConsumer → vault_health_score update
    """
    db = request.app.state.db_pool
    kafka = getattr(request.app.state, "kafka_producer", None)

    # Update pipeline_status in prana-api's document row (prana-ai writes to
    # its own DB view; prana-api is authoritative for the REST-facing document table)
    vcode = _gen_verification_code()
    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE document
            SET pipeline_status     = 'ROUTED',
                employee_uuid       = $2,
                pan_token           = $3,
                doc_type            = $4,
                routed_at           = NOW(),
                verification_code   = COALESCE(verification_code, $6)
            WHERE document_id = $1
              AND tenant_id   = $5
              AND is_deleted  = FALSE
            """,
            payload.document_id,
            payload.employee_uuid,
            payload.pan_token,
            payload.doc_type,
            payload.tenant_id,
            vcode,
        )

    if kafka:
        try:
            await kafka.doc_routed(
                document_id=payload.document_id,
                tenant_id=payload.tenant_id,
                employee_uuid=payload.employee_uuid,
                pan_token=payload.pan_token,
                doc_type=payload.doc_type,
                doc_period=payload.doc_period,
                resolution_method=payload.resolution_method,
                resolution_confidence=payload.resolution_confidence,
            )
        except Exception:
            log.exception("DOC_ROUTED publish failed doc=%s", payload.document_id)

    return {"accepted": True}


@router.post("/exception", dependencies=[Depends(_require_internal)])
async def pipeline_exception(payload: ExceptionPayload, request: Request):
    """
    prana-ai calls this when a document cannot be resolved or fails safety scan.
    prana-api publishes a pipeline event so SSE updates the portal exception queue.
    """
    kafka = getattr(request.app.state, "kafka_producer", None)

    if kafka:
        try:
            await kafka.stage_changed(
                document_id=payload.document_id,
                tenant_id=payload.tenant_id,
                stage="EXCEPTION",
                status="FAILED",
                detail=payload.exception_type,
            )
        except Exception:
            log.exception("EXCEPTION publish failed doc=%s", payload.document_id)

    return {"accepted": True}
