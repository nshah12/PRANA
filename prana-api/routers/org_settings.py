"""
Org settings & profile — OA-Admin / OA-Operator.
GET  /org/settings        — tenant config + platform defaults (legacy)
PATCH /org/settings       — update tenant-level overrides
GET  /org/profile         — full tenant profile (all enterprise fields)
PATCH /org/profile        — OA-editable fields: branding, contacts, workforce, statutory
"""
import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from dependencies import DbConn, require_oa
from services.tenant_service import TenantService
from errors import PranaError

router = APIRouter()
OAAdmin = Depends(require_oa("oa_admin"))


@router.get("/settings")
async def get_settings(db: DbConn, current=OAAdmin):
    tenant = await db.fetchrow(
        """
        SELECT t.tenant_id, t.tenant_name, t.domain, t.status, t.home_region,
               t.self_upload_policy,
               tc_ch.config_value AS employee_activation_channels
        FROM tenant t
        LEFT JOIN tenant_config tc_ch ON tc_ch.tenant_id = t.tenant_id
                                      AND tc_ch.config_key = 'employee_activation_channels'
        WHERE t.tenant_id = $1
        """,
        current.tenant_id,
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.TENANT_NOT_FOUND)

    row = dict(tenant)
    if not row.get("employee_activation_channels"):
        row["employee_activation_channels"] = await db.fetchval(
            "SELECT config_value FROM platform_config WHERE config_key='employee_activation_channels'"
        ) or "personal_email"
    return row


VALID_CHANNELS = {"personal_email", "work_email", "sms"}
BFSI_FORBIDDEN = {"sms"}


class UpdateSettingsIn(BaseModel):
    employee_activation_channels: Optional[str] = None   # comma-separated: "personal_email,sms"


@router.patch("/settings")
async def update_settings(body: UpdateSettingsIn, db: DbConn, current=OAAdmin):
    if body.employee_activation_channels is not None:
        requested = {c.strip() for c in body.employee_activation_channels.split(",") if c.strip()}
        invalid = requested - VALID_CHANNELS
        if invalid:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"INVALID_CHANNELS: {invalid}")
        if not requested:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=PranaError.AT_LEAST_ONE_CHANNEL_REQUIRED)

        self_upload = await db.fetchval(
            "SELECT config_value FROM tenant_config WHERE tenant_id=$1 AND config_key='self_upload_policy'",
            current.tenant_id,
        )
        if self_upload == "BLOCKED_ENTIRELY" and requested & BFSI_FORBIDDEN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="BFSI_POLICY: SMS channel not permitted for this tenant")

        normalised = ",".join(sorted(requested))  # stable order
        await db.execute(
            """
            INSERT INTO tenant_config (tenant_id, config_key, config_value, updated_by)
            VALUES ($1, 'employee_activation_channels', $2, $3)
            ON CONFLICT (tenant_id, config_key)
            DO UPDATE SET config_value=$2, updated_by=$3, updated_at=NOW()
            """,
            current.tenant_id, normalised, current.user_id,
        )

    return {"message": "Settings updated"}


@router.get("/profile")
async def get_org_profile(db: DbConn, current=OAAdmin):
    svc = TenantService(db, None)
    profile = await svc.get(current.tenant_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.TENANT_NOT_FOUND)
    return profile


class OrgProfileAddress(BaseModel):
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None


class OrgProfileContact(BaseModel):
    name: Optional[str] = None
    designation: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None


class UpdateOrgProfileIn(BaseModel):
    # Contacts & addresses
    primary_contact: Optional[OrgProfileContact] = None
    reg_address: Optional[OrgProfileAddress] = None
    corp_address: Optional[OrgProfileAddress] = None
    # DPDP officers
    dpo_name: Optional[str] = None
    dpo_email: Optional[str] = None
    grievance_officer_name: Optional[str] = None
    grievance_officer_email: Optional[str] = None
    # Workforce
    industry: Optional[str] = None
    employee_headcount_band: Optional[str] = None
    payroll_frequency: Optional[str] = None
    fiscal_year_start: Optional[str] = None
    hrms_system: Optional[str] = None
    document_ingestion_method: Optional[str] = None
    # Statutory
    pf_registration: Optional[str] = None
    esic_registration: Optional[str] = None
    # Branding
    brand_name: Optional[str] = None
    logo_url: Optional[str] = None
    brand_colour: Optional[str] = None
    support_email: Optional[str] = None
    # Comms
    default_language: Optional[str] = None
    push_window_months: Optional[int] = None
    self_upload_policy: Optional[str] = None
    additional_domains: Optional[List[str]] = None


@router.patch("/profile")
async def update_org_profile(body: UpdateOrgProfileIn, db: DbConn, current=OAAdmin):
    svc = TenantService(db, None)
    fields = body.model_dump(exclude_none=True)
    for key in ("primary_contact", "reg_address", "corp_address"):
        if key in fields and isinstance(fields[key], dict):
            # strip None values from nested dicts
            fields[key] = {k: v for k, v in fields[key].items() if v is not None}
    await svc.update_profile(current.tenant_id, current.user_id, **fields)
    return {"message": "Profile updated"}
