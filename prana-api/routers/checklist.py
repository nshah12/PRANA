"""
Go-Live Checklist — setup readiness gate before an OA-Admin can upload documents.

OA-Admin routes  → /v1/org/setup-checklist/*   (versioned, employer-facing — api-versioning.md)
PA routes        → /admin/setup-checklist/*    (unversioned, platform-staff-only)

Effective checklist for a tenant = platform baseline (PA-owned, tenant_id IS
NULL) UNION that tenant's own items (OA-Admin-owned) — additive, never an
override. The actual upload-blocking enforcement lives in routers/ingest.py's
three upload entrypoints via ChecklistService.assert_upload_allowed(); this
router only manages the checklist items and completion state.
"""

import logging
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import CurrentUser, DbConn, PortalAdmin, require_oa
from errors import PranaError
from services.checklist_service import ChecklistService

log = logging.getLogger(__name__)

router = APIRouter()

OaStaff = Annotated[CurrentUser, Depends(require_oa("oa_admin", "oa_operator"))]
OaAdmin = Annotated[CurrentUser, Depends(require_oa("oa_admin"))]


# ── Request models ──────────────────────────────────────────────────────────

class CompleteItemRequest(BaseModel):
    notes: Optional[str] = None


class AddTenantItemRequest(BaseModel):
    item_key:    str            = Field(min_length=1, max_length=100)
    title:       str            = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    is_required: bool           = True


class AddPlatformItemRequest(BaseModel):
    item_key:      str            = Field(min_length=1, max_length=100)
    title:         str            = Field(min_length=1, max_length=200)
    description:   Optional[str] = None
    is_required:   bool           = True
    display_order: int            = 0


class UpdatePlatformItemRequest(BaseModel):
    title:         Optional[str]  = None
    description:   Optional[str]  = None
    display_order: Optional[int]  = None
    is_required:   Optional[bool] = None
    is_active:     Optional[bool] = None


# ── OA-Admin / OA-Operator routes ───────────────────────────────────────────

@router.get("/v1/org/setup-checklist")
async def get_checklist(current: OaStaff, db: DbConn):
    """Effective checklist (baseline + tenant's own items) with completion status."""
    svc = ChecklistService(db)
    items = await svc.get_effective_checklist(UUID(current.tenant_id))
    return {"items": items, "total": len(items)}


@router.post("/v1/org/setup-checklist/{item_key}/complete")
async def complete_checklist_item(item_key: str, body: CompleteItemRequest, current: OaAdmin, db: DbConn):
    """OA-Admin manually confirms a checklist item (baseline or their own) is done."""
    svc = ChecklistService(db)
    try:
        await svc.complete_item(
            UUID(current.tenant_id), item_key.upper(), completed_by=UUID(current.user_id), notes=body.notes,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail=PranaError.CHECKLIST_ITEM_NOT_FOUND)
    log.info("checklist item completed: tenant=%s item=%s by=%s", current.tenant_id, item_key, current.user_id)
    return {"item_key": item_key.upper(), "completed": True}


@router.delete("/v1/org/setup-checklist/{item_key}/complete")
async def uncomplete_checklist_item(item_key: str, current: OaAdmin, db: DbConn):
    """OA-Admin undoes a completion (the underlying condition regressed)."""
    svc = ChecklistService(db)
    undone = await svc.uncomplete_item(UUID(current.tenant_id), item_key.upper())
    if not undone:
        raise HTTPException(status_code=404, detail=PranaError.CHECKLIST_ITEM_NOT_FOUND)
    log.info("checklist item un-completed: tenant=%s item=%s by=%s", current.tenant_id, item_key, current.user_id)
    return {"item_key": item_key.upper(), "completed": False}


@router.post("/v1/org/setup-checklist")
async def add_tenant_checklist_item(body: AddTenantItemRequest, current: OaAdmin, db: DbConn):
    """OA-Admin adds a tenant-specific checklist item on top of the platform baseline."""
    svc = ChecklistService(db)
    try:
        item = await svc.add_tenant_item(
            UUID(current.tenant_id), body.item_key.upper(), body.title,
            body.description, body.is_required, created_by_oa=UUID(current.user_id),
        )
    except ValueError:
        raise HTTPException(status_code=409, detail=PranaError.CHECKLIST_ITEM_KEY_TAKEN)
    log.info("tenant checklist item added: tenant=%s item=%s by=%s", current.tenant_id, body.item_key, current.user_id)
    return {"item": item}


@router.delete("/v1/org/setup-checklist/{item_key}")
async def delete_tenant_checklist_item(item_key: str, current: OaAdmin, db: DbConn):
    """OA-Admin removes their own tenant-specific item. Never the platform baseline —
    the DELETE is scoped by tenant_id, so a baseline row (tenant_id IS NULL) can never match."""
    svc = ChecklistService(db)
    deleted = await svc.delete_tenant_item(UUID(current.tenant_id), item_key.upper())
    if not deleted:
        raise HTTPException(status_code=404, detail=PranaError.CHECKLIST_ITEM_NOT_FOUND)
    log.info("tenant checklist item deleted: tenant=%s item=%s by=%s", current.tenant_id, item_key, current.user_id)
    return {"deleted": True, "item_key": item_key.upper()}


# ── PA routes — platform-baseline management ────────────────────────────────

@router.get("/admin/setup-checklist")
async def pa_list_checklist_items(current: PortalAdmin, db: DbConn):
    """PA only — list all platform-baseline checklist items."""
    svc = ChecklistService(db)
    items = await svc.list_platform_items()
    return {"items": items, "total": len(items)}


@router.post("/admin/setup-checklist")
async def pa_add_checklist_item(body: AddPlatformItemRequest, current: PortalAdmin, db: DbConn):
    """PA only — add a new platform-baseline checklist item."""
    svc = ChecklistService(db)
    try:
        item = await svc.add_platform_item(
            body.item_key.upper(), body.title, body.description,
            body.is_required, created_by_pa=UUID(current.user_id), display_order=body.display_order,
        )
    except ValueError:
        raise HTTPException(status_code=409, detail=PranaError.CHECKLIST_ITEM_KEY_TAKEN)
    log.info("platform checklist item added: item=%s by PA=%s", body.item_key, current.user_id)
    return {"item": item}


@router.patch("/admin/setup-checklist/{item_id}")
async def pa_update_checklist_item(item_id: str, body: UpdatePlatformItemRequest, current: PortalAdmin, db: DbConn):
    """PA only — edit or deactivate a platform-baseline checklist item."""
    svc = ChecklistService(db)
    try:
        item = await svc.update_platform_item(
            UUID(item_id),
            title=body.title, description=body.description, display_order=body.display_order,
            is_required=body.is_required, is_active=body.is_active,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail=PranaError.CHECKLIST_ITEM_NOT_FOUND)
    log.info("platform checklist item updated: item_id=%s by PA=%s", item_id, current.user_id)
    return {"item": item}
