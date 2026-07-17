"""
HRMSSyncWorkflow — thin Temporal adapter for HRMS pull sync.

Triggered by HRMSSyncScheduleWorkflow (Temporal Schedule) or manually via
the /v1/hrms/config/{id}/sync endpoint (future).

Business logic lives entirely in HRMSSyncService — zero business logic here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import activity, workflow

from services.hrms_sync_service import HRMSSyncService

_svc = HRMSSyncService()


@dataclass
class HRMSSyncInput:
    connector_id: str
    tenant_id:    str


# ── Activity ──────────────────────────────────────────────────────────────────

@activity.defn
async def run_hrms_pull(connector_id: str, tenant_id: str) -> dict:
    """Pull records from the HRMS connector and publish to Kafka."""
    import asyncpg
    import os
    from uuid import UUID
    import boto3

    conn   = await asyncpg.connect(os.environ["DATABASE_URL"])
    kms    = boto3.client("kms", region_name="ap-south-1")

    # kafka.producer has no "KafkaProducer" class (that's aiokafka's raw API,
    # not this project's wrapper) — the real producer is KafkaPub, obtained
    # via get_kafka_producer(). _svc.run_pull_sync calls kafka.employee_event(...),
    # a KafkaPub method, so this must return a KafkaPub instance, not a raw
    # aiokafka producer even if one were constructed correctly.
    from kafka.producer import get_kafka_producer
    kafka = await get_kafka_producer()

    # workflow.info()/workflow.in_workflow() don't exist — this runs as an
    # ACTIVITY, not workflow code, so the run id (if any) comes from
    # activity.info(), which raises RuntimeError outside an activity context
    # (e.g. called directly in a unit test).
    try:
        temporal_run_id = activity.info().workflow_run_id
    except RuntimeError:
        temporal_run_id = None

    try:
        return await _svc.run_pull_sync(
            connector_id=UUID(connector_id),
            tenant_id=UUID(tenant_id),
            db=conn,
            kms=kms,
            kafka=kafka,
            temporal_run_id=temporal_run_id,
        )
    finally:
        await conn.close()


# ── Workflow shell (<20 lines) ────────────────────────────────────────────────

@workflow.defn
class HRMSSyncWorkflow:
    @workflow.run
    async def run(self, inp: HRMSSyncInput) -> dict:
        return await workflow.execute_activity(
            run_hrms_pull,
            args=[inp.connector_id, inp.tenant_id],
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=workflow.RetryPolicy(maximum_attempts=3),
        )
