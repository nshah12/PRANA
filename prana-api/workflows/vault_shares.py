"""
Vault & Shares workflows — thin Temporal shells.
Business logic lives in services/vault_service.py.

Task queue: vault-queue

Workflows:
  ShareExpiryWorkflow     — expire a share token at its scheduled time (durable timer)
  ShareRevocationWorkflow — immediately revoke a share token (user-initiated)
  DocumentShareWorkflow   — create a share token with OTP verification flow
"""
from datetime import timedelta

from temporalio import workflow, activity
from temporalio.common import RetryPolicy

_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=10),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
)


# ── Activities (stubs — implementations in services/vault_service.py) ─────────

@activity.defn(name="expire_share_token")
async def expire_share_token(params: dict) -> None: ...

@activity.defn(name="revoke_share_token")
async def revoke_share_token(params: dict) -> None: ...

@activity.defn(name="create_share_token")
async def create_share_token(params: dict) -> dict: ...

@activity.defn(name="send_share_otp")
async def send_share_otp(params: dict) -> None: ...

@activity.defn(name="notify_share_accessed")
async def notify_share_accessed(params: dict) -> None: ...

@activity.defn(name="get_share_config")
async def get_share_config(params: dict) -> str: ...


# ── ShareExpiryWorkflow (Pattern 1 — Durable Timer) ──────────────────────────

@workflow.defn(name="ShareExpiryWorkflow")
class ShareExpiryWorkflow:
    """
    Schedules expiry of a share token at its `expires_at` timestamp.
    Started when a share is created (POST /vault/shares).
    When the timer fires: marks share_token as expired in DB + invalidates Redis cache entry.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        from datetime import datetime, timezone
        expires_at = datetime.fromisoformat(params["expires_at"]).replace(tzinfo=timezone.utc)
        now = workflow.now()
        wait_seconds = max(0, (expires_at - now).total_seconds())
        if wait_seconds > 0:
            await workflow.sleep(timedelta(seconds=wait_seconds))
        await workflow.execute_activity(
            expire_share_token, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )


# ── ShareRevocationWorkflow (Pattern 1 — fast, immediate) ────────────────────

@workflow.defn(name="ShareRevocationWorkflow")
class ShareRevocationWorkflow:
    """
    Employee revokes a share link (DELETE /vault/shares/{token_id}).
    Immediately invalidates the token in DB + Redis cache.
    Thin wrapper so revocation appears in Temporal audit trail.
    """

    @workflow.run
    async def run(self, params: dict) -> None:
        await workflow.execute_activity(
            revoke_share_token, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )


# ── DocumentShareWorkflow (Pattern 2 — Signal-Driven, with OTP) ──────────────

@workflow.defn(name="DocumentShareWorkflow")
class DocumentShareWorkflow:
    """
    Creates a share token and sends an OTP to the recipient's mobile.
    Waits for OTP verification via 'otp_verified' signal.
    If no signal within share_otp_ttl_minutes (default: 10): token auto-expires.
    Once verified: notifies the document owner that their share was accessed.
    """

    def __init__(self):
        self._otp_verified = False
        self._accessor_id: str = ""

    @workflow.signal(name="otp_verified")
    def otp_verified(self, payload: dict) -> None:
        self._otp_verified = True
        self._accessor_id = payload.get("accessor_id", "")

    @workflow.run
    async def run(self, params: dict) -> dict:
        ttl_str = await workflow.execute_activity(
            get_share_config,
            {"key": "share_otp_ttl_minutes", "tenant_id": params.get("tenant_id"), "default": "10"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        token_data = await workflow.execute_activity(
            create_share_token, params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            send_share_otp, {**params, **token_data},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY,
        )

        verified = await workflow.wait_condition(
            lambda: self._otp_verified,
            timeout=timedelta(minutes=int(ttl_str)),
        )

        if verified and self._otp_verified:
            await workflow.execute_activity(
                notify_share_accessed,
                {**params, **token_data, "accessor_id": self._accessor_id},
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_RETRY,
            )
        else:
            # OTP not verified in time — expire the token
            await workflow.execute_activity(
                expire_share_token, token_data,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_RETRY,
            )

        return token_data
