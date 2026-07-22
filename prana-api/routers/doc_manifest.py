"""
Doc-type field manifest management.

OA-Admin routes  → /v1/manifests/*
PA routes        → /admin/manifests/*

OA-Admin can view effective manifests for their tenant and create/update overrides.
Deleting an override reverts that doc_type to the platform default.
PA can view/update platform-level defaults.
"""

import logging
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from dependencies import CurrentUser, DbConn, PortalAdmin, require_oa
from services.manifest_service import ManifestService
from errors import PranaError

log = logging.getLogger(__name__)

router = APIRouter()

OaStaff = Annotated[CurrentUser, Depends(require_oa("oa_admin", "oa_operator"))]
OaAdmin = Annotated[CurrentUser, Depends(require_oa("oa_admin"))]


# ── Request / response models ──────────────────────────────────────────────────

KNOWN_DOC_TYPES = {
    "SALARY_SLIP", "FORM_16", "OFFER_LETTER", "APPOINTMENT_LETTER",
    "INCREMENT_LETTER", "PROMOTION_LETTER", "EXPERIENCE_LETTER",
    "RELIEVING_LETTER", "JOINING_LETTER", "PF_ACKNOWLEDGEMENT",
    "BANK_STATEMENT", "IT_RETURN", "INVESTMENT_PROOF", "APPRAISAL_LETTER",
    # Labour-law employee-centric types (migration 020)
    "BONUS_LETTER", "GRATUITY_LETTER", "FORM_12B", "FORM_26AS",
    "SELF_UPLOAD",
}

KNOWN_FORMATS = {"pdf", "docx", "jpeg", "jpg", "png", "tiff", "xlsx", "auto"}


class ManifestUpsertRequest(BaseModel):
    required_fields:        list[str]        = Field(default_factory=list)
    identity_fields:        list[str]        = Field(default_factory=list)
    optional_fields:        list[str]        = Field(default_factory=list)
    classification_signals: list[list[str]]  = Field(default_factory=list)
    signal_weights:         list[float]      = Field(default_factory=list)
    confidence_threshold:   float            = Field(default=0.75, ge=0.0, le=1.0)
    supported_formats:      list[str]        = Field(
        default=["pdf", "docx", "jpeg", "jpg", "png", "tiff"]
    )
    is_active:              bool             = True
    # Subset of required_fields/identity_fields/optional_fields explicitly
    # confirmed non-monetary metadata. Anything NOT here is stripped before DB
    # storage by default (fail-closed) — see prana-ai/pipeline/stage06_route.py's
    # _SAFE_METADATA_FIELDS, which this is unioned into per-tenant/doc_type.
    safe_fields:            list[str]        = Field(default_factory=list)

    @field_validator("required_fields", "identity_fields", "optional_fields")
    @classmethod
    def no_empty_strings(cls, v: list[str]) -> list[str]:
        cleaned = [f.strip() for f in v if f.strip()]
        return cleaned

    @field_validator("supported_formats")
    @classmethod
    def valid_formats(cls, v: list[str]) -> list[str]:
        bad = [f for f in v if f not in KNOWN_FORMATS]
        if bad:
            raise ValueError(f"Unknown formats: {bad}. Allowed: {sorted(KNOWN_FORMATS)}")
        return v

    @model_validator(mode="after")
    def safe_fields_must_be_declared_fields(self) -> "ManifestUpsertRequest":
        all_fields = set(self.required_fields) | set(self.identity_fields) | set(self.optional_fields)
        unknown = [f for f in self.safe_fields if f not in all_fields]
        if unknown:
            raise ValueError(
                f"safe_fields entries must be declared in required_fields/identity_fields/"
                f"optional_fields first: {unknown}"
            )
        return self


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_svc(db) -> ManifestService:
    return ManifestService(db)


def _validate_doc_type(doc_type: str) -> str:
    dt = doc_type.upper()
    if dt not in KNOWN_DOC_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"UNKNOWN_DOC_TYPE. Known types: {sorted(KNOWN_DOC_TYPES)}",
        )
    return dt


# ── OA-Admin routes ────────────────────────────────────────────────────────────

@router.get("/v1/manifests")
async def list_manifests(current: OaStaff, db: DbConn):
    """
    List effective manifests for the caller's tenant.
    Tenant overrides are shown with is_tenant_override=true.
    """
    tenant_id = UUID(current.tenant_id)
    svc = _get_svc(db)
    items = await svc.list_for_tenant(tenant_id)
    return {"items": items, "total": len(items)}


@router.get("/v1/manifests/{doc_type}")
async def get_manifest(doc_type: str, current: OaStaff, db: DbConn):
    """Get the effective manifest for a specific doc_type (tenant override or platform default)."""
    tenant_id = UUID(current.tenant_id)
    dt = _validate_doc_type(doc_type)
    svc = _get_svc(db)
    try:
        manifest = await svc.resolve(tenant_id, dt)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "manifest": {
            "manifest_id":             manifest.manifest_id,
            "doc_type":                manifest.doc_type,
            "required_fields":         manifest.required_fields,
            "identity_fields":         manifest.identity_fields,
            "optional_fields":         manifest.optional_fields,
            "classification_signals":  manifest.classification_signals,
            "signal_weights":          manifest.signal_weights,
            "safe_fields":             manifest.safe_fields,
            "confidence_threshold":    manifest.confidence_threshold,
            "supported_formats":       manifest.supported_formats,
            "usage_count":             manifest.usage_count,
            "is_tenant_override":      manifest.is_tenant_override,
        }
    }


@router.put("/v1/manifests/{doc_type}")
async def upsert_manifest(doc_type: str, body: ManifestUpsertRequest, current: OaAdmin, db: DbConn):
    """
    Create or update a tenant-level manifest override for the given doc_type.
    This shadows the platform default for this tenant only.
    """
    tenant_id = UUID(current.tenant_id)
    oa_user_id = UUID(current.user_id)
    dt = _validate_doc_type(doc_type)
    svc = _get_svc(db)

    result = await svc.upsert(
        tenant_id=tenant_id,
        doc_type=dt,
        payload=body.model_dump(),
        updated_by=oa_user_id,
    )
    log.info("manifest upsert: tenant=%s doc_type=%s by=%s", tenant_id, dt, oa_user_id)
    return {"manifest": result}


@router.delete("/v1/manifests/{doc_type}")
async def delete_manifest_override(doc_type: str, current: OaAdmin, db: DbConn):
    """
    Remove the tenant override for this doc_type.
    Pipeline falls back to the platform default after deletion.
    Returns 404 if no tenant override exists (platform default cannot be deleted here).
    """
    tenant_id = UUID(current.tenant_id)
    oa_user_id = UUID(current.user_id)
    dt = _validate_doc_type(doc_type)
    svc = _get_svc(db)
    deleted = await svc.delete_tenant_override(tenant_id, dt)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=PranaError.NO_TENANT_OVERRIDE,
        )
    log.info("manifest override deleted: tenant=%s doc_type=%s by=%s", tenant_id, dt, oa_user_id)
    return {"deleted": True, "doc_type": dt}


# ── Unclassified queue ─────────────────────────────────────────────────────────

@router.get("/v1/unclassified")
async def list_unclassified(
    current: OaStaff,
    db: DbConn,
    status: Optional[str] = "PENDING",
    limit: int = 50,
):
    """List unclassified documents for this tenant. OA-Admin reviews and resolves."""
    tenant_id = UUID(current.tenant_id)

    rows = await db.fetch(
        """
        SELECT uq.document_id, uq.reason,
               uq.declared_doc_type, uq.best_guess_doc_type, uq.best_guess_score,
               uq.partial_fields, uq.status, uq.created_at,
               d.original_filename, d.file_size_bytes
        FROM unclassified_queue uq
        JOIN document d ON d.document_id = uq.document_id
        WHERE uq.tenant_id = $1 AND uq.status = $2
        ORDER BY uq.created_at DESC
        LIMIT $3
        """,
        tenant_id, status.upper() if status else "PENDING", min(limit, 200),
    )

    import json
    items = [
        {
            "document_id":         str(r["document_id"]),
            "reason":              r["reason"],
            "declared_doc_type":   r["declared_doc_type"],
            "best_guess_doc_type": r["best_guess_doc_type"],
            "best_guess_score":    float(r["best_guess_score"]) if r["best_guess_score"] is not None else None,
            "partial_fields":      json.loads(r["partial_fields"]) if isinstance(r["partial_fields"], str) else (r["partial_fields"] or {}),
            "status":              r["status"],
            "created_at":          r["created_at"].isoformat(),
            "original_filename":   r["original_filename"],
            "file_size_bytes":     r["file_size_bytes"],
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


class ResolveUnclassifiedRequest(BaseModel):
    resolved_doc_type: str
    resolution_note:   Optional[str] = None


@router.post("/v1/unclassified/{document_id}/resolve")
async def resolve_unclassified(
    document_id: str,
    body: ResolveUnclassifiedRequest,
    current: OaStaff,
    db: DbConn,
    request: Request,
):
    """
    OA-Admin manually classifies a document and re-queues it for pipeline processing.
    Sets unclassified_queue.status = RESOLVED and publishes DOC_RECLASSIFIED to Kafka.
    WorkflowConsumer restarts DocumentPipelineWorkflow with the resolved doc_type.
    """
    tenant_id = UUID(current.tenant_id)
    oa_user_id = UUID(current.user_id)
    dt = _validate_doc_type(body.resolved_doc_type)

    row = await db.fetchrow(
        "SELECT document_id FROM unclassified_queue WHERE document_id=$1 AND tenant_id=$2",
        document_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail=PranaError.NOT_FOUND)

    await db.execute(
        """
        UPDATE unclassified_queue SET
          status = 'RESOLVED', resolved_doc_type = $2,
          resolved_by = $3, resolved_at = NOW(), updated_at = NOW()
        WHERE document_id = $1
        """,
        document_id, dt, oa_user_id,
    )

    kafka = request.app.state.kafka_producer
    await kafka.stage_changed({
        "event_type":  "DOC_RECLASSIFIED",
        "document_id": document_id,
        "tenant_id":   str(tenant_id),
        "doc_type":    dt,
        "resolved_by": str(oa_user_id),
    })

    log.info("unclassified resolved: doc=%s doc_type=%s by=%s", document_id, dt, oa_user_id)
    return {"resolved": True, "document_id": document_id, "doc_type": dt}


# ── Internal routes — called by prana-ai worker pods ──────────────────────────
# These are NOT exposed via Kong — internal VPC only, authenticated by service token.

@router.get("/internal/manifests/{tenant_id}/{doc_type}")
async def internal_get_manifest(tenant_id: str, doc_type: str, request: Request, db: DbConn):
    """
    prana-ai calls this to fetch the resolved manifest before Stage 04 extraction.
    Authenticated by X-Internal-Token header (shared secret, not JWT).
    """
    _require_internal_token(request)
    svc = _get_svc(db)
    try:
        manifest = await svc.resolve(UUID(tenant_id), doc_type.upper())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "manifest": {
            "manifest_id":             manifest.manifest_id,
            "doc_type":                manifest.doc_type,
            "required_fields":         manifest.required_fields,
            "identity_fields":         manifest.identity_fields,
            "optional_fields":         manifest.optional_fields,
            "classification_signals":  manifest.classification_signals,
            "signal_weights":          manifest.signal_weights,
            "safe_fields":             manifest.safe_fields,
            "confidence_threshold":    manifest.confidence_threshold,
            "supported_formats":       manifest.supported_formats,
            "usage_count":             manifest.usage_count,
            "is_tenant_override":      manifest.is_tenant_override,
        }
    }


@router.get("/internal/manifests/{tenant_id}")
async def internal_list_manifests(tenant_id: str, request: Request, db: DbConn):
    """prana-ai calls this to load all manifests for AUTO_DETECT scoring."""
    _require_internal_token(request)
    svc = _get_svc(db)
    items = await svc.list_for_tenant(UUID(tenant_id))
    return {"items": items}


def _require_internal_token(request: Request) -> None:
    import os
    expected = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
    provided = request.headers.get("X-Internal-Token", "")
    if not expected or provided != expected:
        raise HTTPException(status_code=403, detail=PranaError.INTERNAL_TOKEN_REQUIRED)


# ── PA routes — platform defaults ─────────────────────────────────────────────

@router.get("/admin/manifests")
async def pa_list_platform_manifests(current: PortalAdmin, db: DbConn):
    """PA only — list all platform-default manifests."""
    svc = _get_svc(db)
    items = await svc.list_all_platform()
    return {"items": items, "total": len(items)}


@router.put("/admin/manifests/{doc_type}")
async def pa_upsert_platform_manifest(
    doc_type: str,
    body: ManifestUpsertRequest,
    current: PortalAdmin,
    db: DbConn,
):
    """PA only — create or update a platform-default manifest (tenant_id = NULL)."""
    pa_id = UUID(current.user_id)
    dt = _validate_doc_type(doc_type)

    import json
    row = await db.fetchrow(
        """
        INSERT INTO doc_type_field_manifest
          (tenant_id, doc_type, required_fields, identity_fields, optional_fields,
           classification_signals, signal_weights, confidence_threshold, supported_formats,
           is_active, created_by, updated_by, safe_fields)
        VALUES (NULL,$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$10,$11)
        ON CONFLICT (doc_type) WHERE tenant_id IS NULL DO UPDATE SET
          required_fields        = EXCLUDED.required_fields,
          identity_fields        = EXCLUDED.identity_fields,
          optional_fields        = EXCLUDED.optional_fields,
          classification_signals = EXCLUDED.classification_signals,
          signal_weights         = EXCLUDED.signal_weights,
          confidence_threshold   = EXCLUDED.confidence_threshold,
          supported_formats      = EXCLUDED.supported_formats,
          is_active              = EXCLUDED.is_active,
          updated_by             = EXCLUDED.updated_by,
          updated_at             = NOW(),
          safe_fields            = EXCLUDED.safe_fields
        RETURNING manifest_id, tenant_id, doc_type, required_fields, identity_fields,
                  optional_fields, classification_signals, signal_weights,
                  confidence_threshold, supported_formats, usage_count,
                  is_active, created_at, updated_at, safe_fields
        """,
        dt,
        json.dumps(body.required_fields),
        json.dumps(body.identity_fields),
        json.dumps(body.optional_fields),
        json.dumps(body.classification_signals),
        json.dumps(body.signal_weights),
        body.confidence_threshold,
        json.dumps(body.supported_formats),
        body.is_active,
        pa_id,
        json.dumps(body.safe_fields),
    )
    log.info("platform manifest upserted: doc_type=%s by PA=%s", dt, pa_id)
    from services.manifest_service import _serialize_manifest_row
    return {"manifest": _serialize_manifest_row(dict(row))}
