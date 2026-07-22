"""
Stage 06 — Tag & Route
Final stage: update document row to ROUTED, create career_event, trigger InsightRefreshWorkflow.
If exception needed: create exception_queue row, set pipeline_status=EXCEPTION.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import asyncpg

from insights.benchmark_service import BenchmarkService
from pipeline.errors import PipelineError, PipelineException

log = logging.getLogger(__name__)

# ALLOWLIST of fields safe to persist to document.extracted_fields — everything
# NOT on this list is stripped by default, including field names neither this
# file nor any extraction/schemas/*.py has ever seen.
#
# This used to be a blocklist ("strip these known-sensitive names"), which
# failed twice: once because a schema's real field names (gross_ctc/net_pay/
# tds_amount) didn't match the list, and it structurally can never cover the
# manifest-driven extraction path — prana-api's doc_type_field_manifest lets
# any tenant's OA-Admin configure arbitrary field names per doc type, so no
# fixed list of "known-bad" names can keep up. An allowlist fails in the safe
# direction instead: an unrecognized field (whether a typo, a new doc type
# nobody's updated this list for yet, or a tenant-custom manifest field) is
# dropped — data loss, not a privacy violation.
#
# Every entry here is verified non-monetary metadata across every
# extraction/schemas/*.py field (names, dates, designations, IDs, document
# reference numbers, etc.) — see tests/test_prompt_schema_consistency.py and
# tests/test_stage06_route.py for the regression guards.
_SAFE_METADATA_FIELDS = {
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


class Stage06Route:

    def __init__(self, db: asyncpg.Connection, benchmark_svc: BenchmarkService,
                 kafka_producer=None):
        self._db = db
        self._benchmark = benchmark_svc
        self._kafka = kafka_producer  # optional: AiPipelineClient or aiokafka producer

    async def route(
        self,
        document_id: str,
        tenant_id: str,
        employee_uuid: str,
        pan_token: str,
        doc_type: str,
        doc_period: Optional[str],
        extracted_fields: dict,
        resolution_method: str,
        resolution_confidence: float,
        s3_key: str,
    ) -> None:
        # Produce benchmarks from salary fields BEFORE stripping them
        from uuid import UUID as _UUID
        benchmarks = await self._benchmark.build_career_context(
            employee_uuid=_UUID(employee_uuid),
            tenant_id=_UUID(tenant_id),
            extracted_fields=extracted_fields,
            doc_type=doc_type,
        )

        # Allowlist filter — only known-safe metadata fields reach the DB.
        safe_fields = {k: v for k, v in extracted_fields.items() if k in _SAFE_METADATA_FIELDS}

        employee_user_id = await self._db.fetchval(
            "SELECT employee_user_id FROM employee_master WHERE employee_uuid=$1", employee_uuid
        )

        try:
            async with self._db.transaction():
                await self._db.execute(
                    """
                    UPDATE document SET
                      employee_uuid=$2, pan_token=$3,
                      extracted_fields=$4, resolution_method=$5, resolution_confidence=$6,
                      pipeline_status='ROUTED', routed_at=NOW(), s3_key=$7
                    WHERE document_id=$1
                    """,
                    document_id, employee_uuid, pan_token,
                    json.dumps(safe_fields), resolution_method, resolution_confidence, s3_key,
                )

                # Career event from this document
                event_type = _doc_type_to_event(doc_type)
                if event_type:
                    await self._db.execute(
                        """
                        INSERT INTO career_event
                          (pan_token, employee_user_id, employee_uuid, tenant_id,
                           event_type, event_date, verified, doc_uuid, metadata)
                        VALUES ($1,$2,$3,$4,$5,$6,TRUE,$7,$8)
                        ON CONFLICT DO NOTHING
                        """,
                        pan_token, employee_user_id, employee_uuid, tenant_id,
                        event_type, _period_to_date(doc_period),
                        document_id, json.dumps({"benchmarks": benchmarks}),
                    )

                await self._db.execute(
                    """
                    UPDATE employee_master
                    SET vault_completeness = (
                      SELECT LEAST(100, COUNT(DISTINCT doc_type) * 10)
                      FROM document
                      WHERE employee_uuid=$1 AND pipeline_status='ROUTED' AND is_deleted=FALSE
                    ), updated_at=NOW()
                    WHERE employee_uuid=$1
                    """,
                    employee_uuid,
                )
        except PipelineException:
            raise
        except Exception as exc:
            raise PipelineException(
                code=PipelineError.S06_ROUTE_DB_TRANSACTION_FAILED,
                stage="stage06",
                message=f"ROUTED transaction failed for doc={document_id}: {exc}",
            ) from exc

        # Publish DOC_ROUTED to prana.pipeline.events AFTER the transaction commits.
        # Consumers: SSEFanoutConsumer (browser update), AnalyticsConsumer (vault health),
        # WorkflowConsumer (VaultCompletenessWorkflow trigger).
        # Fire-and-forget: a publish failure must not roll back the DB transaction.
        if self._kafka:
            try:
                await self._kafka.publish(
                    "prana.pipeline.events",
                    {
                        "event_type":   "DOC_ROUTED",
                        "document_id":  document_id,
                        "tenant_id":    tenant_id,
                        "employee_uuid": employee_uuid,
                        "pan_token":    pan_token,
                        "doc_type":     doc_type,
                        "doc_period":   doc_period,
                        "pipeline_status": "ROUTED",
                    },
                    key=document_id,
                )
            except Exception:
                log.exception("DOC_ROUTED Kafka publish failed doc=%s — DB already committed",
                              document_id)

    async def raise_exception(
        self,
        document_id: str,
        tenant_id: str,
        exception_type: str,
        extracted_fields: dict,
        candidates: list,
    ) -> None:
        safe_fields = {k: v for k, v in extracted_fields.items() if k in _SAFE_METADATA_FIELDS}

        async with self._db.transaction():
            await self._db.execute(
                "UPDATE document SET pipeline_status='EXCEPTION' WHERE document_id=$1",
                document_id,
            )
            await self._db.execute(
                """
                INSERT INTO exception_queue
                  (document_id, tenant_id, exception_type, extracted_fields, candidate_matches)
                VALUES ($1,$2,$3,$4,$5)
                """,
                document_id, tenant_id, exception_type,
                json.dumps(safe_fields), json.dumps(candidates),
            )


def _doc_type_to_event(doc_type: str) -> Optional[str]:
    return {
        "APPOINTMENT_LETTER": "JOINED",
        "JOINING_LETTER":     "JOINED",
        "OFFER_LETTER":       "JOINED",
        "INCREMENT_LETTER":   "INCREMENT",
        "PROMOTION_LETTER":   "PROMOTED",
        "RELIEVING_LETTER":   "EXITED",
        "EXPERIENCE_LETTER":  "EXITED",
    }.get(doc_type)


def _period_to_date(period: Optional[str]):
    if not period:
        return datetime.now(tz=timezone.utc).date()
    try:
        if period.startswith("FY:"):
            year = int(period.split(":")[1].split("-")[0])
            return datetime(year, 4, 1).date()
        if len(period) == 7:  # 2024-03
            return datetime.strptime(period, "%Y-%m").date().replace(day=1)
        return datetime.fromisoformat(period).date()
    except Exception:
        return datetime.now(tz=timezone.utc).date()
