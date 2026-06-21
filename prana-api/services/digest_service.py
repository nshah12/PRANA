"""
DigestService — builds digest data for CHRO, CFO, CISO over any date window.
Business logic only: no Temporal imports, no Kafka.
Called by HTTP GET endpoints and DigestWorkflow activities.

Date window rules (enforced here AND at the API layer):
  - Max range: 184 days (~6 months)
  - Max lookback: 730 days (2 years — older data is in cold Iceberg storage)
  - to_dt must be <= today UTC
  - from_dt must be < to_dt, min 1-day window

Privacy contract:
  - Cost figures (CFO) are CFO-configured estimates from tenant_config, never extracted salary
  - No raw ₹ figures, PAN, or NIK in any output
"""
import json
import datetime
from typing import Literal

DigestRole   = Literal["chro", "cfo", "ciso"]
DigestPeriod = Literal["weekly", "monthly", "quarterly"]

MAX_RANGE_DAYS   = 184
MAX_LOOKBACK_DAYS = 730

_CONFIG_KEY: dict[str, str] = {
    "chro": "digest_chro_config",
    "cfo":  "digest_cfo_config",
    "ciso": "digest_ciso_config",
}

_DEFAULT_CONFIG: dict = {
    "recipients": [],
    "schedules": {
        "weekly":    {"enabled": False, "day": "MON", "time": "08:00"},
        "monthly":   {"enabled": False, "day_of_month": 1, "time": "08:00"},
        "quarterly": {"enabled": False, "time": "08:00"},
    },
    "sections": [],
    "format": "email",
    "active": False,
}


def period_window(period: DigestPeriod) -> tuple[datetime.datetime, datetime.datetime]:
    """Return (from_dt, to_dt) UTC for a named period preset."""
    now = datetime.datetime.now(datetime.timezone.utc)
    days = {"weekly": 7, "monthly": 30, "quarterly": 91}[period]
    return now - datetime.timedelta(days=days), now


def validate_window(
    from_dt: datetime.datetime,
    to_dt: datetime.datetime,
) -> None:
    """
    Raise ValueError with a structured dict payload if the window violates bounds.
    Callers catch ValueError and convert to HTTP 400.
    """
    now = datetime.datetime.now(datetime.timezone.utc)

    if to_dt > now + datetime.timedelta(minutes=1):
        raise ValueError({
            "error": "DATE_RANGE_FUTURE",
            "message": "to_date cannot be in the future.",
        })

    if from_dt >= to_dt:
        raise ValueError({
            "error": "DATE_RANGE_INVALID",
            "message": "from_date must be before to_date.",
        })

    delta = (to_dt - from_dt).days
    if delta < 1:
        raise ValueError({
            "error": "DATE_RANGE_TOO_SMALL",
            "message": "Date range must be at least 1 day.",
            "min_days": 1,
        })

    if delta > MAX_RANGE_DAYS:
        raise ValueError({
            "error": "DATE_RANGE_TOO_LARGE",
            "message": f"Date range cannot exceed {MAX_RANGE_DAYS} days (~6 months). "
                       f"Requested: {delta} days.",
            "max_days": MAX_RANGE_DAYS,
            "requested_days": delta,
        })

    lookback = (now - from_dt).days
    if lookback > MAX_LOOKBACK_DAYS:
        raise ValueError({
            "error": "DATE_RANGE_TOO_OLD",
            "message": f"from_date cannot be more than {MAX_LOOKBACK_DAYS} days ago (2 years). "
                       f"Data older than 2 years is in cold storage.",
            "max_lookback_days": MAX_LOOKBACK_DAYS,
        })


class DigestService:

    # ── Config ────────────────────────────────────────────────────────────────

    async def get_config(self, db, tenant_id: str, role: DigestRole) -> dict:
        row = await db.fetchrow(
            "SELECT config_value FROM tenant_config WHERE tenant_id=$1 AND config_key=$2",
            tenant_id, _CONFIG_KEY[role],
        )
        if not row:
            return dict(_DEFAULT_CONFIG)
        val = row["config_value"]
        parsed = json.loads(val) if isinstance(val, str) else val
        return parsed if parsed else dict(_DEFAULT_CONFIG)

    async def save_config(
        self,
        db,
        tenant_id: str,
        role: DigestRole,
        config: dict,
        updated_by: str,
    ) -> None:
        await db.execute(
            """
            INSERT INTO tenant_config (tenant_id, config_key, config_value, updated_by, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (tenant_id, config_key)
            DO UPDATE SET config_value=$3, updated_by=$4, updated_at=NOW()
            """,
            tenant_id, _CONFIG_KEY[role], json.dumps(config), updated_by,
        )

    # ── CHRO digest ───────────────────────────────────────────────────────────

    async def build_chro_digest(
        self,
        db,
        tenant_id: str,
        from_dt: datetime.datetime,
        to_dt: datetime.datetime,
    ) -> dict:
        docs_processed = int(await db.fetchval(
            """SELECT COUNT(*) FROM document
               WHERE tenant_id=$1 AND pushed_at>=$2 AND pushed_at<$3
                 AND pipeline_status='ROUTED' AND is_deleted=FALSE""",
            tenant_id, from_dt, to_dt,
        ) or 0)

        vault_score = await db.fetchval(
            """SELECT ROUND(AVG(vault_completeness)::NUMERIC, 1)
               FROM employee_master WHERE tenant_id=$1 AND status='ACTIVE'""",
            tenant_id,
        )

        exceptions_open = int(await db.fetchval(
            """SELECT COUNT(*) FROM document
               WHERE tenant_id=$1 AND pipeline_status='EXCEPTION' AND is_deleted=FALSE""",
            tenant_id,
        ) or 0)

        alumni_self_served = int(await db.fetchval(
            """SELECT COUNT(*) FROM audit_event
               WHERE tenant_id=$1 AND actor_type='ALUMNI'
                 AND event_type='DOCUMENT_ACCESS'
                 AND occurred_at>=$2 AND occurred_at<$3""",
            tenant_id, from_dt, to_dt,
        ) or 0)

        active_employees = int(await db.fetchval(
            "SELECT COUNT(*) FROM employee_master WHERE tenant_id=$1 AND status='ACTIVE'",
            tenant_id,
        ) or 0)

        type_rows = await db.fetch(
            """SELECT doc_type, COUNT(*) AS cnt FROM document
               WHERE tenant_id=$1 AND pushed_at>=$2 AND pushed_at<$3
                 AND pipeline_status='ROUTED' AND is_deleted=FALSE
               GROUP BY doc_type ORDER BY cnt DESC LIMIT 10""",
            tenant_id, from_dt, to_dt,
        )

        dept_rows = await db.fetch(
            """SELECT department, ROUND(AVG(vault_completeness)::NUMERIC, 1) AS score
               FROM employee_master
               WHERE tenant_id=$1 AND status='ACTIVE' AND department IS NOT NULL
               GROUP BY department ORDER BY score ASC LIMIT 10""",
            tenant_id,
        )

        return {
            "from": from_dt.date().isoformat(),
            "to": (to_dt - datetime.timedelta(seconds=1)).date().isoformat(),
            "active_employees": active_employees,
            "docs_processed": docs_processed,
            "vault_completeness_pct": float(vault_score) if vault_score is not None else 0.0,
            "exceptions_open": exceptions_open,
            "alumni_self_served": alumni_self_served,
            "docs_by_type": [
                {"doc_type": r["doc_type"], "count": int(r["cnt"])} for r in type_rows
            ],
            "vault_by_department": [
                {"department": r["department"], "score": float(r["score"])}
                for r in dept_rows
            ],
        }

    # ── CFO digest ────────────────────────────────────────────────────────────

    async def build_cfo_digest(
        self,
        db,
        tenant_id: str,
        from_dt: datetime.datetime,
        to_dt: datetime.datetime,
    ) -> dict:
        headcount = int(await db.fetchval(
            "SELECT COUNT(*) FROM employee_master WHERE tenant_id=$1 AND status='ACTIVE'",
            tenant_id,
        ) or 0)

        exits = int(await db.fetchval(
            """SELECT COUNT(*) FROM career_event
               WHERE tenant_id=$1 AND event_type='EXITED'
                 AND event_date>=$2 AND event_date<$3""",
            tenant_id, from_dt.date(), to_dt.date(),
        ) or 0)

        joiners = int(await db.fetchval(
            """SELECT COUNT(*) FROM career_event
               WHERE tenant_id=$1 AND event_type='JOINED'
                 AND event_date>=$2 AND event_date<$3""",
            tenant_id, from_dt.date(), to_dt.date(),
        ) or 0)

        anomalies_pending = int(await db.fetchval(
            """SELECT COUNT(*) FROM anomaly_event
               WHERE tenant_id=$1 AND acknowledged_by IS NULL AND status='OPEN'""",
            tenant_id,
        ) or 0)

        avg_ctc_row = await db.fetchrow(
            "SELECT config_value FROM tenant_config WHERE tenant_id=$1 AND config_key='avg_ctc_estimate'",
            tenant_id,
        )
        replacement_row = await db.fetchrow(
            "SELECT config_value FROM tenant_config WHERE tenant_id=$1 AND config_key='replacement_cost_estimate'",
            tenant_id,
        )
        budget_row = await db.fetchrow(
            "SELECT config_value FROM tenant_config WHERE tenant_id=$1 AND config_key='headcount_budget'",
            tenant_id,
        )

        compliance_rows = await db.fetch(
            """SELECT doc_type, COUNT(DISTINCT employee_user_id) AS covered
               FROM document
               WHERE tenant_id=$1 AND doc_type=ANY($2)
                 AND pipeline_status='ROUTED' AND is_deleted=FALSE
               GROUP BY doc_type""",
            tenant_id, ["SALARY_SLIP", "FORM_16", "OFFER_LETTER", "PF_STATEMENT"],
        )

        dept_rows = await db.fetch(
            """SELECT department, COUNT(*) AS cnt
               FROM employee_master
               WHERE tenant_id=$1 AND status='ACTIVE' AND department IS NOT NULL
               GROUP BY department ORDER BY cnt DESC LIMIT 8""",
            tenant_id,
        )

        return {
            "from": from_dt.date().isoformat(),
            "to": (to_dt - datetime.timedelta(seconds=1)).date().isoformat(),
            "headcount": headcount,
            "headcount_budget": int(budget_row["config_value"]) if budget_row else None,
            "exits": exits,
            "joiners": joiners,
            "anomalies_pending": anomalies_pending,
            "cost_indicators": {
                "avg_ctc_estimate": float(avg_ctc_row["config_value"]) if avg_ctc_row else None,
                "replacement_cost_estimate": float(replacement_row["config_value"]) if replacement_row else None,
                "note": "CFO-configured estimates — not extracted salary figures",
            },
            "compliance_by_doc_type": {r["doc_type"]: int(r["covered"]) for r in compliance_rows},
            "headcount_by_department": [
                {"department": r["department"], "count": int(r["cnt"])} for r in dept_rows
            ],
        }

    # ── CISO digest ───────────────────────────────────────────────────────────

    async def build_ciso_digest(
        self,
        db,
        tenant_id: str,
        from_dt: datetime.datetime,
        to_dt: datetime.datetime,
    ) -> dict:
        total_accesses = int(await db.fetchval(
            """SELECT COUNT(*) FROM document_access_log
               WHERE tenant_id=$1 AND accessed_at>=$2 AND accessed_at<$3""",
            tenant_id, from_dt, to_dt,
        ) or 0)

        anomalies_total = int(await db.fetchval(
            """SELECT COUNT(*) FROM anomaly_event
               WHERE tenant_id=$1 AND detected_at>=$2 AND detected_at<$3""",
            tenant_id, from_dt, to_dt,
        ) or 0)

        anomalies_open = int(await db.fetchval(
            """SELECT COUNT(*) FROM anomaly_event
               WHERE tenant_id=$1 AND status='OPEN'
                 AND detected_at>=$2 AND detected_at<$3""",
            tenant_id, from_dt, to_dt,
        ) or 0)

        force_logouts = int(await db.fetchval(
            """SELECT COUNT(*) FROM audit_event
               WHERE tenant_id=$1 AND event_type='SESSION_REVOKED'
                 AND occurred_at>=$2 AND occurred_at<$3""",
            tenant_id, from_dt, to_dt,
        ) or 0)

        share_tokens = int(await db.fetchval(
            """SELECT COUNT(*) FROM document_access_log
               WHERE tenant_id=$1 AND access_channel='SHARE_LINK'
                 AND accessed_at>=$2 AND accessed_at<$3""",
            tenant_id, from_dt, to_dt,
        ) or 0)

        channel_rows = await db.fetch(
            """SELECT access_channel, COUNT(*) AS cnt
               FROM document_access_log
               WHERE tenant_id=$1 AND accessed_at>=$2 AND accessed_at<$3
               GROUP BY access_channel ORDER BY cnt DESC""",
            tenant_id, from_dt, to_dt,
        )

        incident_rows = await db.fetch(
            """SELECT anomaly_id, rule_name, severity, detected_at, status, acknowledged_at
               FROM anomaly_event
               WHERE tenant_id=$1 AND detected_at>=$2 AND detected_at<$3
               ORDER BY detected_at DESC LIMIT 10""",
            tenant_id, from_dt, to_dt,
        )

        return {
            "from": from_dt.date().isoformat(),
            "to": (to_dt - datetime.timedelta(seconds=1)).date().isoformat(),
            "total_accesses": total_accesses,
            "anomalies_total": anomalies_total,
            "anomalies_open": anomalies_open,
            "force_logouts": force_logouts,
            "share_tokens_period": share_tokens,
            "by_channel": [
                {"channel": r["access_channel"], "count": int(r["cnt"])}
                for r in channel_rows
            ],
            "incidents": [
                {
                    "anomaly_id": str(r["anomaly_id"]),
                    "rule_name": r["rule_name"],
                    "severity": r["severity"],
                    "detected_at": r["detected_at"].isoformat() if r["detected_at"] else None,
                    "status": r["status"],
                    "resolved": r["acknowledged_at"] is not None,
                }
                for r in incident_rows
            ],
        }
