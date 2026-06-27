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

log = logging.getLogger(__name__)

# Fields stripped from extracted_fields before DB storage — never persisted
_SENSITIVE_FIELDS = {
    "gross_salary", "basic_salary", "net_salary", "hra", "pf_employee",
    "pf_employer", "total_deductions", "ctc_before", "ctc_after",
    "employee_share", "employer_share",
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

        # Strip sensitive raw financial fields — never stored in DB
        safe_fields = {k: v for k, v in extracted_fields.items() if k not in _SENSITIVE_FIELDS}

        employee_user_id = await self._db.fetchval(
            "SELECT employee_user_id FROM employee_master WHERE employee_uuid=$1", employee_uuid
        )

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
        safe_fields = {k: v for k, v in extracted_fields.items() if k not in _SENSITIVE_FIELDS}

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
