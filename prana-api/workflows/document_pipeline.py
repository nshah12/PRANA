"""
DocumentPipelineWorkflow — thin Temporal shell.
All business logic lives in prana-ai pipeline stages (plain Python, no Temporal imports).
This file contains ONLY Temporal primitives: workflow, activities, task queue wiring.
"""
from datetime import timedelta
from temporalio import workflow, activity
from temporalio.common import RetryPolicy

TASK_QUEUE = "document-pipeline"

_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=2),
)


# ── Activity stubs (implementations live in prana-ai, called via HTTP) ────────

@activity.defn(name="stage02_encrypt")
async def stage02_encrypt(params: dict) -> dict: ...

@activity.defn(name="stage03_scan")
async def stage03_scan(params: dict) -> dict: ...

@activity.defn(name="stage04_extract")
async def stage04_extract(params: dict) -> dict: ...

@activity.defn(name="stage05_resolve")
async def stage05_resolve(params: dict) -> dict: ...

@activity.defn(name="stage06_route")
async def stage06_route(params: dict) -> dict: ...

@activity.defn(name="stage06_raise_exception")
async def stage06_raise_exception(params: dict) -> dict: ...

@activity.defn(name="stage04_write_unclassified")
async def stage04_write_unclassified(params: dict) -> dict: ...

@activity.defn(name="stage05_handle_cross_tenant_violation")
async def stage05_handle_cross_tenant_violation(params: dict) -> dict: ...

@activity.defn(name="update_pipeline_status")
async def update_pipeline_status(params: dict) -> None: ...

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
