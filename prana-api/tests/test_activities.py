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
