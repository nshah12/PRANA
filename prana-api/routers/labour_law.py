"""
Labour Law & Statutory Compliance endpoints — CHRO / OA-Admin facing.

Prefix: /v1/compliance/statutory

Indian statutory acts tracked:
  EPF_ACT           — Employee Provident Fund (ECR filing, challan)
  ESIC_ACT          — Employee State Insurance (monthly contribution)
  INCOME_TAX        — TDS deduction & Form 16 issuance
  GRATUITY_ACT      — Payment of Gratuity (eligibility after 5 years)
  BONUS_ACT         — Payment of Bonus (salary ≤ ₹21,000/month employees)
  MATERNITY_ACT     — Maternity Benefit (26 weeks leave, compliance check)
  POSH_ACT          — Prevention of Sexual Harassment (ICC mandatory ≥10 employees)
  MIN_WAGES_ACT     — Minimum Wages (state-wise, updated quarterly)
  FACTORIES_ACT     — Factory license renewal, safety compliance
  SHOPS_EST_ACT     — Shops & Establishment Act (state-specific)
  LABOUR_WELFARE_FUND — LWF contribution (state-specific)
  OTHER

Roles:
  GET  /compliance/statutory              — CHRO: list all obligations (with filters)
  GET  /compliance/statutory/overdue      — CHRO: overdue obligations only
  GET  /compliance/statutory/{id}         — CHRO / OA-Admin: single obligation detail
  POST /compliance/statutory              — OA-Admin: create obligation (from PA-seeded calendar or manual)
  PATCH /compliance/statutory/{id}        — OA-Admin: update status / attach proof
  GET  /compliance/statutory/calendar     — CHRO: upcoming deadlines (next 90 days)

HTTP handler contract:
  validate → DB write → Kafka publish → return 2xx
"""
import uuid
import json
import logging
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from dependencies import require_oa, DbConn

log = logging.getLogger(__name__)
router = APIRouter()
# CHRO can view; OA-Admin can create/update
OA   = Depends(require_oa("oa_admin", "oa_operator"))
CHRO = Depends(require_oa("chro", "oa_admin", "cfo"))

VALID_ACTS = {
    "EPF_ACT", "ESIC_ACT", "INCOME_TAX", "GRATUITY_ACT", "BONUS_ACT",
    "MATERNITY_ACT", "POSH_ACT", "MIN_WAGES_ACT", "FACTORIES_ACT",
    "SHOPS_EST_ACT", "LABOUR_WELFARE_FUND", "OTHER",
}

VALID_STATUSES = {"PENDING", "IN_PROGRESS", "COMPLETE", "OVERDUE"}


def _serialize_obligation(r) -> dict:
    return {
        "obligation_id":   str(r["obligation_id"]),
        "tenant_id":       str(r["tenant_id"]),
        "obligation_name": r["obligation_name"],
        "statutory_act":   r["statutory_act"],
        "category":        r["category"],
        "period_start":    r["period_start"].isoformat() if r["period_start"] else None,
        "period_end":      r["period_end"].isoformat() if r["period_end"] else None,
        "deadline":        r["deadline"].isoformat() if r["deadline"] else None,
        "status":          r["status"],
        "filing_reference": r["filing_reference"],
        "headcount":       r["headcount"],
        "overdue_since":   r["overdue_since"].isoformat() if r["overdue_since"] else None,
        "document_id":     str(r["document_id"]) if r["document_id"] else None,
        "created_at":      r["created_at"].isoformat() if r["created_at"] else None,
        "updated_at":      r["updated_at"].isoformat() if r["updated_at"] else None,
    }


# ── List obligations ──────────────────────────────────────────────────────────

@router.get("")
async def list_obligations(
    db: DbConn,
    current=CHRO,
    statutory_act: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    period_start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """CHRO: list all statutory compliance obligations for this tenant."""
    conditions = ["tenant_id = $1", "TRUE"]
    params: list = [current.tenant_id]

    if statutory_act:
        if statutory_act not in VALID_ACTS:
            raise HTTPException(status_code=400, detail="INVALID_ACT")
        params.append(statutory_act)
        conditions.append(f"statutory_act = ${len(params)}")

    if status_filter:
        if status_filter not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail="INVALID_STATUS")
        params.append(status_filter)
        conditions.append(f"status = ${len(params)}")

    if period_start:
        params.append(period_start)
        conditions.append(f"period_start >= ${len(params)}")

    where = " AND ".join(conditions)
    params.extend([limit, offset])
    n = len(params)

    rows = await db.fetch(
        f"""
        SELECT obligation_id, tenant_id, obligation_name, statutory_act, category,
               period_start, period_end, deadline, status, filing_reference,
               headcount, overdue_since, document_id, created_at, updated_at
        FROM compliance_obligation
        WHERE {where}
        ORDER BY deadline ASC
        LIMIT ${n - 1} OFFSET ${n}
        """,
        *params,
    )
    total = await db.fetchval(
        "SELECT COUNT(*) FROM compliance_obligation WHERE " + where,
        *params[:-2],
    )
    return {"items": [_serialize_obligation(r) for r in rows], "total": total}


# ── Overdue obligations ───────────────────────────────────────────────────────

@router.get("/overdue")
async def list_overdue(db: DbConn, current=CHRO):
    """CHRO: obligations past their deadline that are not yet COMPLETE."""
    today = datetime.date.today()
    rows = await db.fetch(
        """
        SELECT obligation_id, tenant_id, obligation_name, statutory_act, category,
               period_start, period_end, deadline, status, filing_reference,
               headcount, overdue_since, document_id, created_at, updated_at
        FROM compliance_obligation
        WHERE tenant_id = $1
          AND deadline < $2
          AND status NOT IN ('COMPLETE')
        ORDER BY deadline ASC
        LIMIT 200
        """,
        current.tenant_id,
        today,
    )
    return {"items": [_serialize_obligation(r) for r in rows], "total": len(rows)}


# ── Upcoming calendar (next 90 days) ─────────────────────────────────────────

@router.get("/calendar")
async def obligation_calendar(
    db: DbConn,
    current=CHRO,
    days: int = Query(90, ge=7, le=365),
):
    """CHRO: upcoming deadlines within the next N days."""
    today = datetime.date.today()
    cutoff = today + datetime.timedelta(days=days)
    rows = await db.fetch(
        """
        SELECT obligation_id, tenant_id, obligation_name, statutory_act, category,
               period_start, period_end, deadline, status, filing_reference,
               headcount, overdue_since, document_id, created_at, updated_at
        FROM compliance_obligation
        WHERE tenant_id = $1
          AND deadline BETWEEN $2 AND $3
          AND status NOT IN ('COMPLETE')
        ORDER BY deadline ASC
        LIMIT 200
        """,
        current.tenant_id,
        today,
        cutoff,
    )
    return {"items": [_serialize_obligation(r) for r in rows], "total": len(rows)}


# ── Single obligation ─────────────────────────────────────────────────────────

@router.get("/{obligation_id}")
async def get_obligation(obligation_id: str, db: DbConn, current=CHRO):
    try:
        obl_uuid = uuid.UUID(obligation_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    row = await db.fetchrow(
        """
        SELECT obligation_id, tenant_id, obligation_name, statutory_act, category,
               period_start, period_end, deadline, status, filing_reference,
               headcount, overdue_since, document_id, created_at, updated_at
        FROM compliance_obligation
        WHERE obligation_id = $1 AND tenant_id = $2
        """,
        obl_uuid,
        current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return {"obligation": _serialize_obligation(row)}


# ── Create obligation (OA-Admin) ──────────────────────────────────────────────

class ObligationIn(BaseModel):
    obligation_name: str = Field(..., min_length=3, max_length=200)
    statutory_act:   str = Field(..., description="EPF_ACT | ESIC_ACT | INCOME_TAX | ...")
    category:        Optional[str] = Field(None, max_length=50)
    deadline:        str = Field(..., description="YYYY-MM-DD")
    period_start:    Optional[str] = Field(None, description="YYYY-MM-DD")
    period_end:      Optional[str] = Field(None, description="YYYY-MM-DD")
    headcount:       Optional[int] = Field(None, ge=0)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_obligation(
    body: ObligationIn,
    request: Request,
    db: DbConn,
    current=OA,
):
    """OA-Admin: add a statutory compliance obligation to the tracker."""
    if body.statutory_act not in VALID_ACTS:
        raise HTTPException(status_code=400, detail="INVALID_ACT")

    obligation_id = str(uuid.uuid4())
    await db.execute(
        """
        INSERT INTO compliance_obligation
          (obligation_id, tenant_id, obligation_name, statutory_act, category,
           deadline, period_start, period_end, headcount, status, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'PENDING', NOW(), NOW())
        """,
        uuid.UUID(obligation_id),
        current.tenant_id,
        body.obligation_name,
        body.statutory_act,
        body.category,
        datetime.date.fromisoformat(body.deadline),
        datetime.date.fromisoformat(body.period_start) if body.period_start else None,
        datetime.date.fromisoformat(body.period_end) if body.period_end else None,
        body.headcount,
    )

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.statutory_event({
            "event_type":    "OBLIGATION_DUE",
            "obligation_id": obligation_id,
            "act":           body.statutory_act,
            "tenant_id":     str(current.tenant_id),
            "due_date":      body.period_end,
        })

    return {"obligation_id": obligation_id, "status": "PENDING"}


# ── Update obligation (OA-Admin): mark complete / attach proof ────────────────

class ObligationUpdate(BaseModel):
    status:           Optional[str] = Field(None, description="IN_PROGRESS | COMPLETE")
    filing_reference: Optional[str] = Field(None, max_length=100,
                                            description="ECR challan no. / Form 16 batch ref")
    document_id:      Optional[str] = Field(None, description="UUID of uploaded proof document")
    headcount:        Optional[int] = Field(None, ge=0)


@router.patch("/{obligation_id}", status_code=status.HTTP_200_OK)
async def update_obligation(
    obligation_id: str,
    body: ObligationUpdate,
    request: Request,
    db: DbConn,
    current=OA,
):
    """OA-Admin: update obligation status or attach a proof-of-filing document."""
    if body.status and body.status not in {"IN_PROGRESS", "COMPLETE"}:
        raise HTTPException(status_code=400, detail="INVALID_STATUS")

    try:
        obl_uuid = uuid.UUID(obligation_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    row = await db.fetchrow(
        "SELECT obligation_id FROM compliance_obligation WHERE obligation_id=$1 AND tenant_id=$2",
        obl_uuid,
        current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    sets = []
    params: list = []

    if body.status:
        params.append(body.status)
        sets.append(f"status = ${len(params)}")

    if body.filing_reference is not None:
        params.append(body.filing_reference)
        sets.append(f"filing_reference = ${len(params)}")

    if body.document_id is not None:
        params.append(uuid.UUID(body.document_id))
        sets.append(f"document_id = ${len(params)}")

    if body.headcount is not None:
        params.append(body.headcount)
        sets.append(f"headcount = ${len(params)}")

    if not sets:
        raise HTTPException(status_code=400, detail="NO_FIELDS_TO_UPDATE")

    params.append(obl_uuid)
    sets_str = ", ".join(sets) + ", updated_at = NOW()"
    await db.execute(
        "UPDATE compliance_obligation SET " + sets_str + " WHERE obligation_id = $" + str(len(params)),
        *params,
    )

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        etype = "OBLIGATION_COMPLETED" if body.status == "COMPLETE" else "OBLIGATION_DUE"
        await kafka.statutory_event({
            "event_type":    etype,
            "obligation_id": obligation_id,
            "tenant_id":     str(current.tenant_id),
            "new_status":    body.status,
        })

    return {"obligation_id": obligation_id, "updated": True}
