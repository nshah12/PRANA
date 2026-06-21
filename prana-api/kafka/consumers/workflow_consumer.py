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

log = logging.getLogger(__name__)

GROUP_ID = "prana-workflow-consumer"


class WorkflowConsumer:
    def __init__(self, settings: Settings, temporal_client) -> None:
        self._settings = settings
        self._temporal = temporal_client
        self._consumer = AIOKafkaConsumer(
            "prana.ingest.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
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
                except Exception:
                    log.exception("WorkflowConsumer error event_type=%s document_id=%s",
                                  etype, event.get("document_id"))
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

        # Fetch S3 key from DB — the file is still in staging/documents bucket
        # WorkflowConsumer has read-only DB access via the app's existing pool
        # (injected via settings; re-use the same asyncpg DSN prana-api uses)
        import asyncpg
        from config import get_settings
        settings = get_settings()
        db = await asyncpg.connect(settings.db_dsn)
        try:
            row = await db.fetchrow(
                "SELECT s3_key, s3_bucket FROM document WHERE document_id=$1", doc_id
            )
        finally:
            await db.close()

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
