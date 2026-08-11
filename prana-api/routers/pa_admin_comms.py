"""
Portal Admin (PA) endpoints — communications & policy config.
Split 2026-08-10 out of pa_admin.py (see that file's docstring). Covers:
notification log, contact/org-application review, severity/SLA policy,
Communication Hub settings, platform credentials, security HMAC rotation.
"""
import uuid
from messages import SuccessCode, success_response
import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from dependencies import DbConn, require_pa
from errors import PranaError
from services.encryption_service import compute_mobile_token

router = APIRouter()
PA = Depends(require_pa)

# ── Notification log (cross-tenant — PA only) ──────────────────────────────────

@router.get("/notifications")
async def list_notifications(
    db: DbConn,
    _=PA,
    tenant_id: Optional[str] = None,
    channel: Optional[str] = None,
    notif_status: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 200,
):
    """PA: view full notification_log, filterable by tenant/channel/status/event_type."""
    conditions: list[str] = []
    params: list = []
    idx = 1

    if tenant_id:
        conditions.append(f"tenant_id = ${idx}")
        params.append(tenant_id)
        idx += 1
    if channel:
        conditions.append(f"channel = ${idx}")
        params.append(channel)
        idx += 1
    if notif_status:
        conditions.append(f"status = ${idx}")
        params.append(notif_status)
        idx += 1
    if event_type:
        conditions.append(f"event_type = ${idx}")
        params.append(event_type)
        idx += 1

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    rows = await db.fetch(
        f"""
        SELECT notification_id, tenant_id, event_type, channel, template_id,
               recipient_type, status, provider_ref,
               sent_at, failed_at, error_message, retry_count, created_at
          FROM notification_log
         {where}
         ORDER BY created_at DESC
         LIMIT ${idx}
        """,
        *params,
    )
    items = [
        {
            "notification_id": str(r["notification_id"]),
            "tenant_id":       str(r["tenant_id"]) if r["tenant_id"] else None,
            "event_type":      r["event_type"],
            "channel":         r["channel"],
            "template_id":     r["template_id"],
            "recipient_type":  r["recipient_type"],
            "status":          r["status"],
            "provider_ref":    r["provider_ref"],
            "sent_at":         r["sent_at"].isoformat() if r["sent_at"] else None,
            "failed_at":       r["failed_at"].isoformat() if r["failed_at"] else None,
            "error_message":   r["error_message"],
            "retry_count":     r["retry_count"],
            "created_at":      r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


# ── Contact / org-application review ────────────────────────────────────────
# Relocated from routers/public.py (2026-07-15) — PA-authenticated reads/writes
# don't belong under a path named "public" (see .claude/rules/api-versioning.md).

@router.get("/contact-inquiries", status_code=200)
async def list_contact_inquiries(db: DbConn, current=PA, page: int = 1, limit: int = 50):
    offset = (page - 1) * limit
    rows = await db.fetch(
        """
        SELECT id, name, email, org, enquiry_type, message, status, submitted_at
        FROM contact_inquiry
        ORDER BY submitted_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit, offset,
    )
    total = await db.fetchval("SELECT COUNT(*) FROM contact_inquiry")
    return {
        "total": total,
        "page": page,
        "items": [
            {
                "id":           str(r["id"]),
                "name":         r["name"],
                "email":        r["email"],
                "org":          r["org"],
                "enquiry_type": r["enquiry_type"],
                "message":      r["message"],
                "status":       r["status"],
                "submitted_at": r["submitted_at"].isoformat(),
            }
            for r in rows
        ],
    }


@router.get("/org-applications", status_code=200)
async def list_org_applications(
    db: DbConn, current=PA, page: int = 1, limit: int = 50, app_status: Optional[str] = None,
):
    offset = (page - 1) * limit
    where = "WHERE status = $3" if app_status else ""
    params: list = [limit, offset]
    if app_status:
        params.append(app_status)

    rows = await db.fetch(
        f"""
        SELECT id, org_name, domain, entity_type, industry, headcount_band,
               contact_name, contact_email, contact_mobile,
               message, how_heard, agreed_to_dpa, email_verified,
               status, review_notes, submitted_at, reviewed_at
        FROM self_service_application
        {where}
        ORDER BY submitted_at DESC
        LIMIT $1 OFFSET $2
        """,
        *params,
    )
    total = await db.fetchval(
        "SELECT COUNT(*) FROM self_service_application " + where,
        *params[2:],
    )
    return {
        "total": total,
        "page": page,
        "items": [dict(r) | {"id": str(r["id"]), "submitted_at": r["submitted_at"].isoformat()} for r in rows],
    }


class ReviewIn(BaseModel):
    status:       str            # REVIEWED | APPROVED | REJECTED
    review_notes: str = ""


@router.patch("/org-applications/{app_id}", status_code=200)
async def review_application(app_id: str, body: ReviewIn, db: DbConn, current=PA):
    await db.execute(
        """
        UPDATE self_service_application
        SET status = $1, review_notes = $2, reviewed_at = NOW()
        WHERE id = $3::uuid
        """,
        body.status, body.review_notes, app_id,
    )
    return {"status": body.status}


# ── Severity / SLA policy config — see prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §5 ──

@router.get("/sla-policy")
async def list_sla_policy(db: DbConn, _=PA):
    from services.severity_policy_service import SeverityPolicyService
    items = await SeverityPolicyService(db).get_all_sla_policies()
    return {"items": items, "total": len(items)}


class SlaPolicyUpdateIn(BaseModel):
    sla_minutes: Optional[int] = Field(default=None, gt=0)
    auto_create_incident: Optional[bool] = None
    description: Optional[str] = None


@router.patch("/sla-policy/{severity}")
async def update_sla_policy(severity: str, body: SlaPolicyUpdateIn, db: DbConn, current=PA):
    from services.severity_policy_service import SeverityPolicyService
    try:
        policy = await SeverityPolicyService(db).update_sla_policy(
            severity=severity, sla_minutes=body.sla_minutes,
            auto_create_incident=body.auto_create_incident,
            description=body.description, updated_by=current.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    # Retrofit: this endpoint previously wrote no audit event at all — only
    # updated_by/updated_at columns, not tamper-evident. See
    # prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §10.3.
    from kafka.producer import get_kafka_producer
    kafka = await get_kafka_producer()
    await kafka.tenant_event({
        "event_type": "SLA_POLICY_UPDATED",
        "tenant_id": None,
        "severity": severity,
        "sla_minutes": body.sla_minutes,
        "auto_create_incident": body.auto_create_incident,
        "actor_id": current.user_id,
    })

    return {"message": SuccessCode.SLA_POLICY_UPDATED, "sla_policy": policy}


@router.get("/severity-rules")
async def list_severity_rules(db: DbConn, _=PA, domain: Optional[str] = None):
    from services.severity_policy_service import SeverityPolicyService
    items = await SeverityPolicyService(db).list_severity_rules(domain=domain)
    return {"items": items, "total": len(items)}


class SeverityRuleCreateIn(BaseModel):
    domain: str
    match_type: str
    match_value: Optional[str] = None
    occurrence_threshold: Optional[int] = None
    occurrence_threshold_max: Optional[int] = None
    window_minutes: Optional[int] = None
    severity: str
    priority: int = 100
    description: Optional[str] = None


@router.post("/severity-rules", status_code=status.HTTP_201_CREATED)
async def create_severity_rule(body: SeverityRuleCreateIn, db: DbConn, current=PA):
    from services.severity_policy_service import SeverityPolicyService
    try:
        rule = await SeverityPolicyService(db).create_severity_rule(
            domain=body.domain, match_type=body.match_type, match_value=body.match_value,
            occurrence_threshold=body.occurrence_threshold,
            occurrence_threshold_max=body.occurrence_threshold_max,
            window_minutes=body.window_minutes, severity=body.severity,
            priority=body.priority, description=body.description,
            updated_by=current.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    # Retrofit: see update_sla_policy's comment above — same pre-existing gap,
    # same fix (prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §10.3).
    from kafka.producer import get_kafka_producer
    kafka = await get_kafka_producer()
    await kafka.tenant_event({
        "event_type": "SEVERITY_RULE_CREATED",
        "tenant_id": None,
        "rule_id": rule["rule_id"],
        "domain": body.domain,
        "severity": body.severity,
        "actor_id": current.user_id,
    })

    return {"message": SuccessCode.SEVERITY_RULE_CREATED, "severity_rule": rule}


class SeverityRuleUpdateIn(BaseModel):
    occurrence_threshold: Optional[int] = None
    occurrence_threshold_max: Optional[int] = None
    window_minutes: Optional[int] = None
    severity: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None


@router.patch("/severity-rules/{rule_id}")
async def update_severity_rule(rule_id: str, body: SeverityRuleUpdateIn, db: DbConn, current=PA):
    from services.severity_policy_service import SeverityPolicyService
    try:
        rule = await SeverityPolicyService(db).update_severity_rule(
            rule_id=rule_id, occurrence_threshold=body.occurrence_threshold,
            occurrence_threshold_max=body.occurrence_threshold_max,
            window_minutes=body.window_minutes, severity=body.severity,
            priority=body.priority, is_active=body.is_active,
            description=body.description, updated_by=current.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    # Retrofit: see update_sla_policy's comment above — same pre-existing gap,
    # same fix (prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §10.3).
    from kafka.producer import get_kafka_producer
    kafka = await get_kafka_producer()
    await kafka.tenant_event({
        "event_type": "SEVERITY_RULE_UPDATED",
        "tenant_id": None,
        "rule_id": rule_id,
        "actor_id": current.user_id,
    })

    return {"message": SuccessCode.SEVERITY_RULE_UPDATED, "severity_rule": rule}


# ── Communication Hub settings — see prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §8.1 ──
# Platform Admin: full control, platform-wide (tenant_id IS NULL rows).

@router.get("/communications/channel-policy")
async def get_channel_policy(db: DbConn, current=PA):
    from services.communication_settings_service import CommunicationSettingsService
    items = await CommunicationSettingsService(db).get_channel_policy(tenant_id=None)
    return {"items": items, "total": len(items)}


class ChannelPolicyUpdateIn(BaseModel):
    channels: list[str]


@router.patch("/communications/channel-policy/{template_id}")
async def update_channel_policy(template_id: str, body: ChannelPolicyUpdateIn, db: DbConn, current=PA):
    from services.communication_settings_service import CommunicationSettingsService
    try:
        result = await CommunicationSettingsService(db).update_channel_policy(
            template_id=template_id, channels=body.channels, tenant_id=None, updated_by=current.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"message": SuccessCode.COMM_CHANNEL_POLICY_UPDATED, "channel_policy": result}


@router.get("/communications/vendor-chains")
async def get_vendor_chains(db: DbConn, current=PA):
    from services.communication_settings_service import CommunicationSettingsService
    chains = await CommunicationSettingsService(db).get_vendor_chains(tenant_id=None)
    return {"chains": chains}


class VendorChainUpdateIn(BaseModel):
    vendors: list[str]


@router.patch("/communications/vendor-chains/{channel}")
async def update_vendor_chain(channel: str, body: VendorChainUpdateIn, request: Request, db: DbConn, current=PA):
    from services.communication_settings_service import CommunicationSettingsService
    try:
        result = await CommunicationSettingsService(db, redis_client=request.app.state.redis).update_vendor_chain(
            channel=channel, vendors=body.vendors, tenant_id=None, updated_by=current.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"message": SuccessCode.COMM_VENDOR_CHAIN_UPDATED, "vendor_chain": result}


@router.get("/communications/vendor-credentials")
async def get_vendor_credentials(db: DbConn, current=PA):
    """Configuration status per vendor — never exposes secret values, only
    whether one is set and whether it came from env config or a PA-entered
    DB-stored credential. Never exposed to OA-Admin at all (no equivalent
    org/ route)."""
    from config import get_settings
    from services.communication_settings_service import CommunicationSettingsService, VENDOR_CREDENTIAL_FIELDS
    status_map = await CommunicationSettingsService(db).get_vendor_credential_status(get_settings())
    return {"vendors": status_map, "editable_fields": VENDOR_CREDENTIAL_FIELDS}


class VendorCredentialUpdateIn(BaseModel):
    field_name: str
    value: str = Field(min_length=1)


@router.patch("/communications/vendor-credentials/{vendor}")
async def update_vendor_credential(vendor: str, body: VendorCredentialUpdateIn, request: Request, db: DbConn, current=PA):
    """KMS-encrypts under the platform auth CMK before storing — same pattern
    as enc_mobile/totp_secret_enc. Never logs or echoes the plaintext value."""
    from services.communication_settings_service import CommunicationSettingsService
    from services.encryption_service import resolve_platform_auth_kek_arn

    kms = request.app.state.kms_service
    kek_arn = resolve_platform_auth_kek_arn(request.app.state.settings)
    try:
        await CommunicationSettingsService(db).set_vendor_credential(
            vendor=vendor, field_name=body.field_name, value=body.value,
            updated_by=current.user_id, kms=kms, kek_arn=kek_arn,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"message": SuccessCode.COMM_VENDOR_CREDENTIAL_ROTATED, "vendor": vendor, "field_name": body.field_name}


@router.get("/platform-credentials")
async def get_platform_credentials(db: DbConn, current=PA):
    """Non-communication paid-service credentials (currently: Qdrant). See
    services/platform_credential_service.py for why this is split from
    /communications/vendor-credentials rather than merged into it. Same
    never-expose-the-secret guarantee as that endpoint."""
    from config import get_settings
    from services.platform_credential_service import PlatformCredentialService, PLATFORM_CREDENTIAL_FIELDS
    status_map = await PlatformCredentialService(db).get_status(get_settings())
    return {"vendors": status_map, "editable_fields": PLATFORM_CREDENTIAL_FIELDS}


class PlatformCredentialUpdateIn(BaseModel):
    field_name: str
    value: str = Field(min_length=1)


@router.patch("/platform-credentials/{vendor}")
async def update_platform_credential(vendor: str, body: PlatformCredentialUpdateIn, request: Request, db: DbConn, current=PA):
    from services.platform_credential_service import PlatformCredentialService
    from services.encryption_service import resolve_platform_auth_kek_arn

    kms = request.app.state.kms_service
    kek_arn = resolve_platform_auth_kek_arn(request.app.state.settings)
    try:
        await PlatformCredentialService(db).set_credential(
            vendor=vendor, field_name=body.field_name, value=body.value,
            updated_by=current.user_id, kms=kms, kek_arn=kek_arn,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"message": SuccessCode.PLATFORM_CREDENTIAL_ROTATED, "vendor": vendor, "field_name": body.field_name}


@router.post("/security/hmac-rotation/approve")
async def approve_hmac_rotation(request: Request, current=PA):
    """Signals the perpetual HMACSecretRotationWorkflow (id=hmac-secret-rotation-perpetual)
    with this PA's identity — rotation proceeds only once 2 DISTINCT PA accounts
    have signaled (schema.sql's documented '4-eyes enforcement' requirement).
    Approver identity always from the JWT (current.user_id), never the request
    body — same rule as every other actor-identity field in this codebase."""
    temporal = getattr(request.app.state, "temporal_client", None)
    if not temporal:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=PranaError.WORKFLOW_UNAVAILABLE)
    try:
        wf = temporal.get_workflow_handle("hmac-secret-rotation-perpetual")
        await wf.signal("approve", current.user_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=PranaError.WORKFLOW_UNAVAILABLE) from exc
    return {"message": SuccessCode.HMAC_ROTATION_APPROVAL_SIGNALED}

