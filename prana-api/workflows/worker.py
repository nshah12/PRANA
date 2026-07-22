"""
Temporal worker process for prana-api.

Registers all 53 workflow shells across 11 task queues.
In production each task queue runs as a separate Deployment/Pod
(same image, TASK_QUEUE env var selects which worker to start).
GPU-intensive work is delegated to prana-ai via HTTP activity.

Run all queues locally (dev):
    python -m workflows.worker

Run a specific queue in production:
    TASK_QUEUE=auth-queue python -m workflows.worker
"""

import asyncio
import logging
import os
from datetime import timedelta

from temporalio.client import Client
from temporalio.worker import Worker

from workflows.error_capture_interceptor import ErrorObservabilityInterceptor
from workflows.error_threshold import ErrorThresholdEvaluationWorkflow, evaluate_error_thresholds

from config import get_settings

# ── Workflow imports ───────────────────────────────────────────────────────────

from workflows.document_pipeline import (
    DocumentPipelineWorkflow,
    EmbeddingUpdateWorkflow,
)
from workflows.batch_progress import (
    BatchProgressWorkflow,
    BatchTimeoutMonitorWorkflow,
)
from workflows.elevation import ElevationWorkflow
from workflows.tenant import (
    DomainVerificationWorkflow,
    TenantProvisioningWorkflow,
    TenantOffboardingWorkflow,
    TenantMigrationWorkflow,
)
from workflows.compliance import (
    ErasureConfirmationWorkflow,
    ConsentRebumpWorkflow,
    DataExportWorkflow,
    GrievanceWorkflow,
    DataCorrectionWorkflow,
    RetentionWorkflow,
    AuditArchivalWorkflow,
    LegalHoldWorkflow,
    StatutoryComplianceWorkflow,
)
from workflows.insight_refresh import InsightRefreshWorkflow, refresh_document_insight
from workflows.intelligence import (
    CareerInsightWorkflow,
    VaultCompletenessWorkflow,
    AnomalyAcknowledgementWorkflow,
    DigestWorkflow,
    PeerBenchmarkWorkflow,
    SkillGapWorkflow,
    MarketCompWorkflow,
)
from workflows.employee_lifecycle import (
    EmployeeExitWorkflow,
    PushWindowExpiryWorkflow,
    VaultActivationWorkflow,
    VaultHealthWorkflow,
    NomineeAccessWorkflow,
    RejoiningWorkflow,
    AccountDormancyWorkflow,
)
from workflows.security import (
    PolicyLockWorkflow,
    TOTPLockoutWorkflow,
    SessionExpiryWorkflow,
    SessionForceRevokeWorkflow,
    AnomalyDetectionWorkflow,
    KMSKeyRotationWorkflow,
    HMACSecretRotationWorkflow,
    CSAMReportingWorkflow,
)
from workflows.platform_ops import (
    PlatformSummaryWorkflow,
    ClamAVUpdateWorkflow,
    KMSHealthCheckWorkflow,
    StorageQuotaCheckWorkflow,
    StagingCleanupWorkflow,
    WebhookDeliveryWorkflow,
    NotificationDeliveryWorkflow,
    StorageExpansionWorkflow,
    OnboardingReviewSLAWorkflow,
)
from workflows.system_health import SystemHealthWorkflow
from workflows.audit_integrity import AuditIntegrityVerificationWorkflow
from workflows.vault_shares import (
    ShareExpiryWorkflow,
    ShareRevocationWorkflow,
    DocumentShareWorkflow,
)

# ── Activity imports (from activities.py and inline stubs) ─────────────────────

from workflows.activities import (
    stage02_encrypt as stage02_encrypt_impl,
    stage03_scan as stage03_scan_impl,
    stage04_extract as stage04_extract_impl,
    stage04_write_unclassified as stage04_write_unclassified_impl,
    stage05_resolve as stage05_resolve_impl,
    stage06_route as stage06_route_impl,
    stage06_raise_exception as stage06_raise_exception_impl,
    update_pipeline_status as update_pipeline_status_impl,
    get_batch_config as get_batch_config_impl,
    write_batch_summary as write_batch_summary_impl,
    mark_batch_straggler as mark_batch_straggler_impl,
    activate_elevation as activate_elevation_impl,
    finalize_elevation as finalize_elevation_impl,
    expire_elevation as expire_elevation_impl,
    get_tenant_onboarding_config as get_tenant_onboarding_config_impl,
    check_dns_txt_record as check_dns_txt_record_impl,
    mark_tenant_verification_failed as mark_tenant_verification_failed_impl,
    get_tenant_onboarding_tier as get_tenant_onboarding_tier_impl,
    provision_tenant as provision_tenant_impl,
    # ACTIVITY-01 fix (2026-07-17): these 9 + get_config_value were previously
    # imported from workflows.compliance below, which registered that module's
    # bare `...` stubs instead of these real ComplianceService-backed bodies —
    # every workflow using them (ErasureConfirmationWorkflow, GrievanceWorkflow,
    # DataExportWorkflow, ConsentRebumpWorkflow) silently did nothing on Temporal.
    send_erasure_notice as send_erasure_notice_impl,
    execute_erasure as execute_erasure_impl,
    send_consent_rebump as send_consent_rebump_impl,
    check_consent_status as check_consent_status_impl,
    build_data_export as build_data_export_impl,
    notify_export_ready as notify_export_ready_impl,
    open_grievance as open_grievance_impl,
    escalate_grievance as escalate_grievance_impl,
    close_grievance as close_grievance_impl,
    get_config_value as get_config_value_impl,
)

# Stub activities from domain modules (registered by function reference)
from workflows.compliance import (
    apply_data_correction, notify_correction_complete,
    schedule_document_deletion, archive_audit_events_batch,
    apply_legal_hold, release_legal_hold,
    mark_overdue_obligations, notify_overdue_obligations,
)
from workflows.intelligence import (
    build_career_insight, write_career_insight,
    score_vault_completeness, write_vault_completeness,
    record_anomaly_ack, build_weekly_digest, build_monthly_digest,
    send_digest_email, build_peer_benchmark, write_peer_benchmark,
    build_skill_gap_analysis, write_skill_gap,
    build_market_comp, write_market_comp,
)
from workflows.employee_lifecycle import (
    freeze_employee_vault, notify_exit_employee, start_retention_workflow,
    close_push_window, provision_vault, send_vault_welcome,
    recompute_vault_completeness, grant_nominee_access, revoke_nominee_access,
    reconcile_rejoining_employee, flag_dormant_account, get_lifecycle_config,
)
from workflows.security import (
    apply_policy_lock, release_policy_lock, notify_policy_lock,
    apply_totp_lockout, release_totp_lockout,
    expire_session, force_revoke_session,
    run_anomaly_detection_batch, rotate_tenant_kek, rotate_hmac_secret,
    get_next_tenant_for_rotation, report_csam_to_ncmec,
    apply_csam_legal_hold, notify_csam_platform_admin, get_security_config,
)
from workflows.platform_ops import (
    collect_platform_metrics, write_platform_summary,
    pull_clamav_signatures, verify_kms_key_health, alert_kms_key_issue,
    check_tenant_storage_quotas, alert_storage_quota, purge_stale_staging_objects,
    deliver_webhook, mark_webhook_failed, deliver_notification,
    deliver_notification_fallback,
    get_ops_config,
    notify_storage_expansion_request, apply_storage_expansion, reject_storage_expansion,
    escalate_onboarding_review,
)
from workflows.system_health import run_health_checks
from workflows.audit_integrity import verify_audit_integrity
from workflows.vault_shares import (
    expire_share_token, revoke_share_token, create_share_token,
    send_share_otp, notify_share_accessed, get_share_config,
)
from workflows.gamification import GamificationRefreshWorkflow, recalculate_and_persist
from workflows.hrms_sync import HRMSSyncWorkflow, run_hrms_pull
from workflows.hrms_sync_schedule import HRMSSyncScheduleWorkflow, run_ensure_hrms_schedules

log = logging.getLogger(__name__)

# ── Worker definitions (one per task queue) ────────────────────────────────────

WORKERS: dict[str, dict] = {
    "ingestsvc-queue": {
        "workflows": [
            DocumentPipelineWorkflow,
            BatchProgressWorkflow,
            BatchTimeoutMonitorWorkflow,
            ClamAVUpdateWorkflow,
            StagingCleanupWorkflow,
        ],
        "activities": [
            stage02_encrypt_impl, stage03_scan_impl, stage04_extract_impl,
            stage04_write_unclassified_impl,
            stage05_resolve_impl, stage06_route_impl, stage06_raise_exception_impl,
            update_pipeline_status_impl, get_batch_config_impl,
            write_batch_summary_impl, mark_batch_straggler_impl,
            pull_clamav_signatures, purge_stale_staging_objects,
        ],
    },
    "resolution-queue": {
        "workflows": [EmbeddingUpdateWorkflow],
        "activities": [],  # activities registered by prana-ai worker
    },
    "resolution-low-priority-queue": {
        "workflows": [EmbeddingUpdateWorkflow],
        "activities": [],
    },
    "admin-queue": {
        "workflows": [
            ElevationWorkflow,
            DomainVerificationWorkflow, TenantProvisioningWorkflow,
            TenantOffboardingWorkflow, TenantMigrationWorkflow,
            EmployeeExitWorkflow, PushWindowExpiryWorkflow,
            VaultActivationWorkflow, RejoiningWorkflow, AccountDormancyWorkflow,
            WebhookDeliveryWorkflow, NotificationDeliveryWorkflow,
            StorageExpansionWorkflow,
            OnboardingReviewSLAWorkflow,
        ],
        "activities": [
            activate_elevation_impl, finalize_elevation_impl, expire_elevation_impl,
            get_tenant_onboarding_config_impl, check_dns_txt_record_impl,
            mark_tenant_verification_failed_impl, get_tenant_onboarding_tier_impl,
            provision_tenant_impl,
            freeze_employee_vault, notify_exit_employee, start_retention_workflow,
            close_push_window, provision_vault, send_vault_welcome,
            reconcile_rejoining_employee, flag_dormant_account, get_lifecycle_config,
            deliver_webhook, mark_webhook_failed, deliver_notification,
            deliver_notification_fallback,
            get_ops_config, notify_storage_expansion_request,
            apply_storage_expansion, reject_storage_expansion,
            escalate_onboarding_review,
        ],
    },
    "vault-queue": {
        "workflows": [
            VaultHealthWorkflow, NomineeAccessWorkflow,
            ShareExpiryWorkflow, ShareRevocationWorkflow, DocumentShareWorkflow,
            VaultCompletenessWorkflow,
        ],
        "activities": [
            recompute_vault_completeness, grant_nominee_access, revoke_nominee_access,
            score_vault_completeness, write_vault_completeness,
            expire_share_token, revoke_share_token, create_share_token,
            send_share_otp, notify_share_accessed, get_share_config,
        ],
    },
    "auth-queue": {
        "workflows": [
            TOTPLockoutWorkflow, SessionExpiryWorkflow, SessionForceRevokeWorkflow,
        ],
        "activities": [
            apply_totp_lockout, release_totp_lockout,
            expire_session, force_revoke_session, get_security_config,
        ],
    },
    "secops-queue": {
        "workflows": [
            PolicyLockWorkflow, AnomalyDetectionWorkflow,
            KMSKeyRotationWorkflow, HMACSecretRotationWorkflow,
            KMSHealthCheckWorkflow, SystemHealthWorkflow,
            AuditIntegrityVerificationWorkflow, ErrorThresholdEvaluationWorkflow,
        ],
        "activities": [
            apply_policy_lock, release_policy_lock, notify_policy_lock,
            run_anomaly_detection_batch, rotate_tenant_kek, rotate_hmac_secret,
            run_health_checks, verify_audit_integrity, evaluate_error_thresholds,
            get_next_tenant_for_rotation, verify_kms_key_health, alert_kms_key_issue,
            get_security_config,
        ],
    },
    "safety-queue": {
        "workflows": [CSAMReportingWorkflow],
        "activities": [
            report_csam_to_ncmec, apply_csam_legal_hold, notify_csam_platform_admin,
        ],
    },
    "compliance-queue": {
        "workflows": [
            ErasureConfirmationWorkflow, ConsentRebumpWorkflow,
            DataExportWorkflow, GrievanceWorkflow,
            DataCorrectionWorkflow, RetentionWorkflow,
            AuditArchivalWorkflow, LegalHoldWorkflow,
            StatutoryComplianceWorkflow,
        ],
        "activities": [
            send_erasure_notice_impl, execute_erasure_impl, send_consent_rebump_impl,
            check_consent_status_impl, build_data_export_impl, notify_export_ready_impl,
            open_grievance_impl, escalate_grievance_impl, close_grievance_impl,
            apply_data_correction, notify_correction_complete,
            schedule_document_deletion, archive_audit_events_batch,
            apply_legal_hold, release_legal_hold, get_config_value_impl,
            mark_overdue_obligations, notify_overdue_obligations,
        ],
    },
    "analytics-queue": {
        "workflows": [
            PlatformSummaryWorkflow, StorageQuotaCheckWorkflow,
        ],
        "activities": [
            collect_platform_metrics, write_platform_summary,
            check_tenant_storage_quotas, alert_storage_quota, get_ops_config,
        ],
    },
    "insight-queue": {
        "workflows": [
            InsightRefreshWorkflow,
            CareerInsightWorkflow, AnomalyAcknowledgementWorkflow,
            DigestWorkflow, PeerBenchmarkWorkflow, SkillGapWorkflow, MarketCompWorkflow,
            GamificationRefreshWorkflow,
        ],
        "activities": [
            refresh_document_insight,
            build_career_insight, write_career_insight,
            record_anomaly_ack, build_weekly_digest, build_monthly_digest,
            send_digest_email, build_peer_benchmark, write_peer_benchmark,
            build_skill_gap_analysis, write_skill_gap,
            build_market_comp, write_market_comp,
            recalculate_and_persist,   # GamificationRefreshWorkflow
        ],
    },
    "resolution-queue-analytics": {
        "workflows": [VaultCompletenessWorkflow],
        "activities": [score_vault_completeness, write_vault_completeness],
    },
    # HRMS pull sync (schedule-driven) + the schedule-ensurer workflow.
    "hrms-queue": {
        "workflows": [HRMSSyncWorkflow, HRMSSyncScheduleWorkflow],
        "activities": [run_hrms_pull, run_ensure_hrms_schedules],
    },
}


async def start_worker(client: Client, queue: str, cfg: dict) -> None:
    worker = Worker(
        client,
        task_queue=queue,
        workflows=cfg["workflows"],
        activities=cfg["activities"],
        # Records every failed activity attempt to error_event (deduplicated by
        # fingerprint) — see prana-docs/ERROR_OBSERVABILITY_DESIGN.md §4C.
        interceptors=[ErrorObservabilityInterceptor()],
    )
    log.info("Starting worker on queue: %s (%d workflows, %d activities)",
             queue, len(cfg["workflows"]), len(cfg["activities"]))
    await worker.run()


async def main() -> None:
    settings = get_settings()
    log.info("Connecting to Temporal at %s", settings.temporal_host)
    client = await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
    )

    # In production: TASK_QUEUE env var selects a single worker.
    # In dev: run all workers concurrently.
    selected_queue = os.environ.get("TASK_QUEUE")
    if selected_queue:
        if selected_queue not in WORKERS:
            raise ValueError(f"Unknown TASK_QUEUE: {selected_queue!r}. "
                             f"Valid: {list(WORKERS)}")
        await start_worker(client, selected_queue, WORKERS[selected_queue])
    else:
        log.info("TASK_QUEUE not set — starting all %d workers (dev mode)", len(WORKERS))
        await asyncio.gather(*[
            start_worker(client, q, cfg) for q, cfg in WORKERS.items()
        ])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
