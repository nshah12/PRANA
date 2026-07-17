"""
DocumentPipelineWorkflow — thin Temporal shell.
Stage activities (stage02-06) are implemented once in workflows/activities.py
and imported here directly — not redeclared — so there is exactly one
@activity.defn per name and no risk of a duplicate stub shadowing the real
implementation (see scripts/enforce_rules.py's ACTIVITY-01 check, added after
exactly that bug shipped in workflows/compliance.py). Stages 03-06 call
prana-ai via HTTP internally; stage02 (encryption) runs locally since it needs
KMS access, which prana-ai does not have.
"""
from datetime import timedelta
from temporalio import workflow, activity
from temporalio.common import RetryPolicy

from workflows.activities import (
    stage02_encrypt,
    stage03_scan,
    stage04_extract,
    stage04_write_unclassified,
    stage05_resolve,
    stage05_handle_cross_tenant_violation,
    stage06_route,
    stage06_raise_exception,
    update_pipeline_status,
)

# Must match worker.py's WORKERS dict key exactly — this constant is imported by
# workflow_consumer.py (DocumentPipelineWorkflow/BatchTimeoutMonitorWorkflow starts)
# and by batch_progress.py (BatchProgressWorkflow's own child-workflow starts), so a
# wrong value here silently breaks every document upload: start_workflow() never
# validates a queue has a listening worker, so nothing errors — the document simply
# never leaves pipeline_status=QUEUED. See scripts/enforce_rules.py's QUEUE-01 check.
TASK_QUEUE = "ingestsvc-queue"

_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=2),
)


# ── EmbeddingUpdateWorkflow's activities are registered by prana-ai's own ────
# worker process on this same task queue (see worker.py's "resolution-queue"
# entry: "activities": [] # activities registered by prana-ai worker) — prana-
# api never registers a compute_document_embedding/write_document_embedding
# implementation, and must not: doing so from prana-api would create the exact
# duplicate-registration hazard this file's stage02-06 activities used to have
# (see the import block above), just in the opposite direction.
@activity.defn(name="compute_document_embedding")
async def compute_document_embedding(params: dict) -> dict: ...

@activity.defn(name="write_document_embedding")
async def write_document_embedding(params: dict) -> None: ...


# ── Workflow ──────────────────────────────────────────────────────────────────

@workflow.defn(name="DocumentPipelineWorkflow")
class DocumentPipelineWorkflow:
    """
    Orchestrates 6-stage document pipeline for a single document.
    Receives signal from OA-Admin to resolve exceptions (stage 05 UNRESOLVED).
    """

    def __init__(self):
        self._exception_resolution: dict | None = None

    @workflow.run
    async def run(self, params: dict) -> dict:
        doc_id = params["document_id"]
        enc  = await workflow.execute_activity(stage02_encrypt, params, start_to_close_timeout=timedelta(minutes=10), retry_policy=_RETRY)
        scan = await workflow.execute_activity(stage03_scan, {**params, **enc}, start_to_close_timeout=timedelta(minutes=15), retry_policy=_RETRY)
        if scan.get("csam_detected"):
            return await self._handle_csam(params, doc_id)
        if scan.get("virus_status") == "QUARANTINED": return {"status": "QUARANTINED", "document_id": doc_id}  # noqa: E701
        ext = await workflow.execute_activity(stage04_extract, {**params, **enc}, start_to_close_timeout=timedelta(minutes=10), retry_policy=_RETRY)
        if ext.get("status") == "unclassified":
            return await self._handle_unclassified(params, ext, doc_id)
        res = await workflow.execute_activity(stage05_resolve, {**params, **ext}, start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY)
        if res.get("violation_type") == "CROSS_TENANT":
            return await self._handle_cross_tenant(params, res, doc_id)
        if res.get("needs_exception"):
            res = await self._handle_exception_wait(params, ext, res, doc_id)
            if res is None:
                return {"status": "EXCEPTION_TIMEOUT", "document_id": doc_id}
        await workflow.execute_activity(stage06_route, {**params, **enc, **ext, **res}, start_to_close_timeout=timedelta(minutes=10), retry_policy=_RETRY)
        return {"status": "ROUTED", "document_id": doc_id}

    async def _handle_exception_wait(
        self, params: dict, ext: dict, res: dict, doc_id: str
    ) -> dict | None:
        """Raise exception, wait up to 7 days for OA-Admin signal. Returns None on timeout."""
        await workflow.execute_activity(
            stage06_raise_exception, {**params, **ext, **res},
            start_to_close_timeout=timedelta(minutes=5),
        )
        await workflow.wait_condition(
            lambda: self._exception_resolution is not None, timeout=timedelta(days=7)
        )
        return self._exception_resolution

    async def _handle_csam(self, params: dict, doc_id: str) -> dict:
        await workflow.execute_child_workflow(
            "CSAMReportingWorkflow",
            {"document_id": doc_id, "tenant_id": params["tenant_id"],
             "s3_key": params.get("s3_key"), "s3_bucket": params.get("s3_bucket")},
            task_queue="safety-queue",
            execution_timeout=timedelta(minutes=30),
        )
        return {"status": "CSAM_HOLD", "document_id": doc_id}

    async def _handle_unclassified(self, params: dict, ext: dict, doc_id: str) -> dict:
        await workflow.execute_activity(
            stage04_write_unclassified,
            {"document_id": doc_id, "tenant_id": params["tenant_id"],
             "doc_type": params.get("doc_type"),
             "best_guess_doc_type": ext.get("best_guess_doc_type"),
             "best_guess_score": ext.get("best_guess_score", 0.0),
             "partial_fields": ext.get("partial_fields", {}),
             "reason": "AUTO_DETECT_FAILED"},
            start_to_close_timeout=timedelta(minutes=5),
        )
        return {"status": "UNCLASSIFIED", "document_id": doc_id}

    async def _handle_cross_tenant(self, params: dict, res: dict, doc_id: str) -> dict:
        await workflow.execute_activity(
            stage05_handle_cross_tenant_violation, {**params, **res},
            start_to_close_timeout=timedelta(minutes=5),
        )
        return {"status": "CROSS_TENANT_REJECTED", "document_id": doc_id}

    @workflow.signal(name="exception_resolved")
    def exception_resolved(self, payload: dict) -> None:
        """OA-Admin sends this signal after manually picking the correct employee."""
        self._exception_resolution = payload


# ── EmbeddingUpdateWorkflow (resolution-queue) ────────────────────────────────

@workflow.defn(name="EmbeddingUpdateWorkflow")
class EmbeddingUpdateWorkflow:
    """
    Recomputes BAAI/bge-m3 embeddings for a document after text extraction completes.
    Used by identity resolution stage 05 (cosine similarity fallback).
    Runs on resolution-low-priority-queue to yield to pipeline traffic.
    Delegates GPU work to prana-ai via HTTP activity.
    """

    @workflow.run
    async def run(self, params: dict) -> dict:
        result = await workflow.execute_activity(
            compute_document_embedding,
            params,
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            write_document_embedding,
            {**params, **result},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )
        return result
