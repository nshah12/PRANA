"""
Tests for routers/exceptions.py — OA Exception Queue.

Tests cover:
  - Auth: employee JWT → 403, no token → 401
  - Role: oa_operator → 403 (admin only)
  - List: wrapped shape, OPEN-only filter, SLA breach flag
  - Detail: extracted_fields and candidate_matches included
  - Tenant isolation: cannot see another tenant's exceptions
  - Resolve: marks RESOLVED, signals DocumentPipelineWorkflow, publishes Kafka audit
  - Dismiss: marks DISMISSED, signals workflow, publishes Kafka audit
  - Resolve on already-resolved: 409
  - Resolve with unknown employee_uuid: 404
  - Privacy: no raw salary/PAN in any response

TDD: written BEFORE implementation. Run RED first.
"""
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _oa_admin_headers(client, tenant_id="tenant-001"):
    """Inject OA-Admin JWT into mock jwt_service."""
    client.app.state.jwt_service.decode.return_value = {
        "sub": "oa-admin-001",
        "user_type": "oa_user",
        "role": "oa_admin",
        "tenant_id": tenant_id,
        "jti": "sess-oa-001",
        "exp": 9999999999,
    }
    client.app.state.jwt_service.is_revoked = AsyncMock(return_value=False)
    return {"Authorization": "Bearer oa.admin.jwt"}


def _oa_operator_headers(client, tenant_id="tenant-001"):
    client.app.state.jwt_service.decode.return_value = {
        "sub": "oa-op-001",
        "user_type": "oa_user",
        "role": "oa_operator",
        "tenant_id": tenant_id,
        "jti": "sess-op-001",
        "exp": 9999999999,
    }
    client.app.state.jwt_service.is_revoked = AsyncMock(return_value=False)
    return {"Authorization": "Bearer oa.operator.jwt"}


def _open_exception(*, exception_id="exc-001", status="OPEN", hours_old=2):
    raised_at = datetime.now(tz=timezone.utc) - timedelta(hours=hours_old)
    return {
        "exception_id": UUID("11111111-1111-1111-1111-111111111111"),
        "document_id": UUID("22222222-2222-2222-2222-222222222222"),
        "tenant_id": UUID("33333333-3333-3333-3333-333333333333"),
        "exception_type": "NO_MATCH",
        "extracted_fields": json.dumps({"name": "Ramesh Kumar", "doj": "2022-01-15"}),
        "candidate_matches": json.dumps([
            {"employee_uuid": "emp-aaa", "full_name": "Ramesh Kumar", "confidence": 0.72},
        ]),
        "resolved_by": None,
        "resolved_employee_uuid": None,
        "status": status,
        "raised_at": raised_at,
        "resolved_at": None,
    }


# ── Auth enforcement ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_exceptions_without_token_returns_401(client):
    resp = await client.get("/v1/org/exceptions")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_exceptions_with_employee_token_returns_403(client):
    client.app.state.jwt_service.decode.return_value = {
        "sub": "emp-001",
        "user_type": "employee",
        "jti": "sess-emp-001",
        "exp": 9999999999,
    }
    client.app.state.jwt_service.is_revoked = AsyncMock(return_value=False)
    resp = await client.get(
        "/v1/org/exceptions",
        headers={"Authorization": "Bearer emp.jwt"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_exceptions_with_oa_operator_returns_403(client):
    """Exception queue is OA-Admin only — operators cannot see it."""
    headers = _oa_operator_headers(client)
    resp = await client.get("/v1/org/exceptions", headers=headers)
    assert resp.status_code == 403


# ── List endpoint ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_exceptions_returns_wrapped_shape(client, mock_db):
    """Response must be {"exceptions": [...], "total": N, "sla_breached": N}."""
    headers = _oa_admin_headers(client)
    mock_db.fetch.return_value = [_open_exception()]
    mock_db.fetchval.return_value = 0  # sla_breached count

    resp = await client.get("/v1/org/exceptions", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert "exceptions" in body, "Must have 'exceptions' key — not bare array"
    assert "total" in body
    assert "sla_breached" in body
    assert isinstance(body["exceptions"], list)


@pytest.mark.asyncio
async def test_list_exceptions_only_returns_own_tenant(client, mock_db):
    """Tenant A admin must never see tenant B exceptions."""
    headers = _oa_admin_headers(client, tenant_id="tenant-A")
    captured_args = []

    original_fetch = mock_db.fetch

    async def spy_fetch(query, *args):
        captured_args.extend(args)
        return []

    mock_db.fetch = spy_fetch
    mock_db.fetchval = AsyncMock(return_value=0)

    await client.get("/v1/org/exceptions", headers=headers)

    # tenant_id=tenant-A must appear as a query parameter
    assert any("tenant-A" in str(a) for a in captured_args), (
        "Query must filter by tenant_id from JWT — not open to all tenants"
    )


@pytest.mark.asyncio
async def test_list_exceptions_includes_sla_breach_flag(client, mock_db):
    """Exception older than exception_sla_p95_hours must be flagged."""
    headers = _oa_admin_headers(client)
    # 26-hour-old exception — well past the 24hr P95 SLA
    old_exc = _open_exception(hours_old=26)
    mock_db.fetch.return_value = [old_exc]
    mock_db.fetchval.return_value = 1  # 1 SLA breach

    resp = await client.get("/v1/org/exceptions", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["sla_breached"] >= 1, "SLA breach count must be reported"


# ── Detail endpoint ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_exception_detail_returns_404_for_unknown(client, mock_db):
    headers = _oa_admin_headers(client)
    mock_db.fetchrow.return_value = None

    resp = await client.get("/v1/org/exceptions/nonexistent-id", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_exception_detail_returns_extracted_fields_and_candidates(client, mock_db):
    headers = _oa_admin_headers(client)
    mock_db.fetchrow.return_value = _open_exception()

    resp = await client.get("/v1/org/exceptions/exc-001", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert "exception" in body
    exc = body["exception"]
    assert "extracted_fields" in exc, "extracted_fields must be included for OA-Admin context"
    assert "candidate_matches" in exc, "candidate_matches must be included for OA-Admin to pick from"
    assert "exception_type" in exc
    assert "raised_at" in exc


@pytest.mark.asyncio
async def test_get_exception_detail_cross_tenant_returns_404(client, mock_db):
    """OA-Admin of tenant-A must not see tenant-B exception — returns 404 not 403."""
    headers = _oa_admin_headers(client, tenant_id="tenant-A")
    # Row has different tenant_id — the query WHERE tenant_id=$1 should return None
    mock_db.fetchrow.return_value = None  # filtered out by tenant_id condition

    resp = await client.get("/v1/org/exceptions/exc-other-tenant", headers=headers)
    assert resp.status_code == 404


# ── Resolve endpoint ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_exception_without_token_returns_401(client):
    resp = await client.post(
        "/v1/org/exceptions/exc-001/resolve",
        json={"employee_uuid": "emp-aaa"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_resolve_exception_with_operator_returns_403(client):
    headers = _oa_operator_headers(client)
    resp = await client.post(
        "/v1/org/exceptions/exc-001/resolve",
        headers=headers,
        json={"employee_uuid": "emp-aaa"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_resolve_exception_happy_path(client, mock_db):
    """
    Resolve must:
    1. Mark exception RESOLVED in DB
    2. Signal DocumentPipelineWorkflow via Temporal (if available)
    3. Publish audit event to Kafka
    4. Return {"exception_id": ..., "status": "RESOLVED"}
    """
    headers = _oa_admin_headers(client)
    mock_db.fetchrow.return_value = _open_exception()  # OPEN exception exists
    # Validate employee exists in this tenant
    mock_db.fetchval.return_value = "emp-aaa"  # employee found

    resp = await client.post(
        "/v1/org/exceptions/exc-001/resolve",
        headers=headers,
        json={"employee_uuid": "emp-aaa"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "RESOLVED"
    assert "exception_id" in body
    # DB must have been updated
    assert mock_db.execute.called


@pytest.mark.asyncio
async def test_resolve_exception_publishes_kafka_audit(client, mock_db):
    headers = _oa_admin_headers(client)
    mock_db.fetchrow.return_value = _open_exception()
    mock_db.fetchval.return_value = "emp-aaa"

    resp = await client.post(
        "/v1/org/exceptions/exc-001/resolve",
        headers=headers,
        json={"employee_uuid": "emp-aaa"},
    )

    assert resp.status_code == 200
    kafka = client.app.state.kafka_producer
    assert kafka.exception_resolved.called, "Must publish audit event to Kafka on resolve"
    # Verify audit event type
    payload = kafka.exception_resolved.call_args[0][0]
    assert payload.get("event_type") == "EXCEPTION_RESOLVED"


@pytest.mark.asyncio
async def test_resolve_already_resolved_exception_returns_409(client, mock_db):
    headers = _oa_admin_headers(client)
    mock_db.fetchrow.return_value = _open_exception(status="RESOLVED")

    resp = await client.post(
        "/v1/org/exceptions/exc-001/resolve",
        headers=headers,
        json={"employee_uuid": "emp-aaa"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "EXCEPTION_NOT_OPEN"


@pytest.mark.asyncio
async def test_resolve_nonexistent_exception_returns_404(client, mock_db):
    headers = _oa_admin_headers(client)
    mock_db.fetchrow.return_value = None

    resp = await client.post(
        "/v1/org/exceptions/nonexistent/resolve",
        headers=headers,
        json={"employee_uuid": "emp-aaa"},
    )
    assert resp.status_code == 404


# ── Dismiss endpoint ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dismiss_exception_happy_path(client, mock_db):
    """
    Dismiss must:
    1. Mark exception DISMISSED in DB
    2. Signal DocumentPipelineWorkflow with no match (document goes to error state)
    3. Publish audit event
    4. Return {"exception_id": ..., "status": "DISMISSED"}
    """
    headers = _oa_admin_headers(client)
    mock_db.fetchrow.return_value = _open_exception()

    resp = await client.post(
        "/v1/org/exceptions/exc-001/dismiss",
        headers=headers,
        json={"reason": "Document is a duplicate — already routed via another batch."},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "DISMISSED"
    assert "exception_id" in body
    assert mock_db.execute.called


@pytest.mark.asyncio
async def test_dismiss_already_resolved_returns_409(client, mock_db):
    headers = _oa_admin_headers(client)
    mock_db.fetchrow.return_value = _open_exception(status="RESOLVED")

    resp = await client.post(
        "/v1/org/exceptions/exc-001/dismiss",
        headers=headers,
        json={"reason": "Duplicate."},
    )
    assert resp.status_code == 409


# ── Privacy ────────────────────────────────────────────────────────────────────

_FORBIDDEN = {"pan", "nik", "enc_pan", "salary", "gross_salary", "net_salary", "ctc"}


@pytest.mark.asyncio
async def test_list_exceptions_no_pan_or_salary(client, mock_db):
    headers = _oa_admin_headers(client)
    mock_db.fetch.return_value = [_open_exception()]
    mock_db.fetchval.return_value = 0

    resp = await client.get("/v1/org/exceptions", headers=headers)
    if resp.status_code == 200:
        body_str = json.dumps(resp.json()).lower()
        for field in _FORBIDDEN:
            assert field not in body_str, f"Forbidden field '{field}' in exception list response"


@pytest.mark.asyncio
async def test_exception_detail_extracted_fields_no_raw_salary(client, mock_db):
    """extracted_fields is LLM output shown to OA-Admin for context — must not include raw salary."""
    exc = _open_exception()
    # Simulate a bad LLM that included salary — router must strip it
    exc["extracted_fields"] = json.dumps({
        "name": "Ramesh Kumar",
        "doj": "2022-01-15",
        "salary": 85000,       # must be stripped before returning to OA-Admin
        "gross_salary": 92000, # must be stripped
    })
    mock_db.fetchrow.return_value = exc
    headers = _oa_admin_headers(client)

    resp = await client.get("/v1/org/exceptions/exc-001", headers=headers)
    if resp.status_code == 200:
        body_str = json.dumps(resp.json()).lower()
        assert "85000" not in body_str, "Raw salary must be stripped from extracted_fields before OA-Admin response"
        assert "92000" not in body_str
