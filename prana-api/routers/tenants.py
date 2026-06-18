"""
Tenant management — Portal Admin only.
GET  /admin/tenants           — list all tenants
POST /admin/tenants           — create pending tenant + trigger DomainVerificationWorkflow
GET  /admin/tenants/{id}      — get tenant detail
POST /admin/tenants/{id}/suspend
POST /admin/tenants/{id}/activate  — called by TenantProvisioningWorkflow signal
PUT  /admin/tenants/{id}/config/{key}
PATCH /admin/tenants/{id}     — update tenant profile fields
"""
import json
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr

from dependencies import PortalAdmin, DbConn
from services.tenant_service import TenantService
from lib.cache import cache_get, cache_set, invalidate_tenants

router = APIRouter()


class RegAddress(BaseModel):
    line1: str
    line2: Optional[str] = None
    city: str
    district: Optional[str] = None
    state: str
    pincode: str


class PrimaryContact(BaseModel):
    name: str
    designation: str
    email: str
    mobile: str


class CreateTenantIn(BaseModel):
    # ── Section A: Legal Identity (mandatory before KEK) ──────────────────
    tenant_name: str                          # Full registered legal name
    entity_type: Optional[str] = None        # PRIVATE_LIMITED | PUBLIC_LIMITED | LLP | ...
    cin: Optional[str] = None                # Company Identification Number (21 chars)
    gstin: Optional[str] = None              # GST Identification Number (15 chars)
    pan_entity: Optional[str] = None         # Company PAN (10 chars)
    tan: Optional[str] = None                # Tax Deduction Account Number
    brand_name: Optional[str] = None         # Trade / brand name if different
    incorporation_date: Optional[str] = None # ISO date: YYYY-MM-DD
    roc_jurisdiction: Optional[str] = None   # ROC-Mumbai, ROC-Bangalore, etc.

    # ── Section B: Registered Address (mandatory) ─────────────────────────
    primary_state: str                        # Indian state for geo-affinity routing
    reg_address: Optional[RegAddress] = None  # Full registered office address
    corp_address: Optional[RegAddress] = None # Corporate HQ if different from registered

    # ── Section D: Contacts (mandatory) ──────────────────────────────────
    primary_contact: Optional[PrimaryContact] = None
    first_oa_admin_email: str                # First OA-Admin login credentials sent here

    # ── Section E: Technical Configuration (mandatory) ────────────────────
    domain: str                              # Corporate email domain (unique, DNS-verified)
    additional_domains: Optional[List[str]] = None
    nik_type: str = "PAN"                    # PAN | AADHAAR | PASSPORT
    home_region: str = "ap-south-1"         # IMMUTABLE after provisioning
    self_upload_policy: str = "ALLOWED_WITH_WARNING"
    document_ingestion_method: str = "PORTAL_UPLOAD"  # PORTAL_UPLOAD | HRMS_API | BOTH
    hrms_system: Optional[str] = None       # SAP | Darwinbox | GreytHR | Keka | ...

    # ── Section I: DPDP Act 2023 (mandatory) ─────────────────────────────
    dpo_name: Optional[str] = None
    dpo_email: Optional[str] = None
    grievance_officer_name: Optional[str] = None
    grievance_officer_email: Optional[str] = None
    dpa_accepted: bool = False               # Data Processing Agreement acceptance
    dpa_version: str = "1.0"

    # ── Section F: Workforce Profile ──────────────────────────────────────
    industry: Optional[str] = None
    employee_headcount_band: Optional[str] = None  # 1-50 | 51-200 | 201-500 | ...
    payroll_frequency: str = "MONTHLY"       # MONTHLY | BI_MONTHLY | WEEKLY
    fiscal_year_start: str = "APRIL"         # APRIL (India default) | JANUARY

    # ── Section K: Storage & SLA ──────────────────────────────────────────
    storage_quota_gb: int = 50
    push_window_months: int = 6
    default_language: str = "en"
    sla_tier: str = "STANDARD"              # STANDARD | PRIORITY | ENTERPRISE

    # ── Section M: PA-Internal ────────────────────────────────────────────
    onboarding_tier: str = "ASSISTED"       # SELF_SERVICE | ASSISTED | ENTERPRISE
    contract_type: str = "ANNUAL"           # MONTHLY | ANNUAL | MULTI_YEAR
    account_manager: Optional[str] = None


class UpdateTenantIn(BaseModel):
    """PA can update any non-immutable tenant field post-onboarding."""
    brand_name: Optional[str] = None
    entity_type: Optional[str] = None
    industry: Optional[str] = None
    employee_headcount_band: Optional[str] = None
    payroll_frequency: Optional[str] = None
    fiscal_year_start: Optional[str] = None
    hrms_system: Optional[str] = None
    document_ingestion_method: Optional[str] = None
    primary_contact: Optional[PrimaryContact] = None
    reg_address: Optional[RegAddress] = None
    corp_address: Optional[RegAddress] = None
    dpo_name: Optional[str] = None
    dpo_email: Optional[str] = None
    grievance_officer_name: Optional[str] = None
    grievance_officer_email: Optional[str] = None
    pf_registration: Optional[str] = None
    esic_registration: Optional[str] = None
    logo_url: Optional[str] = None
    brand_colour: Optional[str] = None
    support_email: Optional[str] = None
    sla_tier: Optional[str] = None
    contract_type: Optional[str] = None
    account_manager: Optional[str] = None
    storage_quota_gb: Optional[int] = None
    push_window_months: Optional[int] = None


class SuspendIn(BaseModel):
    reason: str


class UpdateConfigIn(BaseModel):
    value: str


@router.get("", status_code=status.HTTP_200_OK)
async def list_tenants(
    current: PortalAdmin,
    db: DbConn,
    status_filter: Optional[str] = None,
    q: Optional[str] = None,
):
    # Only cache the unfiltered full list; filtered results skip cache
    cache_key = f"prana:tenants:all:{status_filter or 'ALL'}"
    if not q:
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

    svc = TenantService(db, None)
    tenants = await svc.list_all(status_filter)
    if q:
        q_lower = q.lower()
        tenants = [
            t for t in tenants
            if q_lower in t.get("tenant_name", "").lower()
            or q_lower in t.get("domain", "").lower()
        ]

    result = {"tenants": tenants}
    if not q:
        await cache_set(cache_key, result, ttl=120)
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_tenant(body: CreateTenantIn, current: PortalAdmin, request: Request, db: DbConn):
    svc = TenantService(db, request.app.state.kms_service)
    dpa_accepted_at = datetime.now(timezone.utc) if body.dpa_accepted else None
    result = await svc.create_pending(
        tenant_name=body.tenant_name,
        domain=body.domain,
        cin=body.cin,
        gstin=body.gstin,
        nik_type=body.nik_type,
        primary_state=body.primary_state,
        home_region=body.home_region,
        self_upload_policy=body.self_upload_policy,
        storage_quota_gb=body.storage_quota_gb,
        created_by_pa=current.user_id,
        brand_name=body.brand_name,
        entity_type=body.entity_type,
        pan_entity=body.pan_entity,
        tan=body.tan,
        incorporation_date=body.incorporation_date,
        roc_jurisdiction=body.roc_jurisdiction,
        reg_address=body.reg_address.model_dump() if body.reg_address else None,
        corp_address=body.corp_address.model_dump() if body.corp_address else None,
        primary_contact=body.primary_contact.model_dump() if body.primary_contact else None,
        first_oa_admin_email=body.first_oa_admin_email,
        dpo_name=body.dpo_name,
        dpo_email=body.dpo_email,
        grievance_officer_name=body.grievance_officer_name,
        grievance_officer_email=body.grievance_officer_email,
        dpa_accepted_at=dpa_accepted_at,
        dpa_version=body.dpa_version,
        industry=body.industry,
        employee_headcount_band=body.employee_headcount_band,
        payroll_frequency=body.payroll_frequency,
        fiscal_year_start=body.fiscal_year_start,
        hrms_system=body.hrms_system,
        document_ingestion_method=body.document_ingestion_method,
        additional_domains=body.additional_domains,
        push_window_months=body.push_window_months,
        default_language=body.default_language,
        sla_tier=body.sla_tier,
        onboarding_tier=body.onboarding_tier,
        contract_type=body.contract_type,
        account_manager=body.account_manager,
    )
    # WorkflowConsumer starts DomainVerificationWorkflow on seeing DOMAIN_VERIFICATION_REQUESTED
    tenant_id = result.get("tenant_id") if isinstance(result, dict) else None
    if tenant_id:
        import uuid, datetime
        kafka = getattr(request.app.state, "kafka_producer", None)
        if kafka:
            await kafka.publish("prana.ingest.events", {
                "event_type": "DOMAIN_VERIFICATION_REQUESTED",
                "event_id": str(uuid.uuid4()),
                "occurred_at": datetime.datetime.utcnow().isoformat(),
                "tenant_id": tenant_id,
                "domain": body.domain,
                "workflow_id": f"domain-verify-{tenant_id}",
            }, key=tenant_id)
    return result


@router.get("/{tenant_id}", status_code=status.HTTP_200_OK)
async def get_tenant(tenant_id: str, current: PortalAdmin, db: DbConn):
    svc = TenantService(db, None)
    tenant = await svc.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TENANT_NOT_FOUND")
    return tenant


@router.patch("/{tenant_id}", status_code=status.HTTP_200_OK)
async def update_tenant(tenant_id: str, body: UpdateTenantIn, current: PortalAdmin, db: DbConn):
    svc = TenantService(db, None)
    existing = await svc.get(tenant_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TENANT_NOT_FOUND")

    fields = body.model_dump(exclude_none=True)
    # Unwrap nested Pydantic objects to dicts
    for key in ("primary_contact", "reg_address", "corp_address"):
        if key in fields and hasattr(fields[key], "model_dump"):
            fields[key] = fields[key].model_dump()

    # PA can also update storage quota and push window directly on the row
    direct_fields = {}
    for col in ("storage_quota_gb", "push_window_months", "sla_tier", "contract_type", "account_manager"):
        if col in fields:
            direct_fields[col] = fields.pop(col)

    if direct_fields:
        set_parts = [f"{k} = ${i+2}" for i, k in enumerate(direct_fields)]
        await db.execute(
            f"UPDATE tenant SET {', '.join(set_parts)} WHERE tenant_id = $1",
            tenant_id, *direct_fields.values(),
        )

    await svc.update_profile(tenant_id, current.user_id, **fields)
    return {"message": "Tenant updated"}


@router.post("/{tenant_id}/activate", status_code=status.HTTP_200_OK)
async def activate_tenant(tenant_id: str, current: PortalAdmin, request: Request, db: DbConn):
    body = await request.json()
    email = body.get("first_oa_admin_email")
    if not email:
        row = await db.fetchrow(
            "SELECT primary_contact FROM tenant WHERE tenant_id=$1", tenant_id
        )
        if row and row["primary_contact"]:
            contact = json.loads(row["primary_contact"]) if isinstance(row["primary_contact"], str) else row["primary_contact"]
            email = contact.get("email", "")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MISSING_OA_ADMIN_EMAIL")

    svc = TenantService(db, request.app.state.kms_service)
    result = await svc.activate(tenant_id, email)
    await invalidate_tenants()
    return result


@router.post("/{tenant_id}/suspend", status_code=status.HTTP_200_OK)
async def suspend_tenant(tenant_id: str, body: SuspendIn, current: PortalAdmin, db: DbConn):
    svc = TenantService(db, None)
    await svc.suspend(tenant_id, body.reason, current.user_id)
    await invalidate_tenants()
    return {"message": "Tenant suspended"}


@router.put("/{tenant_id}/config/{key}", status_code=status.HTTP_200_OK)
async def update_tenant_config(
    tenant_id: str, key: str, body: UpdateConfigIn,
    current: PortalAdmin, db: DbConn,
):
    svc = TenantService(db, None)
    await svc.update_config(tenant_id, key, body.value, current.user_id)
    return {"message": "Config updated"}
