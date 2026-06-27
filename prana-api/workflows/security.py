"""
Security & Access Control workflows — thin Temporal shells.
Business logic lives in services/auth_service.py + services/security_service.py.

Task queues: auth-queue, secops-queue, safety-queue

Workflows:
  PolicyLockWorkflow         — apply and auto-expire a policy-based account lock
  TOTPLockoutWorkflow        — 30-min TOTP lockout after N failed attempts
  SessionExpiryWorkflow      — expire a session at its scheduled time
  SessionForceRevokeWorkflow — immediately revoke a session (CISO force-logout)
  AnomalyDetectionWorkflow   — perpetual: detect behavioural anomalies (Continue-As-New)
  KMSKeyRotationWorkflow     — perpetual: rotate tenant KEKs on schedule
  HMACSecretRotationWorkflow — perpetual: rotate platform HMAC secret
  CSAMReportingWorkflow      — report CSAM detection to NCMEC + legal_hold
"""
from datetime import datetime, timedelta, timezone

from temporalio import workflow, activity
from temporalio.common import RetryPolicy

_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=10),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
)

RENEW_THRESHOLD = 5_000  # Continue-As-New before history fills


# ── Activities (stubs — implementations in services/security_service.py) ──────

@activity.defn(name="apply_policy_lock")
async def apply_policy_lock(params: dict) -> None: ...

@activity.defn(name="release_policy_lock")
async def release_policy_lock(params: dict) -> None: ...

@activity.defn(name="notify_policy_lock")
async def notify_policy_lock(params: dict) -> None: ...

@activity.defn(name="apply_totp_lockout")
async def apply_totp_lockout(params: dict) -> None: ...

@activity.defn(name="release_totp_lockout")
async def release_totp_lockout(params: dict) -> None: ...

@activity.defn(name="expire_session")
async def expire_session(params: dict) -> None: ...

@activity.defn(name="force_revoke_session")
async def force_revoke_session(params: dict) -> None: ...

@activity.defn(name="run_anomaly_detection_batch")
async def run_anomaly_detection_batch(params: dict) -> dict: ...

@activity.defn(name="rotate_tenant_kek")
async def rotate_tenant_kek(params: dict) -> None: ...

@activity.defn(name="rotate_hmac_secret")
async def rotate_hmac_secret(params: dict) -> None: ...

@activity.defn(name="get_next_tenant_for_rotation")
async def get_next_tenant_for_rotation(params: dict) -> dict: ...

@activity.defn(name="report_csam_to_ncmec")
async def report_csam_to_ncmec(params: dict) -> None: ...

@activity.defn(name="apply_csam_legal_hold")
async def apply_csam_legal_hold(params: dict) -> None: ...

@activity.defn(name="notify_csam_platform_admin")
async def notify_csam_platform_admin(params: dict) -> None: ...

@activity.defn(name="get_security_config")
async def get_security_config(params: dict) -> str: ...


# ── PolicyLockWorkflow (Pattern 2 — Signal-Driven Timer) ─────────────────────

@workflow.defn(name="PolicyLockWorkflow")
class PolicyLockWorkflow:
    """
    Applies a policy-based lock (BULK_ACCESS_ANOMALY, SUSPICIOUS_IP, etc.).
    Waits for 'unlock_early' signal from CISO, or auto-expires at configured duration.
    Idempotency: reversal logged in account_status_event with reversed_by_event_id set.
    """

    def __init__(self):
        self._unlocked_early = False
        self._unlocked_by: str = ""

    @workflow.signal(name="unlock_early")
    def unlock_early(self, actor_id: str) -> None:
        self._unlocked_early = True
        self._unlocked_by = actor_id

    @workflow.run
    async def run(self, params: dict) -> None:
        await self._execute(params)

    async def _execute(self, params: dict) -> None:
        hours_str = await workflow.execute_activity(
            get_security_config,
            {"key": "policy_lock_default_hours",
             "tenant_id": params.get("tenant_id"), "default": "24"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        for act, timeout in [(apply_policy_lock, 5), (notify_policy_lock, 5)]:
            await workflow.execute_activity(
                act, params,
                start_to_close_timeout=timedelta(minutes=timeout), retry_policy=_RETRY,
            )
        unlocked = await workflow.wait_condition(
            lambda: self._unlocked_early, timeout=timedelta(hours=int(hours_str)),
        )
        await workflow.execute_activity(
            release_policy_lock,
            {**params, "unlocked_by": self._unlocked_by,
             "early": unlocked and self._unlocked_early},
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
        )


# ── TOTPLockoutWorkflow (Pattern 1 — Durable Timer) ──────────────────────────

@workflow.defn(name="TOTPLockoutWorkflow")
class TOTPLockoutWorkflow:
    """
    N failed TOTP attempts → 30-min lockout (duration from config).
    Separate from PolicyLockWorkflow: lighter, user-self-recoverable via time.
    Portal Admin threshold = 3 attempts (not 5) per CLAUDE.md.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        minutes_str = await workflow.execute_activity(
            get_security_config,
            {"key": "totp_lockout_cooldown_minutes", "tenant_id": params.get("tenant_id"), "default": "30"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        await workflow.execute_activity(
            apply_totp_lockout, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )
        await workflow.sleep(timedelta(minutes=int(minutes_str)))
        await workflow.execute_activity(
            release_totp_lockout, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )


# ── SessionExpiryWorkflow (Pattern 1 — Durable Timer) ────────────────────────

@workflow.defn(name="SessionExpiryWorkflow")
class SessionExpiryWorkflow:
    """
    Schedules session expiry at `expires_at` timestamp.
    When timer fires, marks session as expired in user_session table.
    Avoids polling — one workflow per session, fires exactly once.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        await self._execute(params)

    async def _execute(self, params: dict) -> None:
        expires_at   = datetime.fromisoformat(params["expires_at"]).replace(tzinfo=timezone.utc)
        wait_seconds = max(0, (expires_at - workflow.now()).total_seconds())
        if wait_seconds > 0:
            await workflow.sleep(timedelta(seconds=wait_seconds))
        await workflow.execute_activity(
            expire_session, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )


# ── SessionForceRevokeWorkflow (Pattern 1 — fast, immediate) ─────────────────

@workflow.defn(name="SessionForceRevokeWorkflow")
class SessionForceRevokeWorkflow:
    """
    CISO-initiated force-logout. Immediately revokes the target session.
    Thin wrapper so force-revoke appears in audit trail via Temporal history.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        await workflow.execute_activity(
            force_revoke_session, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )


# ── AnomalyDetectionWorkflow (Pattern 4 — Continue-As-New, perpetual) ────────

@workflow.defn(name="AnomalyDetectionWorkflow")
class AnomalyDetectionWorkflow:
    """
    Perpetual batch anomaly detection: bulk access, off-hours logins, IP anomalies.
    Runs every platform_anomaly_check_minutes (default: 5).
    Restarts via Continue-As-New every RENEW_THRESHOLD batches to keep history bounded.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        batches_run = params.get("batches_run", 0)

        while batches_run < RENEW_THRESHOLD:
            interval_str = await workflow.execute_activity(
                get_security_config,
                {"key": "platform_anomaly_check_minutes", "default": "5"},
                start_to_close_timeout=timedelta(minutes=2),
            )
            await workflow.execute_activity(
                run_anomaly_detection_batch, params,
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=_RETRY,
            )
            await workflow.sleep(timedelta(minutes=int(interval_str)))
            batches_run += 1

        workflow.continue_as_new({**params, "batches_run": 0})


# ── KMSKeyRotationWorkflow (Pattern 4 — Continue-As-New, perpetual) ──────────

@workflow.defn(name="KMSKeyRotationWorkflow")
class KMSKeyRotationWorkflow:
    """
    Rotates tenant KEKs on a configurable schedule (default: 365 days).
    Iterates over all tenants one-at-a-time. Continue-As-New after RENEW_THRESHOLD rotations.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        rotations_done = params.get("rotations_done", 0)
        while rotations_done < RENEW_THRESHOLD:
            interval_str = await workflow.execute_activity(
                get_security_config, {"key": "kek_rotation_interval_days", "default": "365"},
                start_to_close_timeout=timedelta(minutes=2),
            )
            tenant = await workflow.execute_activity(
                get_next_tenant_for_rotation, params,
                start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
            )
            if tenant.get("tenant_id"):
                await workflow.execute_activity(
                    rotate_tenant_kek, tenant,
                    start_to_close_timeout=timedelta(minutes=30),
                    retry_policy=RetryPolicy(maximum_attempts=5),
                )
            else:
                await workflow.sleep(timedelta(days=int(interval_str)))
            rotations_done += 1
        workflow.continue_as_new({**params, "rotations_done": 0})


# ── HMACSecretRotationWorkflow (Pattern 4 — Continue-As-New, perpetual) ──────

@workflow.defn(name="HMACSecretRotationWorkflow")
class HMACSecretRotationWorkflow:
    """
    Rotates the platform-wide HMAC secret used to derive pan_token.
    On rotation: re-derives all pan_tokens (batch re-hash) + updates Redis cache.
    Runs once per rotation cycle (default: 180 days). Continue-As-New.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        rotations_done = params.get("rotations_done", 0)

        while rotations_done < RENEW_THRESHOLD:
            interval_str = await workflow.execute_activity(
                get_security_config,
                {"key": "hmac_rotation_interval_days", "default": "180"},
                start_to_close_timeout=timedelta(minutes=2),
            )
            await workflow.sleep(timedelta(days=int(interval_str)))
            await workflow.execute_activity(
                rotate_hmac_secret, params,
                start_to_close_timeout=timedelta(hours=2),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            rotations_done += 1

        workflow.continue_as_new({**params, "rotations_done": 0})


# ── CSAMReportingWorkflow (Pattern 1 — fast, safety-queue) ───────────────────

@workflow.defn(name="CSAMReportingWorkflow")
class CSAMReportingWorkflow:
    """
    Triggered immediately when ClamAV/PhotoDNA flags CSAM in stage 03.
    Actions (in order, all mandatory):
      1. Apply legal_hold to document and employee account
      2. Report to NCMEC CyberTipline (mandatory under POCSO + IT Act)
      3. Notify Platform Admin
    Fast path — no sleeping, no signals. Must complete quickly.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        await workflow.execute_activity(
            apply_csam_legal_hold, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=10),  # must not fail
        )
        await workflow.execute_activity(
            report_csam_to_ncmec, params,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=10),
        )
        await workflow.execute_activity(
            notify_csam_platform_admin, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )
