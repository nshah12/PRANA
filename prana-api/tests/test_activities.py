"""Tests for workflows/activities.py — Temporal activity implementations."""
import inspect
import json
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_activities_contain_no_temporal_imports():
    # activities.py imports `from temporalio import activity` (decorator only — allowed)
    # Business logic service classes (encryption_service, compliance_service, etc.)
    # must NOT import temporalio — they are pure Python.
    #
    # EXCEPTION: ai_client.py is an infrastructure adapter, not business logic.
    # It raises ApplicationError so Temporal activities can propagate retryable/non-retryable
    # pipeline errors correctly (analogous to encryption_service importing boto3).
    _ALLOWED_TEMPORAL_IMPORTS = {"ai_client.py"}
    services_dir = pathlib.Path(__file__).parent.parent / "services"
    for src_file in services_dir.glob("*.py"):
        if src_file.name in _ALLOWED_TEMPORAL_IMPORTS:
            continue
        src = src_file.read_text(encoding="utf-8")
        assert "from temporalio" not in src and "import temporalio" not in src, \
            f"{src_file.name} must not import temporalio — business logic is pure Python"


def test_activity_callable_without_temporal_cluster():
    # Activities in activities.py are regular async functions decorated with @activity.defn
    # They can be imported and called without a Temporal cluster running
    from workflows import activities
    import asyncio

    # stage05_resolve is a real async function callable without cluster
    assert callable(activities.stage05_resolve)
    assert callable(activities.get_config_value)
    assert callable(activities.execute_erasure)


# ── stage05_handle_cross_tenant_violation — severity from policy, not hardcoded ──

@pytest.mark.asyncio
async def test_cross_tenant_violation_uses_policy_resolved_severity():
    """Severity written to anomaly_event must come from SeverityPolicyService
    (domain=ANOMALY_RULE, CROSS_TENANT_UPLOAD_ATTEMPT), not a hardcoded 'P0' literal —
    see prana-docs/SEVERITY_SLA_POLICY_DESIGN.md."""
    from workflows import activities

    mock_db = AsyncMock()
    mock_db.transaction = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    mock_db.close = AsyncMock()

    mock_kafka = AsyncMock()

    with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_db), \
         patch("services.severity_policy_service.SeverityPolicyService.resolve_severity",
               new_callable=AsyncMock, return_value="P1") as mock_resolve, \
         patch("kafka.producer.KafkaPub", return_value=mock_kafka):
        result = await activities.stage05_handle_cross_tenant_violation({
            "document_id": "doc-1",
            "uploading_tenant_id": "tenant-uploader",
            "owner_tenant_id": "tenant-owner",
            "pan_token": "tok",
            "uploaded_by": "oa-user-1",
        })

    mock_resolve.assert_awaited_once_with(domain="ANOMALY_RULE", value="CROSS_TENANT_UPLOAD_ATTEMPT")
    insert_call = next(
        c for c in mock_db.execute.call_args_list if "INSERT INTO anomaly_event" in c.args[0]
    )
    assert "P1" in insert_call.args
    assert result["status"] == "CROSS_TENANT_REJECTED"

    # Regression: this used to raw-publish only to prana.audit.events and
    # prana.notifications, never to prana.security.events — SecurityConsumer
    # (which owns the CISO real-time SSE dashboard alert) subscribes only to
    # prana.security.events, so its CROSS_TENANT_UPLOAD_DETECTED branch was
    # permanently unreachable dead code and the live dashboard never got pinged
    # (email+bell notification via CommunicationHubConsumer still worked independently).
    topics_published = [c.args[0] for c in mock_kafka.publish.call_args_list]
    assert "prana.security.events" in topics_published
    security_call = next(c for c in mock_kafka.publish.call_args_list if c.args[0] == "prana.security.events")
    assert security_call.args[1]["event_type"] == "CROSS_TENANT_UPLOAD_DETECTED"


@pytest.mark.asyncio
async def test_cross_tenant_violation_falls_back_to_p0_if_no_policy_row():
    """Defense-in-depth: if the policy row is missing/inactive, this security-critical
    path must still default to P0, never silently downgrade to no severity."""
    from workflows import activities

    mock_db = AsyncMock()
    mock_db.transaction = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    mock_db.close = AsyncMock()

    mock_kafka = AsyncMock()

    with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_db), \
         patch("services.severity_policy_service.SeverityPolicyService.resolve_severity",
               new_callable=AsyncMock, return_value=None), \
         patch("kafka.producer.KafkaPub", return_value=mock_kafka):
        await activities.stage05_handle_cross_tenant_violation({
            "document_id": "doc-1",
            "uploading_tenant_id": "tenant-uploader",
            "owner_tenant_id": "tenant-owner",
            "pan_token": "tok",
            "uploaded_by": "oa-user-1",
        })

    insert_call = next(
        c for c in mock_db.execute.call_args_list if "INSERT INTO anomaly_event" in c.args[0]
    )
    assert "P0" in insert_call.args


# ── get_batch_config — durations + (when batch_id given) the batch's document_ids ──
# BATCH_UPLOADED events carry only a count, not the ids, so BatchProgressWorkflow's
# fan-out looks them up here rather than receiving them in its start params.

@pytest.mark.asyncio
async def test_get_batch_config_returns_durations_without_batch_id():
    from workflows import activities

    mock_db = AsyncMock()
    mock_db.fetchrow = AsyncMock(return_value={"val": "4"})
    mock_db.close = AsyncMock()

    with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_db):
        result = await activities.get_batch_config({"tenant_id": "t-1"})

    assert result["pipeline_max_duration_hours"] == "4"
    assert "document_ids" not in result
    mock_db.fetch.assert_not_called()


@pytest.mark.asyncio
async def test_get_batch_config_returns_document_ids_when_batch_id_given():
    from workflows import activities

    mock_db = AsyncMock()
    mock_db.fetchrow = AsyncMock(return_value={"val": "4"})
    mock_db.fetch = AsyncMock(return_value=[{"document_id": "doc-1"}, {"document_id": "doc-2"}])
    mock_db.close = AsyncMock()

    with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_db):
        result = await activities.get_batch_config({"tenant_id": "t-1", "batch_id": "batch-1"})

    assert result["document_ids"] == ["doc-1", "doc-2"]
    sql, *args = mock_db.fetch.call_args.args
    assert "batch_id=$1" in sql
    assert "batch-1" in args


# ── write_batch_summary — real body, previously a bare stub ──────────────────

@pytest.mark.asyncio
async def test_write_batch_summary_updates_document_batch_row():
    from workflows import activities

    mock_db = AsyncMock()
    mock_db.close = AsyncMock()

    with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_db):
        await activities.write_batch_summary({
            "batch_id": "batch-1", "total": 5, "routed": 4,
            "exceptions": 1, "quarantine": 0, "failed": 0,
        })

    sql, *args = mock_db.execute.call_args.args
    assert "UPDATE document_batch" in sql
    assert "batch-1" in args
    assert 5 in args and 4 in args


# ── mark_batch_straggler — real body, previously a bare stub ─────────────────

@pytest.mark.asyncio
async def test_mark_batch_straggler_marks_exception_and_writes_queue_row():
    from workflows import activities

    mock_db = AsyncMock()
    mock_db.transaction = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    mock_db.fetchval = AsyncMock(return_value="doc-1")
    mock_db.close = AsyncMock()

    with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_db):
        await activities.mark_batch_straggler({
            "document_id": "doc-1", "tenant_id": "t-1", "batch_id": "batch-1",
        })

    insert_call = next(
        c for c in mock_db.execute.call_args_list if "INSERT INTO exception_queue" in c.args[0]
    )
    assert "doc-1" in insert_call.args
    assert "PIPELINE_TIMEOUT" in insert_call.args


@pytest.mark.asyncio
async def test_mark_batch_straggler_noop_if_already_terminal():
    """Idempotency guard: a document already ROUTED/EXCEPTION/QUARANTINED/CSAM_HOLD
    must not get a duplicate exception_queue row from a late straggler check."""
    from workflows import activities

    mock_db = AsyncMock()
    mock_db.transaction = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    mock_db.fetchval = AsyncMock(return_value=None)  # UPDATE matched 0 rows
    mock_db.close = AsyncMock()

    with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_db):
        await activities.mark_batch_straggler({
            "document_id": "doc-1", "tenant_id": "t-1", "batch_id": "batch-1",
        })

    assert not any("INSERT INTO exception_queue" in c.args[0] for c in mock_db.execute.call_args_list)


# ── stage02_encrypt — KMSService.unwrap_dek, not the nonexistent decrypt_dek ────

def test_stage02_encrypt_calls_unwrap_dek_synchronously_not_decrypt_dek():
    """Regression guard: this used to call `await kms.decrypt_dek(...)` — a method
    that doesn't exist on KMSService (real methods are wrap_dek/unwrap_dek), and
    even if renamed naively, unwrap_dek is synchronous (boto3 kms.decrypt is not
    async), so `await`ing it would raise TypeError. Since AttributeError fires
    before that ever mattered, every PAN-bearing document upload through
    stage02_encrypt would have crashed instantly against a real KMSService.
    No test previously called this function with pan supplied, so it shipped
    unnoticed — see workflows/activities.py's stage02_encrypt."""
    from workflows import activities

    assert not hasattr(activities.KMSService, "decrypt_dek"), \
        "decrypt_dek should not exist on KMSService — real method is unwrap_dek"
    import inspect
    assert not inspect.iscoroutinefunction(activities.KMSService.unwrap_dek), \
        "unwrap_dek is synchronous — awaiting it would raise TypeError"


@pytest.mark.asyncio
async def test_stage02_encrypt_with_pan_encrypts_and_uploads():
    from workflows import activities

    fake_dek = b"0" * 32
    mock_kms = MagicMock()
    mock_kms.unwrap_dek = MagicMock(return_value=fake_dek)  # sync, not a coroutine

    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"file-bytes"))}

    mock_cipher = MagicMock()
    mock_cipher.encrypt.return_value = "0000000000"

    with patch("workflows.activities.KMSService", return_value=mock_kms), \
         patch("boto3.client", return_value=mock_s3), \
         patch("ff3.FF3Cipher.withCustomAlphabet", return_value=mock_cipher):
        result = await activities.stage02_encrypt({
            "pan": "ABCDE1234F",
            "enc_dek": "wrapped-dek-ciphertext",
            "tenant_kek_arn": "arn:aws:kms:ap-south-1:123:key/tenant-kek",
            "s3_staging_key": "staging/doc-1",
            "s3_staging_bucket": "prana-staging-dev",
            "tenant_id": "t-1",
            "document_id": "doc-1",
            "doc_type": "salary_slip",
        })

    mock_kms.unwrap_dek.assert_called_with("wrapped-dek-ciphertext", "arn:aws:kms:ap-south-1:123:key/tenant-kek")
    assert result["nik_found"] is True
    assert result["pan_token"]
    mock_s3.put_object.assert_called_once()
    mock_s3.delete_object.assert_called_once_with(Bucket="prana-staging-dev", Key="staging/doc-1")
