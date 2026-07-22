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
from services.manifest_service import ManifestService

router = APIRouter()

OAAdmin = Depends(require_oa("oa_admin"))

# ALLOWLIST of extracted_fields keys safe to return to OA-Admin — everything
# NOT on this list is stripped by default.
#
# This used to be a blocklist of bare words ("ctc", "tds", "pf", "salary")
# checked via exact match — it never matched the real field names prana-ai's
# extraction schemas actually produce (gross_ctc, net_pay, tds_amount,
# pf_employee), so real ₹ figures reached the OA-Admin's browser via this
# endpoint. A blocklist also can't cover prana-api's own doc_type_field_
# manifest system, which lets a tenant configure arbitrary field names per
# doc type — no fixed "known-bad" list can keep up with that. An allowlist
# fails in the safe direction: an unrecognized key (typo, new doc type, or
# tenant-custom manifest field) is dropped instead of leaked.
#
# Kept in sync by hand with prana-ai/pipeline/stage06_route.py's
# _SAFE_METADATA_FIELDS (separate deployables — no cross-service imports
# allowed, see .claude/rules/deployment.md) — this is the second, defense-in-
# depth layer, since exception_queue.extracted_fields was already filtered
# once by Stage06Route.raise_exception() before landing here.
_SAFE_EXTRACTED_FIELDS = {
    "account_holder", "account_number", "acknowledgement_date",
    "acknowledgement_no", "acknowledgement_number", "appraisal_period",
    "assessment_year", "bank_name", "bonus_percentage", "bonus_type",
    "conduct", "contribution_month", "credit_dates", "date_of_appointment",
    "date_of_exit", "date_of_joining", "date_of_joining_prev",
    "date_of_leaving", "date_of_leaving_prev", "date_of_offer",
    "deductor_name", "deductor_tan", "department", "designation",
    "effective_date", "eligible_months", "employee_id", "employee_name",
    "employer_address", "employer_name", "employer_tan", "employment_type",
    "establishment_id", "filing_date", "financial_year", "full_settlement",
    "grade", "grade_band", "gratuity_eligible", "hr_name", "ifsc_code",
    "increment_percent", "increment_percentage", "increment_reason",
    "itr_form_type", "last_working_day", "letter_date", "location",
    "manager_name", "member_id", "new_designation", "new_grade",
    "notice_period", "notice_period_days", "overall_confidence",
    "pan_number", "pay_period_month", "pay_period_year", "payment_date",
    "performance_band", "performance_rating", "period_of_employment",
    "pf_account_no", "pf_number", "policy_number", "previous_designation",
    "previous_employer_name", "previous_employer_tan", "previous_grade",
    "probation_months", "probation_period", "proof_type", "provider_name",
    "reason", "reason_for_exit", "receipt_date", "reporting_manager",
    "reporting_to", "salary_credit_count", "statement_from", "statement_to",
    "submission_date", "taxpayer_name", "tenure_text", "uan", "uan_number",
    "years_of_service",
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


async def _effective_safe_fields(db, tenant_id, doc_type: Optional[str]) -> set:
    """
    Static allowlist unioned with this tenant/doc_type's manifest-declared
    safe_fields — mirrors prana-ai's Stage06Route._effective_safe_fields so
    a tenant-custom field that survived Stage06's strip (because an OA-Admin
    marked it safe in their manifest) doesn't get re-stripped here.

    Fails closed: no doc_type on the row (older exception, pre-dates this
    field), or the manifest lookup itself fails (no manifest configured, DB
    hiccup), falls back to the static allowlist alone.
    """
    if not doc_type:
        return _SAFE_EXTRACTED_FIELDS
    try:
        manifest = await ManifestService(db).resolve(tenant_id, doc_type)
        return _SAFE_EXTRACTED_FIELDS | set(manifest.safe_fields)
    except Exception:
        return _SAFE_EXTRACTED_FIELDS


def _safe_extracted_fields(raw: Optional[str], effective_safe: Optional[set] = None) -> Optional[dict]:
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
    return {k: v for k, v in data.items() if k in (effective_safe or _SAFE_EXTRACTED_FIELDS)}


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
        SELECT eq.exception_id, eq.document_id, eq.tenant_id, eq.exception_type,
               eq.extracted_fields, eq.candidate_matches,
               eq.status, eq.raised_at, eq.resolved_at, eq.resolved_by, eq.resolved_employee_uuid,
               d.doc_type
        FROM exception_queue eq
        JOIN document d ON d.document_id = eq.document_id
        WHERE eq.exception_id = $1 AND eq.tenant_id = $2
        """,
        exception_id, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EXCEPTION_NOT_FOUND)

    exc = _serialize_exception(row)
    effective_safe = await _effective_safe_fields(db, current.tenant_id, row.get("doc_type"))
    exc["extracted_fields"] = _safe_extracted_fields(row["extracted_fields"], effective_safe)
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
        from services.tenant_isolation_guard import TenantIsolationGuard
        await TenantIsolationGuard(db).check_employee_access(
            employee_uuid=body.employee_uuid, requesting_tenant_id=current.tenant_id,
            actor_id=current.user_id,
        )
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
        except Exception as exc:
            from services.error_observability_service import ErrorObservabilityService
            try:
                await ErrorObservabilityService(db).record(
                    exc=exc, source="HTTP", source_detail="resolve_exception:signal_workflow",
                )
            except Exception:
                pass
            # Pipeline workflow may have already timed out — non-fatal

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
        except Exception as exc:
            from services.error_observability_service import ErrorObservabilityService
            try:
                await ErrorObservabilityService(db).record(
                    exc=exc, source="HTTP", source_detail="dismiss_exception:signal_workflow",
                )
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

