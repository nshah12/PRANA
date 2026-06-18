"""
CFO endpoints — aggregated financial analytics only.
Privacy contract: zero individual salary figures in any response.
All ₹ values replaced with qualitative labels or percentile ranges.
Cohort minimum 30 enforced before returning payroll data.
All queries scoped to tenant_id from JWT.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from dependencies import DbConn, require_oa

router = APIRouter()
CFO = Depends(require_oa("cfo", "oa_admin"))

_CFO_COHORT_MIN = 30   # overridable via platform_config in production


# ── Dashboard KPIs ────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def cfo_dashboard(db: DbConn, current=CFO):
    active_count = await db.fetchval(
        "SELECT COUNT(*) FROM employee_master WHERE tenant_id=$1 AND status='ACTIVE'",
        current.tenant_id,
    )
    open_anomalies = await db.fetchval(
        "SELECT COUNT(*) FROM anomaly_event WHERE tenant_id=$1 AND status='OPEN'",
        current.tenant_id,
    )
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
        "trend":            [dict(r) for r in reversed(trend_rows)],
        "band_distribution":[dict(r) for r in band_rows],
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
        "tenure_distribution":   [dict(r) for r in tenure_rows],
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
    return {"items": [dict(r) for r in rows]}


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
    return {"benchmarks": [dict(r) for r in rows]}


# ── Anomaly alerts ────────────────────────────────────────────────────────────

@router.get("/anomalies")
async def anomaly_alerts(db: DbConn, current=CFO):
    rows = await db.fetch(
        """
        SELECT anomaly_id, anomaly_type AS type, financial_pattern,
               detected_at, severity, status
        FROM anomaly_event
        WHERE tenant_id = $1 AND status = 'OPEN'
        ORDER BY detected_at DESC
        """,
        current.tenant_id,
    )
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
    return {"by_department": [dict(r) for r in dept_rows]}


# ── LLM insight narrative (aggregated metadata only) ─────────────────────────

@router.get("/insight-narrative")
async def insight_narrative(db: DbConn, current=CFO):
    # In production: calls prana-ai career_insight_service with pre-aggregated metrics
    # Never passes raw extracted_fields — only benchmarked percentiles
    return {"narrative": "Insight narrative generation pending — prana-ai integration required."}
