"""
PA-level HRMS connector definition router.

Manages the platform's connector catalogue (factory pattern).
Portal Admin only — OA users cannot access these endpoints.
Mounted at /v1/admin/hrms/definitions in main.py.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, field_validator

from dependencies import DbConn, PortalAdmin
from services.hrms_connector_service import HRMSConnectorService, _VALID_AUTH_METHODS
from errors import PranaError

log    = logging.getLogger(__name__)
router = APIRouter()
_svc   = HRMSConnectorService()


# ── Request models ────────────────────────────────────────────────────────────

class CreateDefinitionRequest(BaseModel):
    connector_key:          str
    display_name:           str
    auth_method:            str
    supported_modes:        list[str]
    canonical_field_schema: dict
    docs_url:               Optional[str] = None
    logo_url:               Optional[str] = None

    @field_validator("auth_method")
    @classmethod
    def validate_auth_method(cls, v: str) -> str:
        if v not in _VALID_AUTH_METHODS:
            raise ValueError(f"auth_method must be one of {sorted(_VALID_AUTH_METHODS)}")
        return v

    @field_validator("supported_modes")
    @classmethod
    def validate_modes(cls, v: list[str]) -> list[str]:
        valid = {"PULL", "PUSH", "WEBHOOK", "SHARED_LOCATION"}
        bad = set(v) - valid
        if bad:
            raise ValueError(f"Unsupported modes: {bad}")
        return v


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_definitions(db: DbConn, _pa: PortalAdmin):
    """List all active connector definitions available on the platform."""
    items = await _svc.list_definitions(db)
    return {"items": items, "total": len(items)}


@router.get("/{connector_key}")
async def get_definition(connector_key: str, db: DbConn, _pa: PortalAdmin):
    """Get a single connector definition by its key (e.g. 'darwinbox')."""
    defn = await _svc.get_definition(connector_key=connector_key, db=db)
    if not defn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.CONNECTOR_NOT_FOUND)
    return defn


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_definition(body: CreateDefinitionRequest, db: DbConn, _pa: PortalAdmin):
    """Register a new HRMS connector type on the platform."""
    try:
        new_id = await _svc.create_definition(
            connector_key=body.connector_key,
            display_name=body.display_name,
            auth_method=body.auth_method,
            supported_modes=body.supported_modes,
            canonical_field_schema=body.canonical_field_schema,
            docs_url=body.docs_url,
            logo_url=body.logo_url,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    log.info("PA created connector definition connector_key=%s", body.connector_key)
    return {"connector_definition_id": str(new_id)}


@router.patch("/{connector_definition_id}/activate")
async def activate_definition(connector_definition_id: UUID, db: DbConn, _pa: PortalAdmin):
    """Enable a connector so tenants can configure it."""
    await _svc.set_definition_active(connector_definition_id=connector_definition_id, is_active=True, db=db)
    return {"connector_definition_id": str(connector_definition_id), "status": "activated"}


@router.patch("/{connector_definition_id}/deactivate")
async def deactivate_definition(connector_definition_id: UUID, db: DbConn, _pa: PortalAdmin):
    """Disable a connector — existing tenant configs remain but can no longer sync."""
    await _svc.set_definition_active(connector_definition_id=connector_definition_id, is_active=False, db=db)
    return {"connector_definition_id": str(connector_definition_id), "status": "deactivated"}
