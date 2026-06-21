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
        document_id = params["document_id"]
        tenant_id   = params["tenant_id"]

        await workflow.execute_activity(
            update_pipeline_status,
            {"document_id": document_id, "status": "ENCRYPTING"},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )

        # Stage 02
        enc_result = await workflow.execute_activity(
            stage02_encrypt, params,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )

        # Stage 03
        await workflow.execute_activity(
            update_pipeline_status,
            {"document_id": document_id, "status": "SCANNING"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        scan_result = await workflow.execute_activity(
            stage03_scan, {**params, **enc_result},
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=_RETRY,
        )
        if scan_result.get("csam_detected"):
            return {"status": "CSAM_HOLD", "document_id": document_id}
        if scan_result.get("virus_status") == "QUARANTINED":
            return {"status": "QUARANTINED", "document_id": document_id}

        # Stage 04
        await workflow.execute_activity(
            update_pipeline_status,
            {"document_id": document_id, "status": "EXTRACTING"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        extract_result = await workflow.execute_activity(
            stage04_extract, {**params, **enc_result},
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )

        # AUTO_DETECT failed — doc type unknown, OA-Admin must classify manually
        if extract_result.get("status") == "unclassified":
            await workflow.execute_activity(
                update_pipeline_status,
                {"document_id": document_id, "status": "UNCLASSIFIED"},
                start_to_close_timeout=timedelta(minutes=2),
            )
            await workflow.execute_activity(
                stage04_write_unclassified,
                {
                    "document_id":        document_id,
                    "tenant_id":          tenant_id,
                    "doc_type":           params.get("doc_type"),
                    "best_guess_doc_type": extract_result.get("best_guess_doc_type"),
                    "best_guess_score":    extract_result.get("best_guess_score", 0.0),
                    "partial_fields":      extract_result.get("partial_fields", {}),
                    "reason":              "AUTO_DETECT_FAILED",
                },
                start_to_close_timeout=timedelta(minutes=5),
            )
            return {"status": "UNCLASSIFIED", "document_id": document_id}

        # Stage 05
        await workflow.execute_activity(
            update_pipeline_status,
            {"document_id": document_id, "status": "RESOLVING"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        resolve_result = await workflow.execute_activity(
            stage05_resolve, {**params, **extract_result},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )

        # Cross-tenant contamination — reject, write anomaly, alert CISO + PA Admin
        if resolve_result.get("violation_type") == "CROSS_TENANT":
            await workflow.execute_activity(
                stage05_handle_cross_tenant_violation,
                {**params, **resolve_result},
                start_to_close_timeout=timedelta(minutes=5),
            )
            return {"status": "CROSS_TENANT_REJECTED", "document_id": document_id}

        # Exception path: wait up to 7 days for OA-Admin signal
        if resolve_result.get("needs_exception"):
            await workflow.execute_activity(
                stage06_raise_exception, {**params, **extract_result, **resolve_result},
                start_to_close_timeout=timedelta(minutes=5),
            )
            # Wait for exception_resolved signal (OA-Admin picks employee_uuid)
            await workflow.wait_condition(
                lambda: self._exception_resolution is not None,
                timeout=timedelta(days=7),
            )
            if self._exception_resolution is None:
                return {"status": "EXCEPTION_TIMEOUT", "document_id": document_id}
            resolve_result = self._exception_resolution

        # Stage 06
        route_result = await workflow.execute_activity(
            stage06_route, {**params, **enc_result, **extract_result, **resolve_result},
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY,
        )

        # Fire-and-forget: generate LLM insight + embed into Qdrant
        # Runs on insight-queue independently — pipeline doesn't wait for it
        await workflow.execute_child_workflow(
            "InsightRefreshWorkflow",
            {
                "document_id": document_id,
                "employee_uuid": resolve_result.get("employee_uuid"),
                "doc_type": params.get("doc_type"),
                "doc_period": params.get("doc_period"),
                "benchmarks": route_result.get("benchmarks", {}),
            },
            task_queue="insight-queue",
            execution_timeout=timedelta(minutes=15),
        )

        return {"status": "ROUTED", "document_id": document_id}

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
        from temporalio.common import RetryPolicy
        result = await workflow.execute_activity(
            "compute_document_embedding",
            params,
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        await workflow.execute_activity(
            "write_document_embedding",
            {**params, **result},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        return result
