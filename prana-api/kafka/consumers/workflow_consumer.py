"""
WorkflowConsumer — prana.ingest.events

Listens for DOC_INGESTED, BATCH_UPLOADED, DOC_RECLASSIFIED, DOC_ROUTED, and
DOMAIN_VERIFICATION_REQUESTED events. Starts Temporal workflows so the HTTP
handler never has to.

DOC_INGESTED                  → DocumentPipelineWorkflow + BatchTimeoutMonitorWorkflow (per file)
BATCH_UPLOADED                → BatchProgressWorkflow (parent tracker, only when batch_id present)
DOC_RECLASSIFIED              → DocumentPipelineWorkflow restart with OA-Admin resolved doc_type
DOC_ROUTED                    → GamificationRefreshWorkflow (badge/score refresh for the employee)
DOMAIN_VERIFICATION_REQUESTED → DomainVerificationWorkflow (tenant onboarding)
"""
import asyncio
import logging

from aiokafka import AIOKafkaConsumer

from config import Settings
from workflows.document_pipeline import DocumentPipelineWorkflow, TASK_QUEUE
from workflows.batch_progress import BatchProgressWorkflow, BatchTimeoutMonitorWorkflow, BATCH_TASK_QUEUE
from workflows.gamification import GamificationRefreshWorkflow
from workflows.tenant import DomainVerificationWorkflow, TASK_QUEUE as TENANT_TASK_QUEUE

# Must match the queue GamificationRefreshWorkflow is registered on in workflows/worker.py.
# Previously "prana-analytics" — a queue no worker polls, so the workflow never ran.
GAMIFICATION_TASK_QUEUE = "insight-queue"

log = logging.getLogger(__name__)

GROUP_ID = "prana-workflow-consumer"


class WorkflowConsumer:
    def __init__(self, settings: Settings, temporal_client, db_pool=None) -> None:
        self._settings = settings
        self._temporal = temporal_client
        self._db_pool = db_pool
        limit = getattr(settings, "max_concurrent_workflow_starts", 50)
        self._wf_semaphore = asyncio.Semaphore(limit)
        self._consumer = AIOKafkaConsumer(
            "prana.ingest.events",
            "prana.pipeline.events",
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
                    elif etype == "DOC_ROUTED":
                        await self._handle_doc_routed(event)
                    elif etype == "DOMAIN_VERIFICATION_REQUESTED":
                        await self._handle_domain_verification_requested(event)
                    else:
                        log.debug("WorkflowConsumer: no handler for event_type=%s", etype)
                except Exception as exc:
                    from kafka.error_capture import record_consumer_error
                    await record_consumer_error(
                        self._db_pool, consumer_name="WorkflowConsumer", exc=exc, event_type=etype,
                    )
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

        # Semaphore caps concurrent Temporal API calls during burst ingest (e.g. 20K batch).
        # Without it, all start_workflow calls fire simultaneously and saturate the Temporal frontend.
        async with self._wf_semaphore:
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

    async def _handle_doc_routed(self, event: dict) -> None:
        """DOC_ROUTED → refresh gamification score + award new badges for this employee."""
        employee_user_id = event.get("employee_user_id")
        document_id      = event.get("document_id")
        if not employee_user_id:
            log.warning("DOC_ROUTED: missing employee_user_id — skipping gamification refresh")
            return
        wf_id = f"gamification-refresh-{employee_user_id}"
        try:
            await self._temporal.start_workflow(
                GamificationRefreshWorkflow.run,
                employee_user_id,
                id=wf_id,
                task_queue=GAMIFICATION_TASK_QUEUE,
            )
        except Exception as exc:
            if "already" not in str(exc).lower():
                log.exception("GamificationRefreshWorkflow start failed emp=%s doc=%s", employee_user_id, document_id)

    async def _handle_domain_verification_requested(self, event: dict) -> None:
        tenant_id = event["tenant_id"]
        domain    = event["domain"]
        workflow_id = event.get("workflow_id", f"domain-verify-{tenant_id}")

        # Idempotent: a retry re-publishes with a distinct workflow_id suffix
        # (see routers/pa_admin.py's retry_verification); the original
        # workflow_id is reused for the first attempt so duplicate
        # DOMAIN_VERIFICATION_REQUESTED deliveries don't start two runs.
        try:
            await self._temporal.start_workflow(
                DomainVerificationWorkflow.run,
                {"tenant_id": tenant_id, "domain": domain},
                id=workflow_id,
                task_queue=TENANT_TASK_QUEUE,
            )
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
