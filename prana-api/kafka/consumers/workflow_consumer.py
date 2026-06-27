"""
WorkflowConsumer — prana.ingest.events

Listens for DOC_INGESTED, BATCH_UPLOADED, and DOC_RECLASSIFIED events.
Starts Temporal workflows so the HTTP handler never has to.

DOC_INGESTED     → DocumentPipelineWorkflow + BatchTimeoutMonitorWorkflow (per file)
BATCH_UPLOADED   → BatchProgressWorkflow (parent tracker, only when batch_id present)
DOC_RECLASSIFIED → DocumentPipelineWorkflow restart with OA-Admin resolved doc_type
"""
import asyncio
import logging

from aiokafka import AIOKafkaConsumer

from config import Settings
from workflows.document_pipeline import DocumentPipelineWorkflow, TASK_QUEUE
from workflows.batch_progress import BatchProgressWorkflow, BatchTimeoutMonitorWorkflow, BATCH_TASK_QUEUE
from workflows.compliance import (
    ErasureConfirmationWorkflow,
    DataExportWorkflow,
    GrievanceWorkflow,
    DataCorrectionWorkflow,
)

log = logging.getLogger(__name__)

GROUP_ID = "prana-workflow-consumer"
COMPLIANCE_TASK_QUEUE = "compliance-queue"


class WorkflowConsumer:
    def __init__(self, settings: Settings, temporal_client, db_pool=None) -> None:
        self._settings = settings
        self._temporal = temporal_client
        self._db_pool = db_pool
        self._consumer = AIOKafkaConsumer(
            "prana.ingest.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            value_deserializer=lambda b: __import__("json").loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("WorkflowConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                etype = event.get("event_type")
                try:
                    if etype == "DOC_INGESTED":
                        await self._handle_doc_ingested(event)
                    elif etype == "BATCH_UPLOADED":
                        await self._handle_batch_uploaded(event)
                    elif etype == "DOC_RECLASSIFIED":
                        await self._handle_doc_reclassified(event)
                    elif etype == "ERASURE_REQUESTED":
                        await self._handle_erasure_requested(event)
                    elif etype == "DATA_EXPORT_REQUESTED":
                        await self._handle_data_export_requested(event)
                    elif etype == "GRIEVANCE_FILED":
                        await self._handle_grievance_filed(event)
                    elif etype == "DATA_CORRECTION_REQUESTED":
                        await self._handle_data_correction_requested(event)
                    else:
                        log.debug("WorkflowConsumer: no handler for event_type=%s", etype)
                except Exception:
                    log.exception("WorkflowConsumer error event_type=%s document_id=%s",
                                  etype, event.get("document_id"))
                else:
                    try:
                        await self._consumer.commit()
                    except Exception:
                        log.warning("WorkflowConsumer: offset commit failed — will retry on restart")
        finally:
            await self._consumer.stop()

    async def _handle_doc_ingested(self, event: dict) -> None:
        doc_id    = event["document_id"]
        tenant_id = event["tenant_id"]
        batch_id  = event.get("batch_id")

        # Idempotent: workflow already running → Temporal returns WorkflowAlreadyStartedError, ignore
        try:
            await self._temporal.start_workflow(
                DocumentPipelineWorkflow.run,
                {
                    "document_id": doc_id,
                    "tenant_id":   tenant_id,
                    "doc_type":    event["doc_type"],
                    "doc_period":  event.get("doc_period"),
                    "s3_key":      event["s3_key"],
                    "s3_bucket":   event["s3_bucket"],
                },
                id=f"doc-pipeline-{doc_id}",
                task_queue=TASK_QUEUE,
            )
        except Exception as exc:
            if "already" not in str(exc).lower():
                raise

        try:
            await self._temporal.start_workflow(
                BatchTimeoutMonitorWorkflow.run,
                {"document_id": doc_id, "tenant_id": tenant_id, "batch_id": batch_id},
                id=f"doc-timeout-{doc_id}",
                task_queue=TASK_QUEUE,
            )
        except Exception as exc:
            if "already" not in str(exc).lower():
                raise

    async def _handle_doc_reclassified(self, event: dict) -> None:
        """
        OA-Admin resolved an unclassified document.
        Re-start DocumentPipelineWorkflow with the manually-assigned doc_type.
        Uses a new workflow ID (suffix -reclassified-{n}) so Temporal doesn't
        collide with the original pipeline run.
        """
        doc_id    = event["document_id"]
        tenant_id = event["tenant_id"]
        doc_type  = event["doc_type"]       # OA-Admin's classification

        # Fetch S3 key from DB using the injected pool
        if not self._db_pool:
            log.error("DOC_RECLASSIFIED: no db_pool injected — cannot fetch s3_key")
            return
        async with self._db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT s3_key, s3_bucket FROM document WHERE document_id=$1", doc_id
            )

        if not row:
            log.error("DOC_RECLASSIFIED: document %s not found in DB", doc_id)
            return

        # Increment suffix to produce a unique workflow ID each re-attempt
        run_suffix = event.get("run_attempt", 1)
        try:
            await self._temporal.start_workflow(
                DocumentPipelineWorkflow.run,
                {
                    "document_id": doc_id,
                    "tenant_id":   tenant_id,
                    "doc_type":    doc_type,
                    "doc_period":  event.get("doc_period"),
                    "s3_key":      row["s3_key"],
                    "s3_bucket":   row["s3_bucket"],
                },
                id=f"doc-pipeline-{doc_id}-reclassified-{run_suffix}",
                task_queue=TASK_QUEUE,
            )
            log.info("Restarted pipeline for reclassified doc=%s doc_type=%s", doc_id, doc_type)
        except Exception as exc:
            if "already" not in str(exc).lower():
                raise

    async def _handle_erasure_requested(self, event: dict) -> None:
        employee_user_id = event.get("employee_user_id", "")
        wf_id = event.get("workflow_id") or f"erasure-{employee_user_id}"
        payload = {k: v for k, v in event.items() if k != "event_type"}
        try:
            await self._temporal.start_workflow(
                ErasureConfirmationWorkflow.run,
                payload,
                id=wf_id,
                task_queue=COMPLIANCE_TASK_QUEUE,
            )
        except Exception:
            log.exception("WorkflowConsumer: ErasureConfirmationWorkflow start failed wf_id=%s", wf_id)

    async def _handle_data_export_requested(self, event: dict) -> None:
        wf_id = event.get("workflow_id") or f"export-{event.get('employee_user_id')}-{event.get('export_id')}"
        payload = {k: v for k, v in event.items() if k != "event_type"}
        try:
            await self._temporal.start_workflow(
                DataExportWorkflow.run,
                payload,
                id=wf_id,
                task_queue=COMPLIANCE_TASK_QUEUE,
            )
        except Exception:
            log.exception("WorkflowConsumer: DataExportWorkflow start failed wf_id=%s", wf_id)

    async def _handle_grievance_filed(self, event: dict) -> None:
        grievance_id = event.get("grievance_id", "")
        wf_id = event.get("workflow_id") or f"grievance-{grievance_id}"
        payload = {k: v for k, v in event.items() if k != "event_type"}
        try:
            await self._temporal.start_workflow(
                GrievanceWorkflow.run,
                payload,
                id=wf_id,
                task_queue=COMPLIANCE_TASK_QUEUE,
            )
        except Exception:
            log.exception("WorkflowConsumer: GrievanceWorkflow start failed wf_id=%s", wf_id)

    async def _handle_data_correction_requested(self, event: dict) -> None:
        correction_id = event.get("correction_id", "")
        wf_id = f"correction-{correction_id}"
        payload = {k: v for k, v in event.items() if k != "event_type"}
        try:
            await self._temporal.start_workflow(
                DataCorrectionWorkflow.run,
                payload,
                id=wf_id,
                task_queue=COMPLIANCE_TASK_QUEUE,
            )
        except Exception:
            log.exception("WorkflowConsumer: DataCorrectionWorkflow start failed wf_id=%s", wf_id)

    async def _handle_batch_uploaded(self, event: dict) -> None:
        batch_id = event.get("batch_id")
        if not batch_id:
            return

        # BatchProgressWorkflow tracks fan-out; only meaningful for multi-file batches
        # (document_ids not in BATCH_UPLOADED — BatchProgressWorkflow queries DB for them)
        try:
            await self._temporal.start_workflow(
                BatchProgressWorkflow.run,
                {
                    "batch_id":   batch_id,
                    "tenant_id":  event["tenant_id"],
                    "doc_type":   event["doc_type"],
                    "doc_period": event.get("doc_period"),
                },
                id=f"batch-{batch_id}",
                task_queue=BATCH_TASK_QUEUE,
            )
        except Exception as exc:
            if "already" not in str(exc).lower():
                raise
