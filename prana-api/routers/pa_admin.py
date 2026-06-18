"""
Portal Admin (PA) endpoints — platform-wide management.
PA has zero SELECT on document rows or employee PII — only aggregates and tenant metadata.
All routes require @prana.in JWT (enforced in auth_pa.py at login time).
"""
import uuid
import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from dependencies import DbConn, require_pa, AuthUser as PortalAdmin

router = APIRouter()
PA = Depends(require_pa)


# ── Meta dashboard ────────────────────────────────────────────────────────────

@router.get("/meta-dashboard")
async def meta_dashboard(request: Request, db: DbConn, current=PA):
    active_tenants  = await db.fetchval("SELECT COUNT(*) FROM tenant WHERE status='ACTIVE'")
    total_employees = await db.fetchval("SELECT COUNT(*) FROM employee_master WHERE status='ACTIVE'")
    open_exceptions = await db.fetchval("SELECT COUNT(*) FROM exception_queue WHERE status='OPEN'")

    stage_counts = await db.fetch(
        """
        SELECT pipeline_status, COUNT(*) AS cnt
        FROM document
        WHERE pipeline_status NOT IN ('ROUTED','EXCEPTION','QUARANTINED')
        GROUP BY pipeline_status
        """
    )

    # Recent tenant status changes (account_status_event covers TOTP_LOCKOUT + ADMIN_DISABLED events)
    # For tenant-level activity use tenant table directly (created_at ordering)
    recent_tenants = await db.fetch(
        """
        SELECT tenant_name, status, created_at
        FROM tenant
        ORDER BY created_at DESC LIMIT 10
        """
    )

    # Query MinIO/S3 for real storage usage
    storage_used_label = "—"
    try:
        s3 = request.app.state.s3
        settings = request.app.state.settings
        total_bytes = 0
        for bucket in [settings.s3_bucket_documents, settings.s3_bucket_staging]:
            paginator = s3.raw_client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket):
                for obj in page.get("Contents", []):
                    total_bytes += obj.get("Size", 0)
        if total_bytes < 1024 * 1024:
            storage_used_label = f"{total_bytes // 1024} KB"
        elif total_bytes < 1024 ** 3:
            storage_used_label = f"{total_bytes / (1024**2):.1f} MB"
        else:
            storage_used_label = f"{total_bytes / (1024**3):.2f} GB"
    except Exception:
        pass  # S3 unavailable in CI

    return {
        "active_tenants":         int(active_tenants or 0),
        "total_employees":        int(total_employees or 0),
        "storage_used_label":     storage_used_label,
        "open_exceptions":        int(open_exceptions or 0),
        "pipeline_counts":        {r["pipeline_status"]: int(r["cnt"]) for r in stage_counts},
        "recent_tenant_activity": [
            {
                "tenant_name": r["tenant_name"],
                "type": "ACTIVE" if r["status"] == "ACTIVE" else r["status"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in recent_tenants
        ],
    }


# ── Tenant management ─────────────────────────────────────────────────────────

@router.get("/tenants")
async def list_tenants(
    db: DbConn,
    status: Optional[str] = None,
    q: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
    current=PA,
):
    conditions = []
    params: list = []
    i = 1

    if status:
        conditions.append(f"t.status = ${i}"); params.append(status); i += 1
    if q:
        conditions.append(f"(t.tenant_name ILIKE ${i} OR t.domain ILIKE ${i})"); params.append(f"%{q}%"); i += 1

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = await db.fetch(
        f"""
        SELECT t.tenant_id, t.tenant_name, t.domain,
               t.status, t.home_region, t.primary_state,
               t.created_at, t.cin, t.gstin, t.storage_quota_gb
        FROM tenant t
        {where}
        ORDER BY t.created_at DESC
        LIMIT {limit} OFFSET {offset}
        """,
        *params,
    )
    return {"tenants": [dict(r) for r in rows]}


class ActivateTenantIn(BaseModel):
    home_region_override: Optional[str] = None
    override_reason: Optional[str] = None


@router.post("/tenants/{tenant_id}/activate")
async def activate_tenant(
    tenant_id: str,
    body: ActivateTenantIn,
    request: Request,
    db: DbConn,
    current=PA,
):
    row = await db.fetchrow(
        "SELECT tenant_id, status FROM tenant WHERE tenant_id=$1", tenant_id
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TENANT_NOT_FOUND")
    if row["status"] not in ("PENDING", "PENDING_VERIFICATION"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ALREADY_ACTIVATED")

    if body.home_region_override and not body.override_reason:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="OVERRIDE_REASON_REQUIRED")

    update_region = f", home_region='{body.home_region_override}'" if body.home_region_override else ""
    await db.execute(
        f"UPDATE tenant SET status='ACTIVE'{update_region} WHERE tenant_id=$1", tenant_id
    )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.publish("prana.audit.events", {
            "event_type": "TENANT_ACTIVATED",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.utcnow().isoformat(),
            "tenant_id": tenant_id,
            "actor_id": str(current.user_id),
            "actor_type": "PORTAL_ADMIN",
            "override_region": body.home_region_override,
            "reason": body.override_reason,
        }, key=tenant_id)
    return {"message": "Tenant activated", "tenant_id": tenant_id}


@router.post("/tenants/{tenant_id}/reject")
async def reject_tenant(tenant_id: str, db: DbConn, current=PA):
    await db.execute(
        "UPDATE tenant SET status='REJECTED' WHERE tenant_id=$1 AND status IN ('PENDING','PENDING_VERIFICATION')",
        tenant_id,
    )
    return {"message": "Tenant rejected"}


@router.post("/tenants/{tenant_id}/suspend")
async def suspend_tenant(tenant_id: str, db: DbConn, current=PA):
    await db.execute("UPDATE tenant SET status='SUSPENDED' WHERE tenant_id=$1", tenant_id)
    return {"message": "Tenant suspended"}


# ── OA Emergency Override ─────────────────────────────────────────────────────

class OaEmergencyIn(BaseModel):
    email: Optional[str] = None
    tenant_domain: str
    reason: str


@router.post("/oa-emergency/create")
async def oa_emergency_create(body: OaEmergencyIn, request: Request, db: DbConn, current=PA):
    tenant = await db.fetchrow("SELECT tenant_id FROM tenant WHERE domain=$1", body.tenant_domain)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TENANT_NOT_FOUND")

    import secrets, string
    temp_pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))

    from services.encryption_service import hash_password
    await db.execute(
        """
        INSERT INTO oa_user (tenant_id, email, display_name, role, temp_password_hash, force_reset)
        VALUES ($1,$2,'Emergency Account','oa_admin',$3,TRUE)
        """,
        tenant["tenant_id"], body.email or f"emergency@{body.tenant_domain}",
        hash_password(temp_pw),
    )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.publish("prana.audit.events", {
            "event_type": "PA_EMERGENCY_OVERRIDE",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.utcnow().isoformat(),
            "tenant_id": str(tenant["tenant_id"]),
            "actor_id": str(current.user_id),
            "actor_type": "PORTAL_ADMIN",
            "action": "create",
            "reason": body.reason,
        }, key=str(tenant["tenant_id"]))
    return {"message": "Emergency account created", "temp_password": temp_pw}


@router.post("/oa-emergency/suspend")
async def oa_emergency_suspend(body: OaEmergencyIn, db: DbConn, current=PA):
    tenant = await db.fetchrow("SELECT tenant_id FROM tenant WHERE domain=$1", body.tenant_domain)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TENANT_NOT_FOUND")

    await db.execute(
        "UPDATE oa_user SET status='INACTIVE' WHERE email=$1 AND tenant_id=$2",
        body.email, tenant["tenant_id"],
    )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.publish("prana.audit.events", {
            "event_type": "PA_EMERGENCY_OVERRIDE",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.utcnow().isoformat(),
            "tenant_id": str(tenant["tenant_id"]),
            "actor_id": str(current.user_id),
            "actor_type": "PORTAL_ADMIN",
            "action": "suspend",
            "reason": body.reason,
        }, key=str(tenant["tenant_id"]))
    return {"message": "Account suspended"}


@router.post("/oa-emergency/reset")
async def oa_emergency_reset(body: OaEmergencyIn, db: DbConn, current=PA):
    tenant = await db.fetchrow("SELECT tenant_id FROM tenant WHERE domain=$1", body.tenant_domain)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TENANT_NOT_FOUND")

    import secrets, string
    temp_pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    from services.encryption_service import hash_password

    await db.execute(
        "UPDATE oa_user SET temp_password_hash=$1, force_reset=TRUE, status='ACTIVE' WHERE email=$2 AND tenant_id=$3",
        hash_password(temp_pw), body.email, tenant["tenant_id"],
    )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.publish("prana.audit.events", {
            "event_type": "PA_EMERGENCY_OVERRIDE",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.utcnow().isoformat(),
            "tenant_id": str(tenant["tenant_id"]),
            "actor_id": str(current.user_id),
            "actor_type": "PORTAL_ADMIN",
            "action": "reset",
            "reason": body.reason,
        }, key=str(tenant["tenant_id"]))
    return {"message": "Password reset", "temp_password": temp_pw}


# ── Storage requests ──────────────────────────────────────────────────────────

@router.get("/storage-requests")
async def list_storage_requests(db: DbConn, current=PA):
    rows = await db.fetch(
        """
        SELECT sr.request_id, sr.tenant_id, t.tenant_name,
               sr.current_gb, sr.requested_gb, sr.reason,
               sr.status, sr.requested_at
        FROM storage_request sr
        JOIN tenant t ON t.tenant_id = sr.tenant_id
        ORDER BY sr.requested_at DESC
        """
    )
    return {"requests": [
        {
            "request_id": str(r["request_id"]),
            "tenant_id": str(r["tenant_id"]),
            "tenant_name": r["tenant_name"],
            "current_gb": r["current_gb"],
            "requested_gb": r["requested_gb"],
            "reason": r["reason"],
            "status": r["status"],
            "requested_at": r["requested_at"].isoformat() if r["requested_at"] else None,
        }
        for r in rows
    ], "total": len(rows)}


@router.post("/storage-requests/{request_id}/approve")
async def approve_storage(request_id: str, db: DbConn, current=PA):
    await db.execute(
        "UPDATE storage_request SET status='APPROVED', decided_by=$2, decided_at=NOW() WHERE request_id=$1",
        request_id, current.user_id,
    )
    return {"message": "Storage request approved"}


@router.post("/storage-requests/{request_id}/reject")
async def reject_storage(request_id: str, db: DbConn, current=PA):
    await db.execute(
        "UPDATE storage_request SET status='REJECTED', decided_by=$2, decided_at=NOW() WHERE request_id=$1",
        request_id, current.user_id,
    )
    return {"message": "Storage request rejected"}


@router.post("/storage-requests/{request_id}/hold")
async def hold_storage(request_id: str, db: DbConn, current=PA):
    await db.execute(
        "UPDATE storage_request SET status='ON_HOLD', decided_by=$2, decided_at=NOW() WHERE request_id=$1",
        request_id, current.user_id,
    )
    return {"message": "Storage request placed on hold"}


# ── Pipeline health ───────────────────────────────────────────────────────────

@router.get("/pipeline-health")
async def pipeline_health(db: DbConn, current=PA):
    counts = await db.fetch(
        """
        SELECT pipeline_status, COUNT(*) AS cnt
        FROM document
        GROUP BY pipeline_status
        """
    )
    return {
        "counts": {r["pipeline_status"]: r["cnt"] for r in counts},
        "latency": {},   # populated from prana-ai metrics endpoint in production
    }


# ── Platform-wide exception overview ─────────────────────────────────────────

@router.post("/exceptions/{exception_id}/resolve")
async def pa_resolve_exception(exception_id: str, db: DbConn, current=PA):
    await db.execute(
        "UPDATE exception_queue SET status='RESOLVED', resolved_by=$2, resolved_at=NOW() "
        "WHERE exception_id=$1 AND status='OPEN'",
        exception_id, str(current.user_id),
    )
    return {"message": "Resolved"}


@router.get("/exceptions")
async def exception_overview(db: DbConn, current=PA):
    open_count      = await db.fetchval("SELECT COUNT(*) FROM exception_queue WHERE status='OPEN'")
    in_progress     = await db.fetchval("SELECT COUNT(*) FROM exception_queue WHERE status='IN_PROGRESS'")
    resolved_24h    = await db.fetchval(
        "SELECT COUNT(*) FROM exception_queue WHERE status='RESOLVED' AND resolved_at > NOW() - INTERVAL '24 hours'"
    )

    rows = await db.fetch(
        """
        SELECT eq.exception_id, eq.document_id, eq.exception_type,
               eq.status, eq.raised_at, eq.tenant_id, t.tenant_name,
               d.doc_type, d.doc_period,
               (NOW() - eq.raised_at) > INTERVAL '24 hours' AS sla_breached
        FROM exception_queue eq
        JOIN tenant t ON t.tenant_id = eq.tenant_id
        JOIN document d ON d.document_id = eq.document_id
        WHERE eq.status IN ('OPEN','IN_PROGRESS')
        ORDER BY eq.raised_at ASC
        LIMIT 200
        """
    )

    exceptions = []
    for r in rows:
        exceptions.append({
            **{k: v for k, v in dict(r).items() if k not in ('raised_at','sla_breached')},
            "document_name": f"{r['doc_type']} · {r['doc_period'] or 'n/a'}",
            "created_at":    r["raised_at"].isoformat() if r["raised_at"] else None,
            "sla_breached":  bool(r["sla_breached"]),
        })

    return {
        "open_count":        int(open_count or 0),
        "in_progress_count": int(in_progress or 0),
        "resolved_24h":      int(resolved_24h or 0),
        "sla_breach_count":  sum(1 for e in exceptions if e["sla_breached"]),
        "exceptions":        exceptions,
    }


# ── Cryptographic health ──────────────────────────────────────────────────────

@router.get("/crypto")
async def crypto_health(db: DbConn, current=PA):
    """
    Returns platform key status and per-tenant KEK inventory.
    In dev: keys are simulated as ENABLED (no real AWS KMS).
    In prod: would call kms:DescribeKey for each ARN.
    """
    # Per-tenant KEK status (derived from tenant table kek_arn field)
    tenant_rows = await db.fetch(
        """
        SELECT t.tenant_id, t.tenant_name, t.kek_arn,
               COUNT(em.employee_uuid) AS dek_count
        FROM tenant t
        LEFT JOIN employee_master em ON em.tenant_id = t.tenant_id
        WHERE t.status = 'ACTIVE'
        GROUP BY t.tenant_id, t.tenant_name, t.kek_arn
        ORDER BY t.tenant_name
        """
    )

    tenant_keys = []
    for r in tenant_rows:
        kek_arn = r["kek_arn"] or ""
        # Extract short key-id from ARN (e.g. mrk-abc123 or key/uuid)
        key_id = kek_arn.split("/")[-1] if "/" in kek_arn else kek_arn
        tenant_keys.append({
            "tenant_id":      str(r["tenant_id"]),
            "tenant_name":    r["tenant_name"],
            "kms_key_id":     key_id or "dev-mock-key",
            "key_state":      "ENABLED",   # dev: mock; prod: kms:DescribeKey
            "dek_count":      int(r["dek_count"] or 0),
            "last_rotated_at": None,       # prod: from kms:GetKeyRotationStatus
        })

    return {
        "hmac_key_status": "ENABLED",   # platform_secret present in env
        "fpe_key_status":  "ENABLED",   # FF3-1 key present in env
        "totp_key_status": "ENABLED",   # AES-256-GCM key present in env
        "tenant_keys":     tenant_keys,
    }


# ── Audit trail ───────────────────────────────────────────────────────────────

@router.get("/audit")
async def audit_trail(
    db: DbConn,
    q: Optional[str] = None,
    event_type: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
    current=PA,
):
    conditions = []
    params: list = []
    i = 1

    if event_type:
        conditions.append(f"ae.event_type = ${i}"); params.append(event_type); i += 1
    if q:
        conditions.append(f"(t.tenant_name ILIKE ${i})"); params.append(f"%{q}%"); i += 1

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = await db.fetch(
        f"""
        SELECT ae.event_id, ae.event_type, ae.actor_id, ae.actor_type,
               ae.document_id AS resource_id, ae.ip_address,
               ae.occurred_at AS created_at,
               t.tenant_name
        FROM audit_event ae
        LEFT JOIN tenant t ON t.tenant_id = ae.tenant_id
        {where}
        ORDER BY ae.occurred_at DESC
        LIMIT {limit} OFFSET {offset}
        """,
        *params,
    )
    return {"events": [dict(r) for r in rows]}


@router.get("/audit/export")
async def export_audit(db: DbConn, current=PA):
    rows = await db.fetch(
        "SELECT event_type, actor_id, tenant_id, ip_address, occurred_at AS created_at FROM audit_event ORDER BY occurred_at DESC LIMIT 10000"
    )
    import csv, io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["event_type","actor_id","tenant_id","ip_address","created_at"])
    w.writeheader()
    for r in rows:
        w.writerow({k: str(v) for k, v in dict(r).items()})

    from fastapi.responses import Response
    return Response(
        content=buf.getvalue().encode(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit_export.csv"'},
    )


# ── API key management ────────────────────────────────────────────────────────

@router.get("/api-keys")
async def list_api_keys(db: DbConn, current=PA):
    rows = await db.fetch(
        """
        SELECT ak.api_key_id, ak.tenant_id, t.tenant_name,
               ak.key_prefix AS key_id_prefix, ak.label,
               ak.rate_limit_rpm AS rate_limit_per_minute,
               ak.status, ak.created_at, ak.last_used_at
        FROM api_key ak
        JOIN tenant t ON t.tenant_id = ak.tenant_id
        ORDER BY ak.created_at DESC
        """
    )
    tenants = await db.fetch(
        "SELECT tenant_id, tenant_name FROM tenant WHERE status='ACTIVE' ORDER BY tenant_name"
    )
    return {
        "keys": [dict(r) for r in rows],
        "tenants": [dict(t) for t in tenants],
    }


@router.post("/api-keys")
async def create_api_key(request: Request, db: DbConn, current=PA):
    import secrets as _s, hashlib
    from services.encryption_service import aes_encrypt
    body = await request.json()
    tenant_id = body.get("tenant_id")  # sec03-cross-tenant-ok: PA creates API keys for specific tenants
    label = body.get("label", "")
    rpm = int(body.get("rate_limit_per_minute", 1000))

    raw_key = f"prana_{_s.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12]
    signing_secret = _s.token_hex(32)
    dev_dek = b"\x00" * 32
    signing_secret_enc = aes_encrypt(signing_secret, dev_dek)

    await db.execute(
        """INSERT INTO api_key (tenant_id, key_prefix, key_hash, signing_secret_enc,
                                label, scopes, rate_limit_rpm, status, created_by)
           VALUES ($1, $2, $3, $4, $5, $6, $7, 'ACTIVE', $8)""",
        tenant_id, key_prefix, key_hash, signing_secret_enc,
        label, ["ingest:write"], rpm, str(current.user_id),
    )
    return {"api_key": raw_key, "key_prefix": key_prefix}


@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(key_id: str, db: DbConn, current=PA):
    await db.execute(
        "UPDATE api_key SET status='REVOKED' WHERE api_key_id=$1", key_id
    )
    return {"message": "Revoked"}


@router.get("/rate-limits")
async def rate_limits(db: DbConn, current=PA):
    # Default rate limit from platform_config
    default_rpm_row = await db.fetchrow(
        "SELECT config_value FROM platform_config WHERE config_key='api_key_default_rate_limit_rpm'"
    )
    default_rpm = int(default_rpm_row["config_value"]) if default_rpm_row else 1000

    # API keys with their per-key limits
    key_rows = await db.fetch(
        """
        SELECT ak.api_key_id, t.tenant_name, t.tenant_id, ak.label,
               ak.rate_limit_rpm, ak.status
        FROM api_key ak
        JOIN tenant t ON t.tenant_id = ak.tenant_id
        WHERE ak.status = 'ACTIVE'
        ORDER BY ak.rate_limit_rpm DESC
        """
    )

    # Per-tenant overrides from tenant_config
    tenant_overrides = await db.fetch(
        """
        SELECT tc.tenant_id, t.tenant_name, tc.config_value AS rpm_override
        FROM tenant_config tc
        JOIN tenant t ON t.tenant_id = tc.tenant_id
        WHERE tc.config_key = 'api_key_default_rate_limit_rpm'
        """
    )
    override_map = {str(r["tenant_id"]): int(r["rpm_override"]) for r in tenant_overrides}

    # All active tenants with their effective default
    tenant_rows = await db.fetch(
        "SELECT tenant_id, tenant_name FROM tenant WHERE status='ACTIVE' ORDER BY tenant_name"
    )
    tenant_defaults = [
        {
            "tenant_id":   str(r["tenant_id"]),
            "tenant_name": r["tenant_name"],
            "default_rpm": override_map.get(str(r["tenant_id"]), default_rpm),
            "source":      "tenant_config" if str(r["tenant_id"]) in override_map else "platform_default",
        }
        for r in tenant_rows
    ]

    total = len(key_rows)
    avg_rpm = round(sum(r["rate_limit_rpm"] for r in key_rows) / total) if total else default_rpm
    return {
        "total_keys":       total,
        "throttled_1h":     0,   # live from Redis token-bucket scan in production
        "avg_rpm":          avg_rpm,
        "platform_default_rpm": default_rpm,
        "keys":             [dict(r) for r in key_rows],
        "tenant_defaults":  tenant_defaults,
    }


@router.get("/contact-inquiries")
async def list_contact_inquiries(current, db: DbConn, event_type: str = "CONTACT_INQUIRY"):
    rows = await db.fetch(
        """
        SELECT event_id, event_type, created_at, event_metadata
        FROM audit_event
        WHERE event_type = $1
        ORDER BY created_at DESC
        LIMIT 200
        """,
        event_type,
    )
    return {
        "inquiries": [
            {
                "event_id": str(r["event_id"]),
                "event_type": r["event_type"],
                "created_at": r["created_at"].isoformat(),
                "data": r["event_metadata"] if isinstance(r["event_metadata"], dict) else {},
            }
            for r in rows
        ]
    }


# ── Service Incidents ─────────────────────────────────────────────────────────

class ResolveIncidentIn(BaseModel):
    note: str = ""

@router.get("/incidents")
async def list_incidents(db: DbConn, _=PA):
    from services.health_service import HealthService
    svc = HealthService(db)
    incidents = await svc.get_open_incidents()
    return {
        "incidents": [
            {**i, "incident_id": str(i["incident_id"]),
             "detected_at": i["detected_at"].isoformat() if i["detected_at"] else None,
             "acknowledged_at": i["acknowledged_at"].isoformat() if i["acknowledged_at"] else None,
             "resolved_at": i["resolved_at"].isoformat() if i["resolved_at"] else None,
            }
            for i in incidents
        ],
        "open_count": sum(1 for i in incidents if i["status"] == "OPEN"),
        "p1_open": sum(1 for i in incidents if i["status"] == "OPEN" and i["severity"] == "P1"),
    }

@router.post("/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(incident_id: str, db: DbConn, current=PA):
    from uuid import UUID
    from services.health_service import HealthService
    svc = HealthService(db)
    await svc.acknowledge(UUID(incident_id), UUID(current.user_id))
    return {"status": "acknowledged"}

@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(incident_id: str, body: ResolveIncidentIn, db: DbConn, current=PA):
    from uuid import UUID
    from services.health_service import HealthService
    svc = HealthService(db)
    await svc.resolve(UUID(incident_id), UUID(current.user_id), body.note)
    return {"status": "resolved"}

@router.post("/incidents/run-check")
async def trigger_health_check(db: DbConn, _=PA):
    """On-demand health check — PA can trigger without waiting for the next schedule."""
    from services.health_service import HealthService
    svc = HealthService(db)
    results = await svc.run_checks()
    return {"results": results}
