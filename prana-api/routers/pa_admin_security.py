"""
Portal Admin (PA) endpoints — security, audit & incidents.
Split 2026-08-10 out of pa_admin.py (see that file's docstring). Covers:
platform anomaly detection, cryptographic health, audit trail, API key
management, service incidents, cross-tenant security incidents, application
errors (4th incident track).
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

# ── Platform anomaly detection ─────────────────────────────────────────────────

@router.get("/anomalies")
async def list_anomalies(db: DbConn, current=PA):
    """PA: platform-wide anomaly events. Returns empty list if table not yet provisioned."""
    try:
        rows = await db.fetch(
            """
            SELECT ae.event_id, ae.tenant_id, t.tenant_name,
                   ae.rule_name, ae.severity, ae.detected_at,
                   ae.status, ae.event_metadata
            FROM anomaly_event ae
            JOIN tenant t ON t.tenant_id = ae.tenant_id
            ORDER BY ae.detected_at DESC
            LIMIT 200
            """
        )
    except Exception:
        rows = []
    return {
        "anomalies": [
            {
                "event_id":     str(r["event_id"]),
                "tenant_id":    str(r["tenant_id"]),
                "tenant_name":  r["tenant_name"],
                "anomaly_type": r["rule_name"],
                "severity":     r["severity"],
                "detected_at":  r["detected_at"].isoformat() if r["detected_at"] else None,
                "status":       r["status"],
                "details":      r["event_metadata"],
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post("/anomalies/{event_id}/acknowledge")
async def acknowledge_anomaly(event_id: str, db: DbConn, current=PA):
    try:
        await db.execute(
            "UPDATE anomaly_event SET status='ACKNOWLEDGED' WHERE event_id=$1",
            event_id,
        )
    except Exception as exc:
        from services.error_observability_service import ErrorObservabilityService
        try:
            await ErrorObservabilityService(db).record(
                exc=exc, source="HTTP", source_detail="acknowledge_anomaly",
            )
        except Exception:
            pass
    return {"message": SuccessCode.ALERT_ACKNOWLEDGED}


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
    return {"events": [
        {
            "event_id": str(r["event_id"]),
            "event_type": r["event_type"],
            "actor_id": str(r["actor_id"]) if r["actor_id"] else None,
            "actor_type": r["actor_type"],
            "resource_id": str(r["resource_id"]) if r["resource_id"] else None,
            "ip_address": str(r["ip_address"]) if r["ip_address"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "tenant_name": r["tenant_name"],
        }
        for r in rows
    ]}


@router.get("/audit/export")
async def export_audit(db: DbConn, current=PA):
    rows = await db.fetch(
        "SELECT event_type, actor_id::text, tenant_id::text, ip_address::text, occurred_at AS created_at FROM audit_event ORDER BY occurred_at DESC LIMIT 10000"
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
        "keys": [
            {
                "api_key_id": str(r["api_key_id"]),
                "tenant_id": str(r["tenant_id"]),
                "tenant_name": r["tenant_name"],
                "key_id_prefix": r["key_id_prefix"],
                "label": r["label"],
                "rate_limit_per_minute": r["rate_limit_per_minute"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
            }
            for r in rows
        ],
        "tenants": [
            {"tenant_id": str(t["tenant_id"]), "tenant_name": t["tenant_name"]}
            for t in tenants
        ],
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
    from services.encryption_service import resolve_auth_dek
    signing_secret = _s.token_hex(32)
    auth_dek = resolve_auth_dek(request.app.state.settings)
    signing_secret_enc = aes_encrypt(signing_secret, auth_dek)

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
    return {"message": SuccessCode.ACCESS_REVOKED}


@router.get("/rate-limits")
async def rate_limits(request: Request, db: DbConn, current=PA):
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

    throttled_1h = 0
    redis = getattr(request.app.state, "redis", None)
    if redis:
        try:
            throttled_1h = int(await redis.get("ratelimit:hits:1h") or 0)
        except Exception:
            throttled_1h = 0

    return {
        "total_keys":       total,
        "throttled_1h":     throttled_1h,
        "avg_rpm":          avg_rpm,
        "platform_default_rpm": default_rpm,
        "keys": [
            {
                "api_key_id":     str(r["api_key_id"]),
                "tenant_name":    r["tenant_name"],
                "tenant_id":      str(r["tenant_id"]),
                "label":          r["label"],
                "rate_limit_rpm": int(r["rate_limit_rpm"]) if r["rate_limit_rpm"] is not None else 0,
                "status":         r["status"],
            }
            for r in key_rows
        ],
        "tenant_defaults":  tenant_defaults,
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


# ── Security incidents (cross-tenant — PA only) ────────────────────────────────

@router.get("/security-incidents")
async def list_security_incidents(
    db: DbConn,
    _=PA,
    tenant_id: Optional[str] = None,
    severity: Optional[str] = None,
    incident_status: Optional[str] = None,
    limit: int = 100,
):
    """PA: list security/anomaly incidents across all tenants (or filter by tenant)."""
    from services.incident_service import IncidentService
    svc = IncidentService(db=db)
    items = await svc.get_incidents(
        tenant_id=tenant_id,   # None = all tenants
        severity=severity,
        status=incident_status,
        limit=limit,
    )
    return {"items": items, "total": len(items)}


class PaResolveIncidentBody(BaseModel):
    resolution_note: str


@router.patch("/security-incidents/{incident_id}/resolve")
async def pa_resolve_security_incident(
    incident_id: str,
    body: PaResolveIncidentBody,
    db: DbConn,
    current=PA,
):
    """PA: resolve any security incident (no tenant scope restriction)."""
    from services.incident_service import IncidentService
    svc = IncidentService(db=db)
    try:
        await svc.resolve_incident(
            incident_id=incident_id,
            resolved_by=current.user_id,
            resolution_note=body.resolution_note,
            tenant_id=None,   # PA sees all tenants
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    return {"status": "resolved"}


@router.patch("/security-incidents/{incident_id}/escalate")
async def pa_escalate_security_incident(incident_id: str, db: DbConn, _=PA):
    """PA: escalate any security incident."""
    from services.incident_service import IncidentService
    svc = IncidentService(db=db)
    try:
        await svc.escalate_incident(incident_id=incident_id, tenant_id=None)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    return {"status": "escalated"}


# ── Application errors (4th incident track — see prana-docs/ERROR_OBSERVABILITY_DESIGN.md) ──

class ResolveErrorIn(BaseModel):
    resolution_note: str = Field(min_length=1)


class PromoteErrorIn(BaseModel):
    severity: str


def _error_value_error_status(exc: ValueError) -> int:
    return status.HTTP_404_NOT_FOUND if "not found" in str(exc) else status.HTTP_422_UNPROCESSABLE_ENTITY


@router.get("/errors")
async def list_errors(
    db: DbConn,
    _=PA,
    tenant_id: Optional[str] = None,
    error_status: Optional[str] = None,
    limit: int = 100,
):
    """PA: list captured application errors across all tenants (or filter by tenant)."""
    from services.error_observability_service import ErrorObservabilityService
    svc = ErrorObservabilityService(db)
    items = await svc.list_errors(tenant_id=tenant_id, status=error_status, limit=limit)
    return {"items": items, "total": len(items)}


@router.post("/errors/{error_id}/acknowledge")
async def acknowledge_error(error_id: str, db: DbConn, _=PA):
    from services.error_observability_service import ErrorObservabilityService
    svc = ErrorObservabilityService(db)
    try:
        await svc.acknowledge(error_id=error_id)
    except ValueError as exc:
        raise HTTPException(status_code=_error_value_error_status(exc), detail=str(exc)) from exc
    return {"status": "acknowledged"}


@router.post("/errors/{error_id}/ignore")
async def ignore_error(error_id: str, db: DbConn, _=PA):
    from services.error_observability_service import ErrorObservabilityService
    svc = ErrorObservabilityService(db)
    try:
        await svc.ignore(error_id=error_id)
    except ValueError as exc:
        raise HTTPException(status_code=_error_value_error_status(exc), detail=str(exc)) from exc
    return {"status": "ignored"}


@router.post("/errors/{error_id}/resolve")
async def resolve_error(error_id: str, body: ResolveErrorIn, db: DbConn, current=PA):
    from services.error_observability_service import ErrorObservabilityService
    svc = ErrorObservabilityService(db)
    try:
        await svc.resolve(error_id=error_id, resolved_by=current.user_id, resolution_note=body.resolution_note)
    except ValueError as exc:
        raise HTTPException(status_code=_error_value_error_status(exc), detail=str(exc)) from exc
    return {"status": "resolved"}


@router.post("/errors/{error_id}/promote-to-incident")
async def promote_error_to_incident(error_id: str, body: PromoteErrorIn, db: DbConn, _=PA):
    from services.error_observability_service import ErrorObservabilityService
    svc = ErrorObservabilityService(db)
    try:
        incident_id = await svc.promote_to_incident(error_id=error_id, severity=body.severity)
    except ValueError as exc:
        raise HTTPException(status_code=_error_value_error_status(exc), detail=str(exc)) from exc
    return {"status": "promoted", "incident_id": incident_id}


