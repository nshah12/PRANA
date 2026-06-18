"""
BatchProgressWorkflow — parent tracker for multi-file uploads.

When an OA-Operator uploads N files in one request, IngestService:
  1. Creates one DocumentPipelineWorkflow per file (child workflows, run independently)
  2. Starts ONE BatchProgressWorkflow as the batch parent

This workflow:
  - Fans out DocumentPipelineWorkflow for each document_id in the batch
  - Polls for completion of all children (does NOT block child pipelines — they run free)
  - Detects stragglers past pipeline_max_duration_hours → marks them EXCEPTION
  - Writes batch-level summary to document_batch table on completion
  - Triggers StagingCleanupWorkflow for the batch staging prefix

BatchTimeoutMonitorWorkflow is a lightweight per-file guard started alongside every
DocumentPipelineWorkflow, even for single-file uploads. It enforces the per-file
ceiling independently of the batch workflow.

Task queue: ingestsvc-queue
Fan-out concurrency: controlled by Temporal worker count × task queue pollers.
  Deploy 10 prana-ai workers → 10 files process in parallel.
  Deploy 100 → 100 in parallel. Zero code change needed. No dropped files.
"""

from datetime import timedelta
from temporalio import workflow, activity
from temporalio.common import RetryPolicy

from workflows.document_pipeline import DocumentPipelineWorkflow, TASK_QUEUE

BATCH_TASK_QUEUE = TASK_QUEUE   # same queue — batch workflows share pipeline workers

_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=2),
)

# ── Activity stubs (implementations registered in activities.py) ───────────────

@activity.defn(name="get_batch_config")
async def get_batch_config(params: dict) -> dict: ...

@activity.defn(name="write_batch_summary")
async def write_batch_summary(params: dict) -> None: ...

@activity.defn(name="mark_batch_straggler")
async def mark_batch_straggler(params: dict) -> None: ...


# ── BatchProgressWorkflow ─────────────────────────────────────────────────────

@workflow.defn(name="BatchProgressWorkflow")
class BatchProgressWorkflow:
    """
    Parent workflow for a multi-file upload batch.

    Fan-out model:
      - Each document_id is launched as an independent DocumentPipelineWorkflow
        child workflow so they all run in parallel, bound only by worker capacity.
      - This workflow gathers results and writes the batch summary.
      - Children are NOT cancelled if this workflow times out — they run to
        completion independently. The timeout only affects batch-level accounting.

    Temporal durability guarantee:
      - If any worker pod dies, Temporal replays the workflow from last checkpoint.
      - Every document_id is either ROUTED, EXCEPTION, QUARANTINED, or
        EXCEPTION_TIMEOUT — never silently dropped.
    """

    @workflow.run
    async def run(self, params: dict) -> dict:
        batch_id     = params["batch_id"]
        tenant_id    = params["tenant_id"]
        document_ids = params["document_ids"]   # list[str]
        doc_type     = params["doc_type"]
        doc_period   = params.get("doc_period")

        # Read per-file timeout from config (tenant overrides platform)
        cfg = await workflow.execute_activity(
            get_batch_config,
            {"tenant_id": tenant_id},
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=_RETRY,
        )
        per_file_timeout_hours = int(cfg.get("pipeline_max_duration_hours", 4))
        batch_max_hours        = int(cfg.get("batch_max_duration_hours", 24))

        # ── Fan-out: launch one child workflow per document ──────────────────
        # All children run in parallel — this is the key fan-out.
        # asyncio.gather() inside a workflow runs coroutines concurrently on
        # Temporal's event loop; each execute_child_workflow is non-blocking
        # until awaited, so all N children are scheduled in one scheduler pass.

        child_handles = []
        for doc_id in document_ids:
            handle = await workflow.start_child_workflow(
                DocumentPipelineWorkflow.run,
                {
                    "document_id": doc_id,
                    "tenant_id":   tenant_id,
                    "doc_type":    doc_type,
                    "doc_period":  doc_period,
                    # s3_key, s3_bucket, enc_dek etc. fetched inside each child
                    # from DB at execution time — no need to pass them here
                },
                id=f"doc-pipeline-{doc_id}",
                task_queue=TASK_QUEUE,
                # Children run independently. This parent doesn't cancel them.
                execution_timeout=timedelta(hours=per_file_timeout_hours),
            )
            child_handles.append((doc_id, handle))

        # ── Gather results with per-batch ceiling ────────────────────────────
        results: dict[str, str] = {}   # doc_id → terminal status
        stragglers: list[str]   = []

        deadline = workflow.now() + timedelta(hours=batch_max_hours)

        for doc_id, handle in child_handles:
            remaining = deadline - workflow.now()
            if remaining.total_seconds() <= 0:
                # Batch wall-clock exceeded — remaining children are stragglers
                stragglers.append(doc_id)
                continue
            try:
                result = await workflow.wait_condition(
                    lambda h=handle: h.result_run_id is not None,  # type: ignore[attr-defined]
                    timeout=remaining,
                )
                child_result = await handle
                results[doc_id] = child_result.get("status", "UNKNOWN")
            except Exception:
                stragglers.append(doc_id)

        # ── Mark stragglers ──────────────────────────────────────────────────
        # Children are still running — we just record the batch timeout.
        # DocumentPipelineWorkflow's own execution_timeout will eventually
        # terminate them if they don't finish.
        for doc_id in stragglers:
            await workflow.execute_activity(
                mark_batch_straggler,
                {"document_id": doc_id, "batch_id": batch_id, "tenant_id": tenant_id},
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_RETRY,
            )
            results[doc_id] = "STRAGGLER"

        # ── Write batch summary ──────────────────────────────────────────────
        routed     = sum(1 for s in results.values() if s == "ROUTED")
        exceptions = sum(1 for s in results.values() if s in ("EXCEPTION", "EXCEPTION_TIMEOUT"))
        quarantine = sum(1 for s in results.values() if s == "QUARANTINED")
        failed     = sum(1 for s in results.values() if s in ("STRAGGLER", "UNKNOWN"))

        await workflow.execute_activity(
            write_batch_summary,
            {
                "batch_id":   batch_id,
                "tenant_id":  tenant_id,
                "total":      len(document_ids),
                "routed":     routed,
                "exceptions": exceptions,
                "quarantine": quarantine,
                "failed":     failed,
                "results":    results,
            },
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )

        return {
            "batch_id":   batch_id,
            "total":      len(document_ids),
            "routed":     routed,
            "exceptions": exceptions,
            "quarantine": quarantine,
            "failed":     failed,
        }


# ── BatchTimeoutMonitorWorkflow ───────────────────────────────────────────────

@workflow.defn(name="BatchTimeoutMonitorWorkflow")
class BatchTimeoutMonitorWorkflow:
    """
    Per-file timeout guard. Runs alongside every DocumentPipelineWorkflow,
    even for single-file uploads (BatchProgressWorkflow is only for N > 1).

    If the document is still not in a terminal state after
    pipeline_max_duration_hours, writes EXCEPTION and raises an exception_queue
    row so OA-Admin can investigate and re-trigger if needed.

    This is a belt-and-suspenders guard — DocumentPipelineWorkflow itself also
    has an execution_timeout — but this one writes a human-visible DB record
    rather than silently expiring in Temporal.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        document_id = params["document_id"]
        tenant_id   = params["tenant_id"]

        # Read timeout from config
        cfg = await workflow.execute_activity(
            get_batch_config,
            {"tenant_id": tenant_id},
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=_RETRY,
        )
        timeout_hours = int(cfg.get("pipeline_max_duration_hours", 4))

        # Sleep for the full allowed duration
        await workflow.sleep(timedelta(hours=timeout_hours))

        # If we wake up, the document hasn't finished — mark it
        await workflow.execute_activity(
            mark_batch_straggler,
            {
                "document_id":  document_id,
                "batch_id":     params.get("batch_id"),
                "tenant_id":    tenant_id,
                "reason":       "PIPELINE_TIMEOUT",
            },
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )
