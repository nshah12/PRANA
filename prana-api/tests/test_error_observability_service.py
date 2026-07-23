"""Tests for services/error_observability_service.py.

4th track of the incident system (prana-docs/ERROR_OBSERVABILITY_DESIGN.md).
Captures caught/uncaught exceptions with fingerprint-based dedup and PII scrubbing.
"""
from unittest.mock import AsyncMock

import pytest

from services.error_observability_service import ErrorObservabilityService


def _boom(message: str = "deliberate test explosion") -> Exception:
    try:
        raise RuntimeError(message)
    except RuntimeError as e:
        return e


@pytest.mark.asyncio
async def test_record_inserts_a_new_row_for_a_new_fingerprint():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=None)   # no existing open row for this fingerprint
    db.execute = AsyncMock()

    svc = ErrorObservabilityService(db)
    await svc.record(exc=_boom(), source="HTTP", source_detail="/admin/contact-inquiries")

    db.execute.assert_awaited_once()
    sql = db.execute.call_args.args[0]
    assert "INSERT INTO error_event" in sql


@pytest.mark.asyncio
async def test_record_increments_occurrence_count_on_repeat_fingerprint():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"error_id": "existing-id", "occurrence_count": 3})
    db.execute = AsyncMock()

    svc = ErrorObservabilityService(db)
    await svc.record(exc=_boom(), source="HTTP", source_detail="/admin/contact-inquiries")

    db.execute.assert_awaited_once()
    sql = db.execute.call_args.args[0]
    assert "UPDATE error_event" in sql
    assert "occurrence_count" in sql


@pytest.mark.asyncio
async def test_same_exception_type_and_location_produces_same_fingerprint():
    svc = ErrorObservabilityService(AsyncMock())
    fp1 = svc._fingerprint(_boom("first message with id 12345"))
    fp2 = svc._fingerprint(_boom("first message with id 99999"))
    # Same exception type + same raise site + normalized message -> same fingerprint,
    # even though the literal digits differ (dedup must survive varying input data).
    assert fp1 == fp2


@pytest.mark.asyncio
async def test_different_exception_types_produce_different_fingerprints():
    svc = ErrorObservabilityService(AsyncMock())
    try:
        raise ValueError("bad value")
    except ValueError as e:
        fp_value_error = svc._fingerprint(e)
    fp_runtime_error = svc._fingerprint(_boom("bad value"))
    assert fp_value_error != fp_runtime_error


def test_scrub_redacts_pan_shaped_strings():
    svc = ErrorObservabilityService(AsyncMock())
    scrubbed = svc._scrub("employee PAN is ABCDE1234F, lookup failed")
    assert "ABCDE1234F" not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_scrub_redacts_jwt_shaped_strings():
    svc = ErrorObservabilityService(AsyncMock())
    fake_jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PYE"
    scrubbed = svc._scrub(f"token validation failed: {fake_jwt}")
    assert fake_jwt not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_scrub_redacts_email_addresses():
    svc = ErrorObservabilityService(AsyncMock())
    scrubbed = svc._scrub("duplicate key value violates unique constraint Key (email)=(rahul@example.in)")
    assert "rahul@example.in" not in scrubbed


def test_scrub_redacts_indian_mobile_numbers():
    svc = ErrorObservabilityService(AsyncMock())
    scrubbed = svc._scrub("failed to send OTP to +919000000001")
    assert "+919000000001" not in scrubbed


def test_scrub_truncates_long_messages():
    svc = ErrorObservabilityService(AsyncMock())
    scrubbed = svc._scrub("x" * 5000)
    assert len(scrubbed) <= 2000


@pytest.mark.asyncio
async def test_record_never_captures_local_variables_only_standard_traceback():
    """Regression guard: must use traceback.format_exc(), never a richer
    introspection library that could dump local variable values (a PAN/salary
    leak vector — see ERROR_OBSERVABILITY_DESIGN.md §6)."""
    import inspect
    src = inspect.getsource(ErrorObservabilityService.record)
    assert "traceback_with_variables" not in src
    assert "locals()" not in src
    assert "f_locals" not in src


@pytest.mark.asyncio
async def test_record_returns_error_id():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=None)
    db.execute = AsyncMock()

    svc = ErrorObservabilityService(db)
    error_id = await svc.record(exc=_boom(), source="KAFKA_CONSUMER", source_detail="CommunicationHubConsumer")

    assert error_id  # non-empty string


@pytest.mark.asyncio
async def test_acknowledge_marks_row_acknowledged():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"error_id": "e-1", "status": "NEW"})
    db.execute = AsyncMock()

    svc = ErrorObservabilityService(db)
    await svc.acknowledge(error_id="e-1")

    sql = db.execute.call_args.args[0]
    assert "ACKNOWLEDGED" in sql


@pytest.mark.asyncio
async def test_resolve_requires_resolution_note():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"error_id": "e-1", "status": "NEW"})

    svc = ErrorObservabilityService(db)
    with pytest.raises(ValueError):
        await svc.resolve(error_id="e-1", resolved_by="pa-1", resolution_note="")


@pytest.mark.asyncio
async def test_resolve_raises_when_error_not_found():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=None)

    svc = ErrorObservabilityService(db)
    with pytest.raises(ValueError):
        await svc.resolve(error_id="missing", resolved_by="pa-1", resolution_note="fixed it")


@pytest.mark.asyncio
async def test_ignore_marks_row_ignored():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"error_id": "e-1", "status": "NEW"})
    db.execute = AsyncMock()

    svc = ErrorObservabilityService(db)
    await svc.ignore(error_id="e-1")

    sql = db.execute.call_args.args[0]
    assert "IGNORED" in sql


@pytest.mark.asyncio
async def test_promote_to_incident_creates_incident_and_links_it():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={
        "error_id": "e-1", "exception_type": "RuntimeError",
        "source_detail": "/admin/contact-inquiries", "tenant_id": None,
    })
    db.execute = AsyncMock()

    svc = ErrorObservabilityService(db)
    from unittest.mock import patch
    with patch("services.incident_service.IncidentService.create_incident",
               new_callable=AsyncMock, return_value="incident-1") as mock_create:
        incident_id = await svc.promote_to_incident(error_id="e-1", severity="P2")

    mock_create.assert_awaited_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["incident_type"] == "APPLICATION_ERROR"
    assert kwargs["severity"] == "P2"
    assert incident_id == "incident-1"
    # error_event.linked_incident_id must be set
    update_sql = db.execute.call_args.args[0]
    assert "linked_incident_id" in update_sql


@pytest.mark.asyncio
async def test_list_errors_filters_by_status_and_tenant():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])

    svc = ErrorObservabilityService(db)
    await svc.list_errors(tenant_id="tenant-1", status="NEW", limit=50)

    args = db.fetch.call_args.args
    assert "tenant-1" in args
    assert "NEW" in args


@pytest.mark.asyncio
async def test_list_errors_include_platform_errors_also_matches_null_tenant():
    """CISO tenant-scoped view (ERROR_OBSERVABILITY_DESIGN.md §7): must see both
    their own tenant's errors AND platform-level errors (tenant_id IS NULL)."""
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])

    svc = ErrorObservabilityService(db)
    await svc.list_errors(tenant_id="tenant-1", include_platform_errors=True, limit=50)

    sql = db.fetch.call_args.args[0]
    assert "tenant_id = $1 OR tenant_id IS NULL" in sql


@pytest.mark.asyncio
async def test_list_errors_without_include_platform_errors_is_exact_tenant_match():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])

    svc = ErrorObservabilityService(db)
    await svc.list_errors(tenant_id="tenant-1", limit=50)

    sql = db.fetch.call_args.args[0]
    assert "tenant_id = $1" in sql
    assert "IS NULL" not in sql
