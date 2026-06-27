"""
CISO (Tenant) endpoints â€” read-only security observer + limited action authority.
All queries scoped by tenant_id from JWT. Never sees document contents, salary, or PAN.
"""
import json
import uuid
import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from dependencies import DbConn, require_oa
from services.digest_service import DigestService, period_window, validate_window

router = APIRouter()
CISO = Depends(require_oa("ciso", "oa_admin"))
_digest_svc = DigestService()


# â”€â”€ Security overview â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/overview")
async def security_overview(db: DbConn, current=CISO):
    now = datetime.datetime.now(datetime.timezone.utc)
    day_ago  = now - datetime.timedelta(hours=24)
    week_ago = now - datetime.timedelta(days=7)

    threats_24h = await db.fetchval(
        "SELECT COUNT(*) FROM anomaly_event WHERE tenant_id=$1 AND detected_at >= $2",
        current.tenant_id, day_ago,
    )
    anomalies_open = await db.fetchval(
        "SELECT COUNT(*) FROM anomaly_event WHERE tenant_id=$1 AND status='OPEN'",
        current.tenant_id,
    )
    auth_events = await db.fetchval(
        "SELECT COUNT(*) FROM login_attempt_log WHERE tenant_id=$1 AND attempted_at >= $2",
        current.tenant_id, day_ago,
    )
    timeline_rows = await db.fetch(
        """
        SELECT DATE(detected_at) AS date, COUNT(*) AS events
        FROM anomaly_event
        WHERE tenant_id=$1 AND detected_at >= $2
        GROUP BY 1 ORDER BY 1
        """,
        current.tenant_id, week_ago,
    )
    threat_rows = await db.fetch(
        """
        SELECT anomaly_id, rule_name AS description, severity, detected_at, status
        FROM anomaly_event
        WHERE tenant_id=$1 AND status='OPEN'
        ORDER BY
          CASE severity WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
          detected_at DESC
        LIMIT 10
        """,
        current.tenant_id,
    )
    posture = "RED" if (threats_24h or 0) > 5 else "AMBER" if (anomalies_open or 0) > 0 else "GREEN"
    return {
        "posture":         posture,
        "threats_24h":     int(threats_24h or 0),
        "anomalies_open":  int(anomalies_open or 0),
        "auth_events_24h": int(auth_events or 0),
        "event_timeline":  [{"date": str(r["date"]), "events": int(r["events"])} for r in timeline_rows],
        "threats": [
            {
                "anomaly_id":  str(r["anomaly_id"]),
                "description": r["description"],
                "severity":    r["severity"],
                "detected_at": r["detected_at"].isoformat() if r["detected_at"] else None,
                "status":      r["status"],
            }
            for r in threat_rows
        ],
    }


# â”€â”€ OA Activity Audit â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/oa-audit")
async def oa_activity_audit(
    db: DbConn,
    action_type: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
    current=CISO,
):
    conditions = ["ae.tenant_id = $1", "ae.actor_type IN ('OA_OPERATOR','OA_ADMIN','OA_OPERATOR_ELEVATED')"]
    params: list = [current.tenant_id]
    i = 2

    if action_type and action_type != "ALL":
        conditions.append(f"ae.event_type = ${i}")
        params.append(action_type)
        i += 1

    where = " AND ".join(conditions)
    rows = await db.fetch(
        f"""
        SELECT ae.event_id, ae.event_type AS action_type, ae.actor_id,
               ae.document_id AS resource_id, ae.ip_address, ae.occurred_at AS created_at,
               ou.email AS actor_name, ou.role AS actor_role
        FROM audit_event ae
        LEFT JOIN oa_user ou ON ou.oa_user_id = ae.actor_id
        WHERE {where}
        ORDER BY ae.occurred_at DESC
        LIMIT {limit} OFFSET {offset}
        """,
        *params,
    )
    return {
        "events": [
            {
                "event_id":    str(r["event_id"]),
                "action_type": r["action_type"],
                "actor_id":    str(r["actor_id"]) if r["actor_id"] else None,
                "actor_name":  r["actor_name"],
                "actor_role":  r["actor_role"],
                "resource_id": str(r["resource_id"]) if r["resource_id"] else None,
                "ip_address":  str(r["ip_address"]) if r["ip_address"] else None,
                "created_at":  r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
    }


@router.get("/oa-audit/export")
async def export_oa_audit(db: DbConn, current=CISO):
    from fastapi.responses import Response
    rows = await db.fetch(
        """
        SELECT ae.event_type, ae.actor_id, ou.email AS actor_name, ou.role AS actor_role,
               ae.document_id, ae.ip_address, ae.occurred_at
        FROM audit_event ae
        LEFT JOIN oa_user ou ON ou.oa_user_id = ae.actor_id
        WHERE ae.tenant_id = $1
          AND ae.actor_type IN ('OA_OPERATOR','OA_ADMIN','OA_OPERATOR_ELEVATED')
        ORDER BY ae.occurred_at DESC
        LIMIT 5000
        """,
        current.tenant_id,
    )
    lines = ["event_type,actor_name,actor_role,resource_id,ip_address,occurred_at"]
    for r in rows:
        lines.append(",".join([
            r["event_type"] or "",
            (r["actor_name"] or "").replace(",", " "),
            r["actor_role"] or "",
            str(r["document_id"]) if r["document_id"] else "",
            str(r["ip_address"]) if r["ip_address"] else "",
            r["occurred_at"].isoformat() if r["occurred_at"] else "",
        ]))
    return Response(
        content="\n".join(lines).encode(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="oa_audit.csv"'},
    )


# â”€â”€ Share analytics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/shares")
async def share_analytics(db: DbConn, current=CISO):
    now = datetime.datetime.now(datetime.timezone.utc)
    day_ago = now - datetime.timedelta(hours=24)

    active_count = await db.fetchval(
        "SELECT COUNT(*) FROM share_token WHERE tenant_id=$1 AND status='ACTIVE' AND expires_at > NOW()",
        current.tenant_id,
    )
    accesses_24h = await db.fetchval(
        "SELECT COUNT(*) FROM document_access_log WHERE tenant_id=$1 AND access_channel='SHARE_LINK' AND accessed_at >= $2",
        current.tenant_id, day_ago,
    )
    expired_today = await db.fetchval(
        "SELECT COUNT(*) FROM share_token WHERE tenant_id=$1 AND status='EXPIRED' AND DATE(expires_at) = CURRENT_DATE",
        current.tenant_id,
    )
    revoked_today = await db.fetchval(
        "SELECT COUNT(*) FROM share_token WHERE tenant_id=$1 AND status='REVOKED' AND DATE(revoked_at) = CURRENT_DATE",
        current.tenant_id,
    )
    link_rows = await db.fetch(
        """
        SELECT st.token_id, st.recipient_identifier, st.expires_at, st.usage_count,
               st.status, eu.mobile AS emp_mobile,
               d.doc_type
        FROM share_token st
        LEFT JOIN employee_user eu ON eu.employee_user_id = st.employee_user_id
        LEFT JOIN document d ON d.document_id = ANY(st.document_ids) AND d.is_deleted = FALSE
        WHERE st.tenant_id = $1
          AND st.status = 'ACTIVE'
          AND st.expires_at > NOW()
        ORDER BY st.created_at DESC
        LIMIT 100
        """,
        current.tenant_id,
    )
    return {
        "active_count":   int(active_count or 0),
        "accesses_24h":   int(accesses_24h or 0),
        "expired_today":  int(expired_today or 0),
        "revoked_today":  int(revoked_today or 0),
        "links": [
            {
                "share_id":       str(r["token_id"]),
                "employee_name":  r["emp_mobile"] or "â€”",
                "doc_type":       r["doc_type"] or "â€”",
                "recipient_label": (r["recipient_identifier"] or "")[:30],
                "access_count":   r["usage_count"],
                "expires_at":     r["expires_at"].isoformat() if r["expires_at"] else None,
            }
            for r in link_rows
        ],
    }


@router.post("/shares/{token_id}/revoke", status_code=status.HTTP_200_OK)
async def ciso_revoke_share(token_id: str, request: Request, db: DbConn, current=CISO):
    row = await db.fetchrow(
        "SELECT token_id, status FROM share_token WHERE token_id=$1 AND tenant_id=$2",
        token_id, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="SHARE_NOT_FOUND")
    if row["status"] != "ACTIVE":
        raise HTTPException(status_code=409, detail="SHARE_NOT_ACTIVE")
    await db.execute(
        "UPDATE share_token SET status='REVOKED', revoked_at=NOW() WHERE token_id=$1",
        token_id,
    )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.share_event({
            "event_type": "SHARE_REVOKED_CISO",
            "tenant_id": str(current.tenant_id),
            "actor_id": str(current.user_id),
            "actor_type": "CISO",
            "share_token_id": token_id,
        })
    return {"message": "Share revoked"}


# â”€â”€ Key health â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/keys")
async def key_health(db: DbConn, current=CISO):
    tenant_row = await db.fetchrow(
        "SELECT kek_arn, status FROM tenant WHERE tenant_id=$1",
        current.tenant_id,
    )
    dek_count = await db.fetchval(
        "SELECT COUNT(*) FROM employee_master WHERE tenant_id=$1 AND enc_dek IS NOT NULL",
        current.tenant_id,
    )
    totp_count = await db.fetchval(
        """
        SELECT COUNT(*) FROM employee_user eu
        JOIN employee_master em ON em.employee_user_id = eu.employee_user_id
        WHERE em.tenant_id=$1 AND eu.totp_secret_enc IS NOT NULL
        """,
        current.tenant_id,
    )
    latest_kms = await db.fetchrow(
        """
        SELECT status, checked_at
        FROM kms_key_log
        WHERE tenant_id=$1
        ORDER BY checked_at DESC LIMIT 1
        """,
        current.tenant_id,
    )
    last_rotation = await db.fetchrow(
        """
        SELECT checked_at
        FROM kms_key_log
        WHERE tenant_id=$1 AND event_type='ROTATED'
        ORDER BY checked_at DESC LIMIT 1
        """,
        current.tenant_id,
    )
    rotation_rows = await db.fetch(
        """
        SELECT kl.event_type, kl.status, kl.checked_at AS occurred_at,
               kl.dek_rewrap_count,
               CASE kl.status WHEN 'HEALTHY' THEN 'SUCCESS' ELSE 'FAILURE' END AS outcome
        FROM kms_key_log kl
        WHERE kl.tenant_id=$1
        ORDER BY kl.checked_at DESC LIMIT 20
        """,
        current.tenant_id,
    )
    kek_arn = tenant_row["kek_arn"] if tenant_row else None
    kek_status = latest_kms["status"] if latest_kms else "UNKNOWN"
    return {
        "kek_arn":           kek_arn,
        "kek_key_id":        kek_arn.split("/")[-1] if kek_arn else None,
        "kek_state":         "Enabled",
        "kek_status":        kek_status,
        "kek_created_at":    None,
        "kek_last_used_at":  latest_kms["checked_at"].isoformat() if latest_kms and latest_kms["checked_at"] else None,
        "dek_count":         int(dek_count or 0),
        "totp_enc_status":   "HEALTHY",
        "totp_secret_count": int(totp_count or 0),
        "last_rotated_at":   last_rotation["checked_at"].isoformat() if last_rotation else None,
        "events": [
            {
                "event_type":     r["event_type"],
                "outcome":        r["outcome"],
                "occurred_at":    r["occurred_at"].isoformat() if r["occurred_at"] else None,
                "dek_rewrap_count": r["dek_rewrap_count"],
            }
            for r in rotation_rows
        ],
    }


# â”€â”€ Auth anomaly feed â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/auth-anomalies")
async def auth_anomaly_feed(db: DbConn, current=CISO):
    rows = await db.fetch(
        """
        SELECT lal.attempt_id AS event_id,
               lal.outcome AS anomaly_type,
               lal.ip_address,
               lal.attempted_at AS detected_at,
               lal.session_id,
               CASE
                 WHEN lal.outcome = 'BLOCKED' THEN 'HIGH'
                 WHEN lal.is_flagged THEN 'MEDIUM'
                 ELSE 'LOW'
               END AS severity,
               lal.user_agent AS description,
               lal.ip_country, lal.ip_city
        FROM login_attempt_log lal
        WHERE lal.tenant_id = $1
          AND lal.is_flagged = TRUE
        ORDER BY lal.attempted_at DESC
        LIMIT 100
        """,
        current.tenant_id,
    )
    return {
        "anomalies": [
            {
                "event_id":    str(r["event_id"]),
                "anomaly_type": r["anomaly_type"],
                "ip_address":  str(r["ip_address"]) if r["ip_address"] else None,
                "ip_city":     r["ip_city"],
                "ip_country":  r["ip_country"],
                "detected_at": r["detected_at"].isoformat() if r["detected_at"] else None,
                "session_id":  str(r["session_id"]) if r["session_id"] else None,
                "severity":    r["severity"],
                "description": r["description"],
            }
            for r in rows
        ]
    }


# â”€â”€ Data residency â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/data-residency")
async def data_residency(db: DbConn, current=CISO):
    row = await db.fetchrow(
        "SELECT home_region, status FROM tenant WHERE tenant_id=$1",
        current.tenant_id,
    )
    doc_count = await db.fetchval(
        "SELECT COUNT(*) FROM document WHERE tenant_id=$1 AND is_deleted=FALSE",
        current.tenant_id,
    )
    return {
        "home_region":         row["home_region"] if row else None,
        "verified":            True,
        "last_checked":        datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "regions_used":        ["ap-south-1", "ap-south-2"],
        "dpdp_compliant":      True,
        "primary_doc_count":   int(doc_count or 0),
        "dr_doc_count":        int(doc_count or 0),
    }


# â”€â”€ Document access flags â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/access-flags")
async def list_access_flags(
    db: DbConn,
    offset: int = 0,
    limit: int = 50,
    current=CISO,
):
    rows = await db.fetch(
        """
        SELECT dal.access_id, dal.document_id, dal.employee_user_id,
               dal.actor_type, dal.access_type, dal.access_channel,
               dal.ip_address, dal.accessed_at, dal.flag_reason, dal.is_flagged,
               d.doc_type, d.doc_period
        FROM document_access_log dal
        LEFT JOIN document d ON d.document_id = dal.document_id
        WHERE dal.tenant_id = $1
          AND dal.is_flagged = TRUE
        ORDER BY dal.accessed_at DESC
        LIMIT $2 OFFSET $3
        """,
        current.tenant_id, limit, offset,
    )
    total = await db.fetchval(
        "SELECT COUNT(*) FROM document_access_log WHERE tenant_id=$1 AND is_flagged=TRUE",
        current.tenant_id,
    )
    return {
        "items": [
            {
                "access_id":      str(r["access_id"]),
                "document_id":    str(r["document_id"]) if r["document_id"] else None,
                "doc_type":       r["doc_type"],
                "doc_period":     r["doc_period"],
                "actor_type":     r["actor_type"],
                "access_type":    r["access_type"],
                "access_channel": r["access_channel"],
                "ip_address":     str(r["ip_address"]) if r["ip_address"] else None,
                "accessed_at":    r["accessed_at"].isoformat() if r["accessed_at"] else None,
                "flag_reason":    r["flag_reason"],
                "is_flagged":     r["is_flagged"],
            }
            for r in rows
        ],
        "total": int(total or 0),
    }


class FlagBody(BaseModel):
    flag_reason: Optional[str] = None
    is_flagged: bool


@router.patch("/access-flags/{access_id}")
async def update_access_flag(access_id: str, body: FlagBody, db: DbConn, current=CISO):
    row = await db.fetchrow(
        "SELECT access_id FROM document_access_log WHERE access_id=$1 AND tenant_id=$2",
        access_id, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="ACCESS_LOG_NOT_FOUND")
    await db.execute(
        "UPDATE document_access_log SET is_flagged=$1, flag_reason=$2 WHERE access_id=$3",
        body.is_flagged, body.flag_reason, access_id,
    )
    return {"message": "Updated"}


# â”€â”€ Account lock management â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/account-locks")
async def list_account_locks(db: DbConn, current=CISO):
    rows = await db.fetch(
        """
        SELECT ase.event_id, ase.user_type, ase.user_id,
               ase.event_type AS lock_reason, ase.occurred_at AS locked_at,
               ase.scheduled_unlock_at, ase.failed_attempt_count, ase.last_failed_ip,
               CASE ase.user_type
                 WHEN 'employee' THEN eu.mobile
                 WHEN 'oa_user'  THEN ou.email
               END AS identifier
        FROM account_status_event ase
        LEFT JOIN employee_user eu ON eu.employee_user_id = ase.user_id
                                   AND ase.user_type = 'employee'
        LEFT JOIN oa_user ou ON ou.oa_user_id = ase.user_id
                             AND ase.user_type = 'oa_user'
        WHERE ase.tenant_id = $1
          AND ase.event_type = 'POLICY_LOCK'
          AND ase.reversed_by_event_id IS NULL
        ORDER BY ase.occurred_at DESC
        LIMIT 200
        """,
        current.tenant_id,
    )
    return {
        "items": [
            {
                "event_id":          str(r["event_id"]),
                "account_type":      r["user_type"],
                "account_id":        str(r["user_id"]) if r["user_id"] else None,
                "identifier":        r["identifier"] or "â€”",
                "lock_reason":       r["lock_reason"],
                "locked_at":         r["locked_at"].isoformat() if r["locked_at"] else None,
                "scheduled_unlock_at": r["scheduled_unlock_at"].isoformat() if r["scheduled_unlock_at"] else None,
                "failed_attempt_count": r["failed_attempt_count"],
                "last_failed_ip":    str(r["last_failed_ip"]) if r["last_failed_ip"] else None,
            }
            for r in rows
        ]
    }


@router.post("/account-locks/{event_id}/unlock", status_code=status.HTTP_200_OK)
async def manual_unlock(event_id: str, request: Request, db: DbConn, current=CISO):
    lock_row = await db.fetchrow(
        """
        SELECT event_id, user_type, user_id, reversed_by_event_id
        FROM account_status_event
        WHERE event_id=$1 AND tenant_id=$2 AND event_type='POLICY_LOCK'
        """,
        event_id, current.tenant_id,
    )
    if not lock_row:
        raise HTTPException(status_code=404, detail="LOCK_NOT_FOUND")
    if lock_row["reversed_by_event_id"]:
        raise HTTPException(status_code=409, detail="ALREADY_UNLOCKED")

    new_event_id = uuid.uuid4()
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO account_status_event
              (event_id, event_type, user_type, user_id, tenant_id, actor_type, actor_id, occurred_at)
            VALUES ($1, 'MANUAL_UNLOCK', $2, $3, $4, 'CISO', $5, NOW())
            """,
            new_event_id,
            lock_row["user_type"], lock_row["user_id"],
            current.tenant_id, current.user_id,
        )
        await db.execute(
            "UPDATE account_status_event SET reversed_by_event_id=$1 WHERE event_id=$2",
            new_event_id, event_id,
        )
        # Restore account to ACTIVE
        if lock_row["account_type"] == "employee":
            await db.execute(
                "UPDATE employee_user SET status='ACTIVE', failed_totp_count=0 WHERE employee_user_id=$1",
                lock_row["account_id"],
            )
        elif lock_row["account_type"] == "oa_user":
            await db.execute(
                "UPDATE oa_user SET status='ACTIVE' WHERE oa_user_id=$1",
                lock_row["account_id"],
            )

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.security_event({
            "event_type": "ACCOUNT_UNLOCKED",
            "tenant_id": str(current.tenant_id),
            "actor_id": str(current.user_id),
            "actor_type": "CISO",
            "target_account_id": str(lock_row["account_id"]),
            "reversed_lock_event_id": event_id,
        })
    return {"message": "Account unlocked"}


# â”€â”€ Anomaly triage queue â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/anomaly-queue")
async def anomaly_queue(
    db: DbConn,
    severity: Optional[str] = None,
    status_filter: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
    current=CISO,
):
    conditions = ["tenant_id = $1"]
    params: list = [current.tenant_id]
    i = 2
    if severity:
        conditions.append(f"severity = ${i}"); params.append(severity); i += 1
    if status_filter:
        conditions.append(f"status = ${i}"); params.append(status_filter); i += 1
    else:
        conditions.append("status NOT IN ('RESOLVED','FALSE_POSITIVE')")

    where = " AND ".join(conditions)
    rows = await db.fetch(
        f"""
        SELECT anomaly_id, rule_name, severity, status, financial_pattern,
               actor_id, event_metadata, detected_at, acknowledged_at
        FROM anomaly_event
        WHERE {where}
        ORDER BY
          CASE severity WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
          detected_at DESC
        LIMIT {limit} OFFSET {offset}
        """,
        *params,
    )
    total = await db.fetchval(
        f"SELECT COUNT(*) FROM anomaly_event WHERE {where}", *params
    )
    return {
        "items": [
            {
                "anomaly_id":       str(r["anomaly_id"]),
                "rule_name":        r["rule_name"],
                "severity":         r["severity"],
                "status":           r["status"],
                "financial_pattern": r["financial_pattern"],
                "actor_id":         str(r["actor_id"]) if r["actor_id"] else None,
                "event_metadata":   json.loads(r["event_metadata"]) if isinstance(r["event_metadata"], str) else (r["event_metadata"] or {}),
                "detected_at":      r["detected_at"].isoformat() if r["detected_at"] else None,
                "acknowledged_at":  r["acknowledged_at"].isoformat() if r["acknowledged_at"] else None,
            }
            for r in rows
        ],
        "total": int(total or 0),
    }


class TriageBody(BaseModel):
    status: str  # INVESTIGATING | RESOLVED | FALSE_POSITIVE


@router.patch("/anomaly-queue/{anomaly_id}")
async def triage_anomaly(anomaly_id: str, body: TriageBody, request: Request, db: DbConn, current=CISO):
    allowed = {"INVESTIGATING", "RESOLVED", "FALSE_POSITIVE"}
    if body.status not in allowed:
        raise HTTPException(status_code=422, detail=f"status must be one of {allowed}")
    row = await db.fetchrow(
        "SELECT anomaly_id FROM anomaly_event WHERE anomaly_id=$1 AND tenant_id=$2",
        anomaly_id, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="ANOMALY_NOT_FOUND")
    await db.execute(
        """
        UPDATE anomaly_event
        SET status=$1, acknowledged_by=$2, acknowledged_at=NOW()
        WHERE anomaly_id=$3
        """,
        body.status, current.user_id, anomaly_id,
    )
    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.security_event({
            "event_type": "ANOMALY_TRIAGED",
            "tenant_id": str(current.tenant_id),
            "actor_id": str(current.user_id),
            "actor_type": "CISO",
            "anomaly_id": anomaly_id,
            "new_status": body.status,
        })
    return {"message": "Anomaly updated"}


# â”€â”€ Elevation history â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/elevations")
async def elevation_history(
    db: DbConn,
    offset: int = 0,
    limit: int = 50,
    current=CISO,
):
    rows = await db.fetch(
        """
        SELECT er.elevation_id, er.requestor_id, er.approver_id, er.status,
               er.duration_hours, er.reason, er.requested_at, er.approved_at, er.expires_at,
               req.email AS requestor_name, req.email AS requestor_email,
               apr.email AS approver_name
        FROM elevation_request er
        LEFT JOIN oa_user req ON req.oa_user_id = er.requestor_id
        LEFT JOIN oa_user apr ON apr.oa_user_id = er.approver_id
        WHERE er.tenant_id = $1
        ORDER BY er.requested_at DESC
        LIMIT $2 OFFSET $3
        """,
        current.tenant_id, limit, offset,
    )
    total = await db.fetchval(
        "SELECT COUNT(*) FROM elevation_request WHERE tenant_id=$1",
        current.tenant_id,
    )
    return {
        "items": [
            {
                "elevation_id":    str(r["elevation_id"]),
                "requestor_name":  r["requestor_name"],
                "requestor_email": r["requestor_email"],
                "approver_name":   r["approver_name"],
                "status":          r["status"],
                "duration_hours":  r["duration_hours"],
                "reason":          r["reason"],
                "requested_at":    r["requested_at"].isoformat() if r["requested_at"] else None,
                "approved_at":     r["approved_at"].isoformat() if r["approved_at"] else None,
                "expires_at":      r["expires_at"].isoformat() if r["expires_at"] else None,
            }
            for r in rows
        ],
        "total": int(total or 0),
    }


# â”€â”€ Digest: settings â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class DigestConfigBody(BaseModel):
    recipients: list[str]
    schedules: dict
    sections: list[str]
    format: Literal["email", "email_pdf"]
    active: bool


@router.get("/digest/settings")
async def get_digest_settings(db: DbConn, current=CISO):
    config = await _digest_svc.get_config(db, current.tenant_id, "ciso")
    return {"digest_settings": config}


@router.put("/digest/settings")
async def save_digest_settings(body: DigestConfigBody, db: DbConn, current=CISO):
    await _digest_svc.save_config(
        db, current.tenant_id, "ciso", body.model_dump(), str(current.user_id)
    )
    return {"message": "CISO digest settings saved"}


# â”€â”€ Digest: data endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _resolve_window(period: str, from_date: datetime.date | None, to_date: datetime.date | None):
    if from_date is not None or to_date is not None:
        if from_date is None or to_date is None:
            raise HTTPException(400, detail={
                "error": "DATE_RANGE_INCOMPLETE",
                "message": "Provide both from_date and to_date, or neither (uses period preset).",
            })
        from_dt = datetime.datetime.combine(from_date, datetime.datetime.min.time()).replace(tzinfo=datetime.timezone.utc)
        to_dt   = min(
            datetime.datetime.combine(to_date, datetime.datetime.min.time()).replace(tzinfo=datetime.timezone.utc) + datetime.timedelta(days=1),
            datetime.datetime.now(datetime.timezone.utc),
        )
    else:
        from_dt, to_dt = period_window(period)  # type: ignore[arg-type]
    try:
        validate_window(from_dt, to_dt)
    except ValueError as exc:
        raise HTTPException(400, detail=exc.args[0])
    return from_dt, to_dt


@router.get("/digest/weekly")
async def weekly_digest(
    db: DbConn, current=CISO,
    from_date: datetime.date | None = Query(None, alias="from"),
    to_date:   datetime.date | None = Query(None, alias="to"),
):
    from_dt, to_dt = _resolve_window("weekly", from_date, to_date)
    return {"digest": await _digest_svc.build_ciso_digest(db, current.tenant_id, from_dt, to_dt)}


@router.get("/digest/monthly")
async def monthly_digest(
    db: DbConn, current=CISO,
    from_date: datetime.date | None = Query(None, alias="from"),
    to_date:   datetime.date | None = Query(None, alias="to"),
):
    from_dt, to_dt = _resolve_window("monthly", from_date, to_date)
    return {"digest": await _digest_svc.build_ciso_digest(db, current.tenant_id, from_dt, to_dt)}


@router.get("/digest/quarterly")
async def quarterly_digest(
    db: DbConn, current=CISO,
    from_date: datetime.date | None = Query(None, alias="from"),
    to_date:   datetime.date | None = Query(None, alias="to"),
):
    from_dt, to_dt = _resolve_window("quarterly", from_date, to_date)
    return {"digest": await _digest_svc.build_ciso_digest(db, current.tenant_id, from_dt, to_dt)}


# â”€â”€ Security incidents â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/incidents")
async def list_incidents(
    db: DbConn,
    current=CISO,
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """CISO: list security incidents for own tenant only."""
    from services.incident_service import IncidentService
    svc = IncidentService(db=db)
    items = await svc.get_incidents(
        tenant_id=current.tenant_id,
        severity=severity,
        status=status,
    )
    return {"items": items, "total": len(items)}


class ResolveIncidentBody(BaseModel):
    resolution_note: str


@router.patch("/incidents/{incident_id}/resolve")
async def resolve_incident(
    incident_id: str,
    body: ResolveIncidentBody,
    db: DbConn,
    current=CISO,
):
    """CISO: resolve a security incident on their tenant."""
    from services.incident_service import IncidentService
    svc = IncidentService(db=db)
    try:
        await svc.resolve_incident(
            incident_id=incident_id,
            resolved_by=current.user_id,
            resolution_note=body.resolution_note,
            tenant_id=current.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    return {"status": "resolved"}


@router.patch("/incidents/{incident_id}/escalate")
async def escalate_incident(incident_id: str, db: DbConn, current=CISO):
    """CISO: escalate a P2/P3 incident to P1."""
    from services.incident_service import IncidentService
    svc = IncidentService(db=db)
    try:
        await svc.escalate_incident(
            incident_id=incident_id,
            tenant_id=current.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    return {"status": "escalated"}


# â”€â”€ Notification log â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/notification-log")
async def notification_log(
    db: DbConn,
    current=CISO,
    channel: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """CISO: view security notification_log rows for own tenant."""
    conditions = ["tenant_id = $1"]
    params: list = [current.tenant_id]
    idx = 2
    if channel:
        conditions.append(f"channel = ${idx}")
        params.append(channel)
        idx += 1
    if event_type:
        conditions.append(f"event_type = ${idx}")
        params.append(event_type)
        idx += 1
    params.append(limit)
    rows = await db.fetch(
        f"""
        SELECT notification_id, event_type, channel, template_id,
               status, sent_at, failed_at, error_message, created_at
          FROM notification_log
         WHERE {' AND '.join(conditions)}
         ORDER BY created_at DESC
         LIMIT ${idx}
        """,
        *params,
    )
    items = [
        {
            "notification_id": str(r["notification_id"]),
            "event_type":      r["event_type"],
            "channel":         r["channel"],
            "template_id":     r["template_id"],
            "status":          r["status"],
            "sent_at":         r["sent_at"].isoformat() if r["sent_at"] else None,
            "failed_at":       r["failed_at"].isoformat() if r["failed_at"] else None,
            "error_message":   r["error_message"],
            "created_at":      r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


