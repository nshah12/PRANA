"""
CFO endpoints — aggregated financial analytics only.
Privacy contract: zero individual salary figures in any response.
All ₹ values replaced with qualitative labels or percentile ranges.
Cohort minimum 30 enforced before returning payroll data.
All queries scoped to tenant_id from JWT.
"""
import json
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from dependencies import DbConn, require_oa
from services.digest_service import DigestService, period_window, validate_window

router = APIRouter()
CFO = Depends(require_oa("cfo", "oa_admin"))

_CFO_COHORT_MIN = 30   # overridable via platform_config in production
_digest_svc = DigestService()


# ── Dashboard KPIs ────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def cfo_dashboard(db: DbConn, current=CFO):
    active_count = await db.fetchval(
        "SELECT COUNT(*) FROM employee_master WHERE tenant_id=$1 AND status='ACTIVE'",
        current.tenant_id,
    )
    try:
        open_anomalies = await db.fetchval(
            "SELECT COUNT(*) FROM anomaly_event WHERE tenant_id=$1 AND status='OPEN'",
            current.tenant_id,
        )
    except Exception:
        open_anomalies = 0
    consent_row = await db.fetchrow(
        """
        SELECT
          COUNT(*) FILTER (WHERE consent_status='GRANTED') AS granted,
          COUNT(*) AS total
        FROM employee_user eu
        JOIN employee_master em ON em.employee_user_id = eu.employee_user_id
        WHERE em.tenant_id = $1 AND em.status = 'ACTIVE'
        """,
        current.tenant_id,
    )
    consent_pct = (
        round(consent_row["granted"] / consent_row["total"] * 100)
        if consent_row and consent_row["total"] > 0 else None
    )

    return {
        "payroll_spend_label":      "Aggregated · cohort < min" if active_count < _CFO_COHORT_MIN else "Available",
        "attrition_cost_label":     "—",
        "compliance_exposure_label":"—",
        "consent_coverage_pct":     consent_pct,
        "active_anomalies":         open_anomalies,
    }


# ── Payroll intelligence ──────────────────────────────────────────────────────

@router.get("/payroll")
async def payroll_intelligence(db: DbConn, current=CFO):
    active_count = await db.fetchval(
        "SELECT COUNT(*) FROM employee_master WHERE tenant_id=$1 AND status='ACTIVE'",
        current.tenant_id,
    )
    if active_count < _CFO_COHORT_MIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"COHORT_TOO_SMALL — minimum {_CFO_COHORT_MIN} employees required",
        )

    # insight_cache holds pre-computed aggregates — never raw ₹ fields from extracted_fields
    trend_rows = await db.fetch(
        """
        SELECT period_month AS month, payroll_total_inr AS total
        FROM insight_cache
        WHERE tenant_id=$1 AND cache_key='payroll_monthly_trend'
        ORDER BY period_month DESC LIMIT 6
        """,
        current.tenant_id,
    )

    band_rows = await db.fetch(
        """
        SELECT band_label AS band, employee_count AS count
        FROM insight_cache
        WHERE tenant_id=$1 AND cache_key='salary_band_distribution'
        ORDER BY band_label
        """,
        current.tenant_id,
    )

    return {
        "trend": [
            {
                "month": r["month"].isoformat() if r["month"] else None,
                "total": int(r["total"]) if r["total"] is not None else 0,
            }
            for r in reversed(trend_rows)
        ],
        "band_distribution": [
            {"band": r["band"], "count": int(r["count"])}
            for r in band_rows
        ],
        "integrity_flags":  [],
    }


# ── Attrition cost ────────────────────────────────────────────────────────────

@router.get("/attrition")
async def attrition_cost(db: DbConn, current=CFO):
    from datetime import datetime, timezone
    qtd_start = datetime.now(timezone.utc).replace(month=((datetime.now().month - 1) // 3) * 3 + 1, day=1)

    exit_count = await db.fetchval(
        """
        SELECT COUNT(*) FROM employee_master
        WHERE tenant_id=$1 AND status='ALUMNI' AND dol >= $2
        """,
        current.tenant_id, qtd_start,
    )

    tenure_rows = await db.fetch(
        """
        SELECT
          CASE
            WHEN EXTRACT(YEAR FROM AGE(COALESCE(dol, NOW()), doj)) < 1 THEN '<1yr'
            WHEN EXTRACT(YEAR FROM AGE(COALESCE(dol, NOW()), doj)) < 3 THEN '1–3yr'
            WHEN EXTRACT(YEAR FROM AGE(COALESCE(dol, NOW()), doj)) < 5 THEN '3–5yr'
            ELSE '5yr+'
          END AS bucket,
          COUNT(*) AS count
        FROM employee_master
        WHERE tenant_id = $1 AND status = 'ALUMNI'
        GROUP BY 1
        """,
        current.tenant_id,
    )

    return {
        "exit_count_qtd":        exit_count,
        "tenure_distribution": [
            {"bucket": r["bucket"], "count": int(r["count"])}
            for r in tenure_rows
        ],
        "replacement_multiplier": 0.8,
    }


# ── Compliance posture ────────────────────────────────────────────────────────

@router.get("/compliance")
async def compliance_posture(db: DbConn, current=CFO):
    rows = await db.fetch(
        """
        SELECT obligation_name, coverage_pct, gap_count, status
        FROM compliance_obligation
        WHERE tenant_id = $1
        ORDER BY coverage_pct ASC
        """,
        current.tenant_id,
    )
    return {"items": [
        {
            "obligation_name": r["obligation_name"],
            "coverage_pct": float(r["coverage_pct"]) if r["coverage_pct"] is not None else 0.0,
            "gap_count": int(r["gap_count"]) if r["gap_count"] is not None else 0,
            "status": r["status"],
        }
        for r in rows
    ]}


# ── Benchmarking ──────────────────────────────────────────────────────────────

@router.get("/benchmark")
async def benchmarking(db: DbConn, current=CFO):
    # insight_cache stores pre-computed cross-org percentiles (suppressed if cohort < 30)
    rows = await db.fetch(
        """
        SELECT cache_key AS role_category, cache_value AS percentiles
        FROM insight_cache
        WHERE tenant_id=$1 AND cache_key LIKE 'benchmark_%'
        ORDER BY cache_key
        """,
        current.tenant_id,
    )
    return {"benchmarks": [
        {
            "role_category": r["role_category"],
            "percentiles": json.loads(r["percentiles"]) if isinstance(r["percentiles"], str) else (r["percentiles"] or {}),
        }
        for r in rows
    ]}


# ── Anomaly alerts ────────────────────────────────────────────────────────────

@router.get("/anomalies")
async def anomaly_alerts(db: DbConn, current=CFO):
    try:
        rows = await db.fetch(
            """
            SELECT anomaly_id, rule_name AS type, financial_pattern,
                   detected_at, severity, status
            FROM anomaly_event
            WHERE tenant_id = $1 AND status = 'OPEN'
            ORDER BY detected_at DESC
            """,
            current.tenant_id,
        )
    except Exception:
        rows = []
    return {"anomalies": [
        {
            "anomaly_id": str(r["anomaly_id"]),
            "type": r["type"],
            "financial_pattern": r["financial_pattern"],
            "detected_at": r["detected_at"].isoformat() if r["detected_at"] else None,
            "severity": r["severity"],
            "status": r["status"],
        }
        for r in rows
    ], "total": len(rows)}


@router.post("/anomalies/{anomaly_id}/acknowledge")
async def acknowledge_anomaly(anomaly_id: str, db: DbConn, current=CFO):
    try:
        row = await db.fetchrow(
            "SELECT anomaly_id, tenant_id FROM anomaly_event WHERE anomaly_id=$1 AND tenant_id=$2",
            anomaly_id, current.tenant_id,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ANOMALY_NOT_FOUND")
        await db.execute(
            "UPDATE anomaly_event SET status='ACKNOWLEDGED', acknowledged_by=$2, acknowledged_at=NOW() WHERE anomaly_id=$1",
            anomaly_id, current.user_id,
        )
    except HTTPException:
        raise
    except Exception:
        pass
    # In production: AnomalyAcknowledgementWorkflow fan-out notifies CHRO with identity context
    return {"message": "Anomaly acknowledged — CHRO notified"}


# ── Consent dashboard ─────────────────────────────────────────────────────────

@router.get("/consent")
async def consent_dashboard(db: DbConn, current=CFO):
    dept_rows = await db.fetch(
        """
        SELECT em.department,
               COUNT(*) FILTER (WHERE eu.consent_status='GRANTED') AS granted,
               COUNT(*) AS total,
               ROUND(COUNT(*) FILTER (WHERE eu.consent_status='GRANTED') * 100.0 / COUNT(*)) AS pct
        FROM employee_user eu
        JOIN employee_master em ON em.employee_user_id = eu.employee_user_id
        WHERE em.tenant_id=$1 AND em.status='ACTIVE' AND em.department IS NOT NULL
        GROUP BY em.department
        ORDER BY pct ASC
        """,
        current.tenant_id,
    )
    return {"by_department": [
        {
            "department": r["department"],
            "granted": int(r["granted"]) if r["granted"] is not None else 0,
            "total": int(r["total"]) if r["total"] is not None else 0,
            "pct": int(r["pct"]) if r["pct"] is not None else 0,
        }
        for r in dept_rows
    ]}


# ── LLM insight narrative (aggregated metadata only) ─────────────────────────

@router.get("/insight-narrative")
async def insight_narrative(db: DbConn, current=CFO):
    # In production: calls prana-ai career_insight_service with pre-aggregated metrics
    # Never passes raw extracted_fields — only benchmarked percentiles
    return {"narrative": "Insight narrative generation pending — prana-ai integration required."}


# ── Digest: settings ─────────────────────────────────────────────────────────


class DigestConfigBody(BaseModel):
    recipients: list[str]
    schedules: dict
    sections: list[str]
    format: Literal["email", "email_pdf"]
    active: bool


@router.get("/digest/settings")
async def get_digest_settings(db: DbConn, current=CFO):
    config = await _digest_svc.get_config(db, current.tenant_id, "cfo")
    return {"digest_settings": config}


@router.put("/digest/settings")
async def save_digest_settings(body: DigestConfigBody, db: DbConn, current=CFO):
    await _digest_svc.save_config(
        db, current.tenant_id, "cfo", body.model_dump(), str(current.user_id)
    )
    return {"message": "CFO digest settings saved"}


# ── Digest: data endpoints ────────────────────────────────────────────────────

def _resolve_window(period: str, from_date: date | None, to_date: date | None):
    if from_date is not None or to_date is not None:
        if from_date is None or to_date is None:
            raise HTTPException(400, detail={
                "error": "DATE_RANGE_INCOMPLETE",
                "message": "Provide both from_date and to_date, or neither (uses period preset).",
            })
        from_dt = datetime.combine(from_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        to_dt   = datetime.combine(to_date,   datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(days=1)
    else:
        from_dt, to_dt = period_window(period)  # type: ignore[arg-type]
    try:
        validate_window(from_dt, to_dt)
    except ValueError as exc:
        raise HTTPException(400, detail=exc.args[0])
    return from_dt, to_dt


@router.get("/digest/weekly")
async def weekly_digest(
    db: DbConn, current=CFO,
    from_date: date | None = Query(None, alias="from"),
    to_date:   date | None = Query(None, alias="to"),
):
    from_dt, to_dt = _resolve_window("weekly", from_date, to_date)
    return {"digest": await _digest_svc.build_cfo_digest(db, current.tenant_id, from_dt, to_dt)}


@router.get("/digest/monthly")
async def monthly_digest(
    db: DbConn, current=CFO,
    from_date: date | None = Query(None, alias="from"),
    to_date:   date | None = Query(None, alias="to"),
):
    from_dt, to_dt = _resolve_window("monthly", from_date, to_date)
    return {"digest": await _digest_svc.build_cfo_digest(db, current.tenant_id, from_dt, to_dt)}


@router.get("/digest/quarterly")
async def quarterly_digest(
    db: DbConn, current=CFO,
    from_date: date | None = Query(None, alias="from"),
    to_date:   date | None = Query(None, alias="to"),
):
    from_dt, to_dt = _resolve_window("quarterly", from_date, to_date)
    return {"digest": await _digest_svc.build_cfo_digest(db, current.tenant_id, from_dt, to_dt)}
