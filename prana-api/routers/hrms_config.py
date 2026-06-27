"""
Tenant-level HRMS connector config router.

OA-Admin configures which HRMS their tenant uses, provides credentials
(stored KMS-encrypted), and manages field mapping overrides.
Mounted at /v1/hrms/config in main.py.

Tenant isolation: tenant_id always from JWT claims — never from request body.
"""
from __future__ import annotations

import logging
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from dependencies import AuthUser, CurrentUser, DbConn, require_oa
from services.hrms_connector_service import HRMSConnectorService

log    = logging.getLogger(__name__)
router = APIRouter()
_svc   = HRMSConnectorService()

# OA user of any role
OAUser      = Annotated[CurrentUser, Depends(require_oa())]
# OA-Admin only for create/delete
OAAdminUser = Annotated[CurrentUser, Depends(require_oa("OA-Admin"))]


# ── Request models ────────────────────────────────────────────────────────────

class CreateConfigRequest(BaseModel):
    connector_definition_id: UUID
    display_name:            str
    integration_mode:        str
    credentials:             dict           # encrypted by endpoint, never stored raw
    pull_schedule:           Optional[str] = None
    field_mapping:           Optional[dict] = None


class UpdateFieldMappingRequest(BaseModel):
    field_mapping: dict


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_configs(db: DbConn, current: OAUser):
    """List HRMS connector configs for the authenticated OA user's tenant."""
    tenant_id = UUID(current.tenant_id)
    items = await _svc.list_tenant_configs(tenant_id=tenant_id, db=db)
    return {"items": items, "total": len(items)}


@router.get("/{connector_id}")
async def get_config(connector_id: UUID, db: DbConn, current: OAUser):
    """Get a specific connector config (tenant-scoped by JWT)."""
    tenant_id = UUID(current.tenant_id)
    cfg = await _svc.get_tenant_config(connector_id=connector_id, tenant_id=tenant_id, db=db)
    if not cfg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CONNECTOR_CONFIG_NOT_FOUND")
    return cfg


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_config(body: CreateConfigRequest, request: Request, db: DbConn, current: OAAdminUser):
    """
    OA-Admin configures their HRMS connector.
    Credentials are KMS-encrypted with the tenant's KEK before DB write.
    tenant_id always from JWT — body tenant_id is ignored and not accepted.
    """
    tenant_id = UUID(current.tenant_id)

    kek_arn = await db.fetchval(
        "SELECT kek_arn FROM tenant WHERE tenant_id = $1",
        tenant_id,
    )
    if not kek_arn:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="TENANT_KEK_NOT_FOUND")

    kms = request.app.state.kms_service

    try:
        connector_id = await _svc.create_tenant_config(
            tenant_id=tenant_id,
            connector_definition_id=body.connector_definition_id,
            display_name=body.display_name,
            integration_mode=body.integration_mode,
            credentials=body.credentials,
            kek_arn=kek_arn,
            kms=kms,
            db=db,
            pull_schedule=body.pull_schedule,
            field_mapping=body.field_mapping,
            created_by=UUID(current.user_id),
        )
    except Exception:
        log.exception("Failed to create HRMS connector config tenant=%s", tenant_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="CONFIG_CREATE_FAILED")

    log.info("Created HRMS connector config connector_id=%s tenant=%s", connector_id, tenant_id)
    return {"connector_id": str(connector_id)}


@router.patch("/{connector_id}/field-mapping")
async def update_field_mapping(
    connector_id: UUID,
    body: UpdateFieldMappingRequest,
    db: DbConn,
    current: OAUser,
):
    """Update tenant-specific field mapping overrides."""
    tenant_id = UUID(current.tenant_id)
    await _svc.update_field_mapping(
        connector_id=connector_id,
        tenant_id=tenant_id,
        field_mapping=body.field_mapping,
        db=db,
    )
    return {"connector_id": str(connector_id), "status": "updated"}


@router.patch("/{connector_id}/pause")
async def pause_connector(connector_id: UUID, db: DbConn, current: OAUser):
    """Pause syncing for this connector."""
    tenant_id = UUID(current.tenant_id)
    await _svc.set_status(connector_id=connector_id, tenant_id=tenant_id, status="PAUSED", db=db)
    return {"connector_id": str(connector_id), "status": "paused"}


@router.patch("/{connector_id}/resume")
async def resume_connector(connector_id: UUID, db: DbConn, current: OAUser):
    """Resume syncing for a paused connector."""
    tenant_id = UUID(current.tenant_id)
    await _svc.set_status(connector_id=connector_id, tenant_id=tenant_id, status="ACTIVE", db=db)
    return {"connector_id": str(connector_id), "status": "active"}
