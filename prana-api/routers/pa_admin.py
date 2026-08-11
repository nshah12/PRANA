"""
Portal Admin (PA) endpoints — platform overview & health.
PA has zero SELECT on document rows or employee PII — only aggregates and tenant metadata.
All routes require @prana.in JWT (enforced in auth_pa.py at login time).

Split 2026-08-10 from a single 1800-line pa_admin.py into 4 domain files
(this one, pa_admin_accounts.py, pa_admin_security.py, pa_admin_comms.py) —
all still mounted at the /admin prefix in main.py. Covers: meta-dashboard,
secops overview, tenant management stubs.
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

# ── Meta dashboard ────────────────────────────────────────────────────────────

@router.get("/meta-dashboard")
async def meta_dashboard(request: Request, db: DbConn, current=PA):
    active_tenants  = await db.fetchval("SELECT COUNT(*) FROM tenant WHERE status='ACTIVE'")
    total_employees = await db.fetchval("SELECT COUNT(*) FROM employee_master WHERE status='ACTIVE'")
    open_exceptions = await db.fetchval("SELECT COUNT(*) FROM exception_queue WHERE status='OPEN'")

    pending_approval_count = await db.fetchval(
        "SELECT COUNT(*) FROM tenant WHERE status IN ('PENDING','PENDING_VERIFICATION')"
    )

    # SLA breach: open exceptions older than each tenant's effective exception_sla_p95_hours
    # (tenant_config override falls back to platform_config — never hardcoded).
    sla_breach_count = await db.fetchval(
        """
        SELECT COUNT(*) FROM exception_queue eq
        WHERE eq.status = 'OPEN'
          AND eq.raised_at < NOW() - make_interval(hours => COALESCE(
                (SELECT config_value::int FROM tenant_config tc
                 WHERE tc.tenant_id = eq.tenant_id AND tc.config_key='exception_sla_p95_hours'),
                (SELECT config_value::int FROM platform_config
                 WHERE config_key='exception_sla_p95_hours'),
                24
              ))
        """
    )

    failed_logins_24h = await db.fetchval(
        """
        SELECT COUNT(*) FROM login_attempt_log
        WHERE outcome IN ('FAILED','BLOCKED')
          AND attempted_at >= NOW() - INTERVAL '24 hours'
        """
    )
    quarantined_files = await db.fetchval(
        "SELECT COUNT(*) FROM document WHERE pipeline_status = 'QUARANTINED'"
    )
    csam_events = await db.fetchval(
        "SELECT COUNT(*) FROM document WHERE csam_detected = TRUE"
    )
    rate_limit_hits_24h = 0
    redis = getattr(request.app.state, "redis", None)
    if redis:
        try:
            rate_limit_hits_24h = int(await redis.get("ratelimit:hits:24h") or 0)
        except Exception:
            rate_limit_hits_24h = 0

    top_tenants = await db.fetch(
        """
        SELECT t.tenant_id, t.tenant_name, t.status,
               COUNT(d.document_id) FILTER (
                 WHERE d.pushed_at >= CURRENT_DATE
               ) AS docs_today,
               COUNT(eq.exception_id) FILTER (WHERE eq.status = 'OPEN') AS open_exceptions
        FROM tenant t
        LEFT JOIN document d ON d.tenant_id = t.tenant_id AND d.is_deleted = FALSE
        LEFT JOIN exception_queue eq ON eq.tenant_id = t.tenant_id
        GROUP BY t.tenant_id, t.tenant_name, t.status
        ORDER BY docs_today DESC
        LIMIT 10
        """
    )

    stage_counts = await db.fetch(
        """
        SELECT pipeline_status, COUNT(*) AS cnt
        FROM document
        WHERE pipeline_status NOT IN ('ROUTED','EXCEPTION','QUARANTINED')
          AND is_deleted = FALSE
        GROUP BY pipeline_status
        """
    )

    extraction_calls_today = await db.fetchval(
        "SELECT COUNT(*) FROM llm_usage_log WHERE occurred_at >= CURRENT_DATE"
    )
    tokens_consumed_today = await db.fetchval(
        "SELECT COALESCE(SUM(total_tokens), 0) FROM llm_usage_log WHERE occurred_at >= CURRENT_DATE"
    )
    avg_confidence = await db.fetchval(
        "SELECT AVG(resolution_confidence) FROM document WHERE pushed_at >= CURRENT_DATE"
    )
    cost_rate_row = await db.fetchval(
        "SELECT config_value FROM platform_config WHERE config_key='llm_cost_per_1k_tokens_inr'"
    )
    cost_rate = float(cost_rate_row) if cost_rate_row else 0.0
    estimated_cost_inr = round((int(tokens_consumed_today or 0) / 1000) * cost_rate, 2)

    # Recent tenant status changes (account_status_event covers TOTP_LOCKOUT + ADMIN_DISABLED events)
    # For tenant-level activity use tenant table directly (created_at ordering)
    recent_tenants = await db.fetch(
        """
        SELECT tenant_name, status, created_at
        FROM tenant
        ORDER BY created_at DESC LIMIT 10
        """
    )

    # Storage: try real S3/MinIO first; fall back to DB-estimated size (avg 200 KB/doc)
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
        if total_bytes > 0:
            if total_bytes < 1024 * 1024:
                storage_used_label = f"{total_bytes // 1024} KB"
            elif total_bytes < 1024 ** 3:
                storage_used_label = f"{total_bytes / (1024**2):.1f} MB"
            else:
                storage_used_label = f"{total_bytes / (1024**3):.2f} GB"
    except Exception as exc:
        from services.error_observability_service import ErrorObservabilityService
        try:
            await ErrorObservabilityService(db).record(
                exc=exc, source="HTTP", source_detail="platform_summary:s3_storage_listing",
            )
        except Exception:
            pass
    if storage_used_label == "—":
        # Estimate from document count: average 200 KB per document
        doc_count = await db.fetchval("SELECT COUNT(*) FROM document WHERE is_deleted=FALSE")
        if doc_count:
            est_bytes = int(doc_count) * 200 * 1024
            if est_bytes < 1024 ** 3:
                storage_used_label = f"~{est_bytes / (1024**2):.0f} MB (est.)"
            else:
                storage_used_label = f"~{est_bytes / (1024**3):.2f} GB (est.)"

    return {
        "active_tenants":         int(active_tenants or 0),
        "total_employees":        int(total_employees or 0),
        "storage_used_label":     storage_used_label,
        "open_exceptions":        int(open_exceptions or 0),
        "pending_approval_count": int(pending_approval_count or 0),
        "sla_breach_count":       int(sla_breach_count or 0),
        "security_alerts": {
            "failed_logins_24h":   int(failed_logins_24h or 0),
            "quarantined_files":   int(quarantined_files or 0),
            "csam_events":         int(csam_events or 0),
            "rate_limit_hits_24h": rate_limit_hits_24h,
        },
        "top_tenants": [
            {
                "tenant_id":       str(r["tenant_id"]),
                "tenant_name":     r["tenant_name"],
                "status":          r["status"],
                "docs_today":      int(r["docs_today"] or 0),
                "open_exceptions": int(r["open_exceptions"] or 0),
            }
            for r in top_tenants
        ],
        "llm_usage_today": {
            "extraction_calls":  int(extraction_calls_today or 0),
            "tokens_consumed":   int(tokens_consumed_today or 0),
            "avg_confidence":    round(float(avg_confidence), 2) if avg_confidence is not None else None,
            "estimated_cost_inr": estimated_cost_inr,
        },
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


# ── SecOps overview ───────────────────────────────────────────────────────────

def _secops_posture(threats_24h: int, anomalies_open: int) -> str:
    if threats_24h > 5:
        return "RED"
    if anomalies_open > 0:
        return "AMBER"
    return "GREEN"


def _secops_alert_severity(severity: str) -> str:
    return "HIGH" if severity in ("P0", "P1") else "LOW"


@router.get("/secops")
async def secops_overview(db: DbConn, current=PA):
    now = datetime.datetime.now(datetime.timezone.utc)
    hour_ago = now - datetime.timedelta(hours=1)
    day_ago  = now - datetime.timedelta(hours=24)

    active_threats = await db.fetchval(
        "SELECT COUNT(*) FROM anomaly_event WHERE status IN ('OPEN','INVESTIGATING')"
    )
    locked_accounts = await db.fetchval(
        """
        SELECT COUNT(*) FROM account_status_event
        WHERE reversed_by_event_id IS NULL
          AND event_type IN ('ADMIN_DISABLED','TOTP_LOCKOUT','PA_SUSPENDED','PASSWORD_LOCKOUT','POLICY_LOCK')
        """
    )
    auth_events_1h = await db.fetchval(
        "SELECT COUNT(*) FROM login_attempt_log WHERE attempted_at >= $1",
        hour_ago,
    )
    # ip_country is populated by async Phase-2 IP-intelligence enrichment, gated by
    # enrichment_status — recent logins within the enrichment lag window won't be
    # counted yet, which is acceptable for a dashboard stat.
    foreign_ips_24h = await db.fetchval(
        """
        SELECT COUNT(*) FROM login_attempt_log
        WHERE attempted_at >= $1
          AND enrichment_status = 'DONE'
          AND ip_country IS NOT NULL
          AND ip_country != 'IN'
        """,
        day_ago,
    )

    tenant_rows = await db.fetch(
        """
        SELECT
          t.tenant_id, t.tenant_name,
          COALESCE(a24.threats_24h, 0)      AS threats_24h,
          COALESCE(aopen.anomalies_open, 0) AS anomalies_open,
          COALESCE(l.locked_count, 0)       AS locked_count,
          amax.last_threat_at
        FROM tenant t
        LEFT JOIN (
          SELECT tenant_id, COUNT(*) AS threats_24h
          FROM anomaly_event WHERE detected_at >= $1
          GROUP BY tenant_id
        ) a24 ON a24.tenant_id = t.tenant_id
        LEFT JOIN (
          SELECT tenant_id, COUNT(*) AS anomalies_open
          FROM anomaly_event WHERE status = 'OPEN'
          GROUP BY tenant_id
        ) aopen ON aopen.tenant_id = t.tenant_id
        LEFT JOIN (
          SELECT tenant_id, COUNT(*) AS locked_count
          FROM account_status_event
          WHERE reversed_by_event_id IS NULL
            AND event_type IN ('ADMIN_DISABLED','TOTP_LOCKOUT','PA_SUSPENDED','PASSWORD_LOCKOUT','POLICY_LOCK')
          GROUP BY tenant_id
        ) l ON l.tenant_id = t.tenant_id
        LEFT JOIN (
          SELECT tenant_id, MAX(detected_at) AS last_threat_at
          FROM anomaly_event
          GROUP BY tenant_id
        ) amax ON amax.tenant_id = t.tenant_id
        WHERE t.status = 'ACTIVE'
        ORDER BY anomalies_open DESC, threats_24h DESC, t.tenant_name
        LIMIT 50
        """,
        day_ago,
    )

    alert_rows = await db.fetch(
        """
        SELECT ae.anomaly_id, ae.rule_name, ae.severity, ae.detected_at, t.tenant_name
        FROM anomaly_event ae
        JOIN tenant t ON t.tenant_id = ae.tenant_id
        WHERE ae.status IN ('OPEN','INVESTIGATING')
        ORDER BY
          CASE ae.severity WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
          ae.detected_at DESC
        LIMIT 20
        """
    )

    return {
        "active_threats":  int(active_threats or 0),
        "locked_accounts": int(locked_accounts or 0),
        "auth_events_1h":  int(auth_events_1h or 0),
        "foreign_ips_24h": int(foreign_ips_24h or 0),
        "tenants": [
            {
                "tenant_id":      str(r["tenant_id"]),
                "tenant_name":    r["tenant_name"],
                "posture":        _secops_posture(int(r["threats_24h"]), int(r["anomalies_open"])),
                "locked_count":   int(r["locked_count"]),
                "anomaly_count":  int(r["anomalies_open"]),
                "last_threat_at": r["last_threat_at"].isoformat() if r["last_threat_at"] else None,
            }
            for r in tenant_rows
        ],
        "alerts": [
            {
                "severity":    _secops_alert_severity(r["severity"]),
                "description": r["rule_name"],
                "tenant_name": r["tenant_name"],
                "occurred_at": r["detected_at"].isoformat() if r["detected_at"] else None,
            }
            for r in alert_rows
        ],
    }


# ── Tenant management ─────────────────────────────────────────────────────────
# NOTE: list_tenants (GET /tenants), activate_tenant (POST /tenants/{id}/activate),
# and suspend_tenant (POST /tenants/{id}/suspend) are intentionally NOT defined
# here — they live in routers/tenants.py, which has the correct account_status_event
# + Kafka audit trail. Duplicate dead-code routes here were previously shadowed by
# tenants.py's registration and never actually served traffic; they're removed
# rather than re-added to avoid silently regressing to the un-audited behavior.

@router.post("/tenants/{tenant_id}/reject")
async def reject_tenant(tenant_id: str, db: DbConn, current=PA):
    await db.execute(
        "UPDATE tenant SET status='REJECTED' WHERE tenant_id=$1 "
        "AND status IN ('PENDING','PENDING_VERIFICATION','VERIFICATION_FAILED')",
        tenant_id,
    )
    return {"message": SuccessCode.TENANT_REJECTED}


@router.post("/tenants/{tenant_id}/retry-verification")
async def retry_verification(tenant_id: str, request: Request, db: DbConn, current=PA):
    """Re-run domain verification for a tenant stuck in VERIFICATION_FAILED —
    republishes DOMAIN_VERIFICATION_REQUESTED with a fresh workflow_id
    (WorkflowConsumer starts a new DomainVerificationWorkflow; the original
    run's ID stays reserved as a completed/failed history entry in Temporal).
    """
    row = await db.fetchrow("SELECT status, domain FROM tenant WHERE tenant_id=$1", tenant_id)
    if not row or row["status"] != "VERIFICATION_FAILED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PranaError.NOT_VERIFICATION_FAILED)

    await db.execute("UPDATE tenant SET status='PENDING' WHERE tenant_id=$1", tenant_id)

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        retry_id = str(uuid.uuid4())[:8]
        await kafka.domain_verification_requested({
            "event_type": "DOMAIN_VERIFICATION_REQUESTED",
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tenant_id": tenant_id,
            "domain": row["domain"],
            "workflow_id": f"domain-verify-{tenant_id}-retry-{retry_id}",
        })
    return success_response(SuccessCode.VERIFICATION_RETRIED)


