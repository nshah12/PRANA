"""
Exception Queue API â€” OA-Admin views and resolves pipeline exceptions.

GET  /org/exceptions                     â€” list OPEN exceptions with SLA countdown
GET  /org/exceptions/{exception_id}      â€” detail: extracted_fields + candidate_matches
POST /org/exceptions/{exception_id}/resolve  â€” assign employee, signal workflow
POST /org/exceptions/{exception_id}/dismiss  â€” close without match, signal workflow

Auth: OA-Admin only. Tenant-scoped â€” admin never sees another tenant's exceptions.

Resolution signals 'exception_resolved' to the running DocumentPipelineWorkflow
(one of the two allowed Temporal calls from the HTTP path per project rules).

Privacy: extracted_fields from LLM output may include raw figures â€” strip salary/PAN
keys before returning to OA-Admin. Context fields (name, doj, designation) are fine.
"""
import datetime
import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from dependencies import DbConn, require_oa
from errors import PranaError

router = APIRouter()

OAAdmin = Depends(require_oa("oa_admin"))

# Fields stripped from extracted_fields before returning (privacy contract)
_STRIP_FROM_EXTRACTED = {
    "salary", "gross_salary", "net_salary", "basic_salary", "ctc",
    "hra", "pf", "tds", "pan", "nik", "account_number",
}


# â”€â”€ Request models â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ResolveExceptionIn(BaseModel):
    employee_uuid: str


class DismissExceptionIn(BaseModel):
    reason: str


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return str(request.client.host) if request.client else "unknown"


def _safe_extracted_fields(raw: Optional[str]) -> Optional[dict]:
    """
    Parse extracted_fields JSONB and strip raw financial figures before
    returning to OA-Admin. LLM output may include salary â€” must never surface.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    else:
        data = raw
    if not isinstance(data, dict):
        return data
    return {k: v for k, v in data.items() if k.lower() not in _STRIP_FROM_EXTRACTED}


def _serialize_exception(r: dict) -> dict:
    return {
        "exception_id": str(r["exception_id"]),
        "document_id": str(r["document_id"]),
        "tenant_id": str(r["tenant_id"]),
        "exception_type": r["exception_type"],
        "status": r["status"],
        "raised_at": r["raised_at"].isoformat() if r["raised_at"] else None,
        "resolved_at": r["resolved_at"].isoformat() if r.get("resolved_at") else None,
        "resolved_by": str(r["resolved_by"]) if r.get("resolved_by") else None,
        "resolved_employee_uuid": str(r["resolved_employee_uuid"]) if r.get("resolved_employee_uuid") else None,
    }


async def _get_sla_hours(db, tenant_id: str) -> int:
    """Fetch exception_sla_p95_hours from platform_config (never hardcoded)."""
    row = await db.fetchrow(
        """
        SELECT COALESCE(
            (SELECT config_value::int FROM tenant_config
             WHERE tenant_id=$1 AND config_key='exception_sla_p95_hours'),
            (SELECT config_value::int FROM platform_config
             WHERE config_key='exception_sla_p95_hours')
        ) AS sla_hours
        """,
        tenant_id,
    )
    return int(row["sla_hours"]) if row and row["sla_hours"] else 24


# â”€â”€ List â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/exceptions")
async def list_exceptions(
    request: Request,
    db: DbConn,
    current=OAAdmin,
    status_filter: str = "OPEN",
    limit: int = 50,
    offset: int = 0,
):
    """List exceptions for this tenant. Default: OPEN only, ordered oldest-first (worst SLA first)."""
    sla_hours = await _get_sla_hours(db, current.tenant_id)
    cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(hours=sla_hours)

    rows = await db.fetch(
        """
        SELECT exception_id, document_id, tenant_id, exception_type,
               status, raised_at, resolved_at, resolved_by, resolved_employee_uuid
        FROM exception_queue
        WHERE tenant_id = $1
          AND status = $2
        ORDER BY raised_at ASC
        LIMIT $3 OFFSET $4
        """,
        current.tenant_id, status_filter, limit, offset,
    )

    sla_breached = await db.fetchval(
        """
        SELECT COUNT(*) FROM exception_queue
        WHERE tenant_id = $1 AND status = 'OPEN' AND raised_at < $2
        """,
        current.tenant_id, cutoff,
    ) or 0

    exceptions = []
    for r in rows:
        exc = _serialize_exception(r)
        exc["sla_breached"] = r["raised_at"] < cutoff if r.get("raised_at") else False
        exceptions.append(exc)

    return {
        "exceptions": exceptions,
        "total": len(exceptions),
        "sla_breached": int(sla_breached),
    }


# â”€â”€ Detail â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/exceptions/{exception_id}")
async def get_exception(
    exception_id: str,
    db: DbConn,
    current=OAAdmin,
):
    row = await db.fetchrow(
        """
        SELECT exception_id, document_id, tenant_id, exception_type,
               extracted_fields, candidate_matches,
               status, raised_at, resolved_at, resolved_by, resolved_employee_uuid
        FROM exception_queue
        WHERE exception_id = $1 AND tenant_id = $2
        """,
        exception_id, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EXCEPTION_NOT_FOUND)

    exc = _serialize_exception(row)
    exc["extracted_fields"] = _safe_extracted_fields(row["extracted_fields"])
    # candidate_matches are IDs/names/confidence â€” no raw financial data
    raw_candidates = row["candidate_matches"]
    if isinstance(raw_candidates, str):
        try:
            exc["candidate_matches"] = json.loads(raw_candidates)
        except (json.JSONDecodeError, TypeError):
            exc["candidate_matches"] = None
    else:
        exc["candidate_matches"] = raw_candidates

    return {"exception": exc}


# â”€â”€ Resolve â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/exceptions/{exception_id}/resolve", status_code=status.HTTP_200_OK)
async def resolve_exception(
    exception_id: str,
    body: ResolveExceptionIn,
    request: Request,
    db: DbConn,
    current=OAAdmin,
):
    """
    OA-Admin picks the correct employee. Marks RESOLVED, signals DocumentPipelineWorkflow
    to continue routing with the confirmed employee_uuid.
    """
    row = await db.fetchrow(
        "SELECT document_id, tenant_id, status FROM exception_queue "
        "WHERE exception_id=$1 AND tenant_id=$2",
        exception_id, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EXCEPTION_NOT_FOUND)
    if row["status"] != "OPEN":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PranaError.EXCEPTION_NOT_OPEN)

    # Validate employee belongs to this tenant
    emp_uuid = await db.fetchval(
        "SELECT employee_uuid FROM employee_master WHERE employee_uuid=$1 AND tenant_id=$2 AND is_deleted=FALSE",
        body.employee_uuid, current.tenant_id,
    )
    if not emp_uuid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EMPLOYEE_NOT_FOUND)

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    await db.execute(
        """
        UPDATE exception_queue
        SET status='RESOLVED',
            resolved_by=$1,
            resolved_employee_uuid=$2,
            resolved_at=$3
        WHERE exception_id=$4 AND tenant_id=$5
        """,
        current.user_id, body.employee_uuid, now, exception_id, current.tenant_id,
    )

    # Signal the running DocumentPipelineWorkflow â€” allowed Temporal call from HTTP path
    temporal = getattr(request.app.state, "temporal_client", None)
    if temporal:
        try:
            document_id = str(row["document_id"])
            wf = temporal.get_workflow_handle(f"doc-pipeline-{document_id}")
            await wf.signal("exception_resolved", {
                "employee_uuid": body.employee_uuid,
                "resolved_by":   current.user_id,
            })
        except Exception:
            pass  # Pipeline workflow may have already timed out â€” non-fatal

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.exception_resolved({
            "event_type": "EXCEPTION_RESOLVED",
            "tenant_id": str(current.tenant_id),
            "actor_id": str(current.user_id),
            "actor_type": "OA_ADMIN",
            "exception_id": exception_id,
            "document_id": str(row["document_id"]),
            "employee_uuid": body.employee_uuid,
        })

    return {"exception_id": exception_id, "status": "RESOLVED"}


# â”€â”€ Dismiss â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/exceptions/{exception_id}/dismiss", status_code=status.HTTP_200_OK)
async def dismiss_exception(
    exception_id: str,
    body: DismissExceptionIn,
    request: Request,
    db: DbConn,
    current=OAAdmin,
):
    """
    OA-Admin dismisses without assigning an employee. Document stays un-routed.
    Signals DocumentPipelineWorkflow so it can exit cleanly.
    """
    row = await db.fetchrow(
        "SELECT document_id, tenant_id, status FROM exception_queue "
        "WHERE exception_id=$1 AND tenant_id=$2",
        exception_id, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EXCEPTION_NOT_FOUND)
    if row["status"] != "OPEN":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PranaError.EXCEPTION_NOT_OPEN)

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    await db.execute(
        """
        UPDATE exception_queue
        SET status='DISMISSED',
            resolved_by=$1,
            resolved_at=$2
        WHERE exception_id=$3 AND tenant_id=$4
        """,
        current.user_id, now, exception_id, current.tenant_id,
    )

    # Signal workflow so it exits the 7-day wait
    temporal = getattr(request.app.state, "temporal_client", None)
    if temporal:
        try:
            document_id = str(row["document_id"])
            wf = temporal.get_workflow_handle(f"doc-pipeline-{document_id}")
            await wf.signal("exception_resolved", {
                "employee_uuid": None,  # None = dismissed, not resolved
                "resolved_by":   current.user_id,
                "dismissed":     True,
                "dismiss_reason": body.reason,
            })
        except Exception:
            pass

    kafka = getattr(request.app.state, "kafka_producer", None)
    if kafka:
        await kafka.oa_user_event({
            "event_type": "EXCEPTION_DISMISSED",
            "tenant_id": current.tenant_id,
            "actor_id": current.user_id,
            "actor_type": "OA_ADMIN",
            "exception_id": exception_id,
        }, key=current.tenant_id)

    return {"exception_id": exception_id, "status": "DISMISSED"}

