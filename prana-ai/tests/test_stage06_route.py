"""Tests for pipeline/stage06_route.py — routing, status update, and event emission."""
import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock

from pipeline.stage06_route import Stage06Route, _SAFE_METADATA_FIELDS


def test_stage06_moves_document_from_staging_to_permanent_s3_key():
    # Stage06 writes the permanent s3_key into the document row on ROUTED.
    src = inspect.getsource(Stage06Route.route)
    assert "s3_key" in src, \
        "Stage06.route must update document.s3_key with the permanent (encrypted) S3 path"
    assert "pipeline_status='ROUTED'" in src or 'pipeline_status=\'ROUTED\'' in src, \
        "Stage06.route must set pipeline_status to ROUTED in the UPDATE statement"


def test_stage06_sets_pipeline_status_to_routed():
    # The UPDATE statement must set pipeline_status='ROUTED' — this is what the
    # SSEFanoutConsumer watches to push real-time progress to the employee browser.
    src = inspect.getsource(Stage06Route.route)
    assert "ROUTED" in src, "Stage06 must mark pipeline_status as ROUTED"
    # Stage06 must use a fail-closed ALLOWLIST (not a blocklist) — see
    # test_stage06_unknown_field_is_stripped_by_default below for why.
    assert _SAFE_METADATA_FIELDS, "Stage06 must define _SAFE_METADATA_FIELDS to allowlist for DB storage"
    assert "gross_salary" not in _SAFE_METADATA_FIELDS, \
        "gross_salary must NOT be in the safe allowlist — it's a raw ₹ figure"
    assert "gross_ctc" not in _SAFE_METADATA_FIELDS, \
        "gross_ctc must NOT be in the safe allowlist — it's a raw ₹ figure"
    assert "designation" in _SAFE_METADATA_FIELDS, \
        "designation is ordinary metadata and must be in the safe allowlist"


def test_stage06_notifies_prana_api_of_routing():
    # Stage06 must NOT publish to Kafka directly (prana-ai has no Kafka credentials —
    # see internal-service-calls.md). It notifies prana-api's /internal/pipeline/routed
    # callback (the one sanctioned VPC-internal bypass), which does the actual
    # DOC_ROUTED publish. AFTER the DB transaction commits.
    src = inspect.getsource(Stage06Route.route)
    assert "career_event" in src, \
        "Stage06 must also insert a career_event row"
    assert "self._kafka" not in src, \
        "Stage06 must not hold a Kafka producer — prana-ai has no Kafka credentials " \
        "(internal-service-calls.md). Dead kafka_producer param/code must be removed, " \
        "not just unused."
    src_notify = inspect.getsource(Stage06Route._notify_routed)
    assert "/internal/pipeline/routed" in src_notify
    assert "X-Internal-Service" in src_notify


@pytest.mark.asyncio
async def test_stage06_notify_fires_after_db_commit_with_first_activation_flag(monkeypatch):
    """Internal-service HTTP notify must be OUTSIDE the transaction block — fire-and-forget
    after commit — and must tell prana-api whether this is the employee's first-ever
    routed document (so prana-api can publish VAULT_ACTIVATED)."""
    monkeypatch.setenv("PRANA_API_INTERNAL_URL", "http://prana-api.prod.internal:8000")

    mock_db = AsyncMock()
    mock_db.fetchval.side_effect = ["emp-user-001", True]  # employee_user_id, then is_first_activation
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
    mock_tx.__aexit__ = AsyncMock(return_value=False)
    mock_db.transaction = MagicMock(return_value=mock_tx)

    mock_benchmark = AsyncMock()
    mock_benchmark.build_career_context = AsyncMock(return_value={})

    _EMP_UUID = "12345678-1234-5678-1234-567812345678"
    _TENANT_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    svc = Stage06Route(db=mock_db, benchmark_svc=mock_benchmark)

    captured = {}

    class _FakeResp:
        def raise_for_status(self): pass

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json, headers, timeout=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _FakeResp()

    monkeypatch.setattr("pipeline.stage06_route.httpx.AsyncClient", lambda *a, **kw: _FakeClient())

    await svc.route(
        document_id="doc-001", tenant_id=_TENANT_UUID,
        employee_uuid=_EMP_UUID, pan_token="pan-tok-001",
        doc_type="SALARY_SLIP", doc_period="2025-05",
        extracted_fields={"gross_salary": 100000, "designation": "Engineer"},
        resolution_method="PAN_TOKEN_EXACT", resolution_confidence=0.99,
        s3_key="t/e/SALARY_SLIP/2025-05_doc-001.pdf",
    )

    assert captured["url"] == "http://prana-api.prod.internal:8000/internal/pipeline/routed"
    assert captured["headers"] == {"X-Internal-Service": "prana-ai"}
    payload = captured["json"]
    assert payload["document_id"] == "doc-001"
    assert payload["employee_uuid"] == _EMP_UUID
    assert payload["employee_user_id"] == "emp-user-001"
    assert payload["is_first_activation"] is True
    # Raw salary must NOT be in the outbound payload
    assert "gross_salary" not in payload


@pytest.mark.asyncio
async def test_stage06_notify_failure_does_not_rollback_db(monkeypatch):
    """If the internal-service HTTP call fails, the DB transaction must already be
    committed — no rollback, and no exception propagates."""
    monkeypatch.setenv("PRANA_API_INTERNAL_URL", "http://prana-api.prod.internal:8000")

    mock_db = AsyncMock()
    mock_db.fetchval.side_effect = ["emp-user-001", False]
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
    mock_tx.__aexit__ = AsyncMock(return_value=False)
    mock_db.transaction = MagicMock(return_value=mock_tx)

    mock_benchmark = AsyncMock()
    mock_benchmark.build_career_context = AsyncMock(return_value={})

    _EMP_UUID = "12345678-1234-5678-1234-567812345678"
    _TENANT_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    svc = Stage06Route(db=mock_db, benchmark_svc=mock_benchmark)

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw):
            raise Exception("prana-api unreachable")

    monkeypatch.setattr("pipeline.stage06_route.httpx.AsyncClient", lambda *a, **kw: _FakeClient())

    # Must not raise — notify failure is logged and swallowed
    await svc.route(
        document_id="doc-002", tenant_id=_TENANT_UUID,
        employee_uuid=_EMP_UUID, pan_token="pan-tok-001",
        doc_type="FORM_16", doc_period="FY:2024-25",
        extracted_fields={}, resolution_method="PAN_TOKEN_EXACT", resolution_confidence=0.95,
        s3_key="t/e/FORM_16/FY2024-25_doc-002.pdf",
    )
    # DB transaction was entered (committed before the HTTP call was made)
    mock_db.transaction.assert_called_once()


@pytest.mark.asyncio
async def test_stage06_unknown_field_is_stripped_by_default():
    """
    Fail-closed regression guard for the manifest-driven extraction path.

    Unlike the static per-doc-type schemas, prana-api's doc_type_field_manifest
    lets any tenant's OA-Admin configure arbitrary field names for a doc type.
    A blocklist ("strip these known-bad names") can never keep up with that —
    it already missed gross_ctc/net_pay/tds_amount for the STATIC schemas, and
    a tenant-custom field name is even less predictable. An allowlist ("keep
    only these known-safe names, strip everything else") fails in the safe
    direction: an unrecognized field is dropped (data loss) instead of leaked
    (privacy violation).

    This test proves a field name that's on NEITHER the safe allowlist NOR any
    known schema (simulating an arbitrary tenant-configured manifest field,
    sensitive-sounding or not) never reaches the DB write.
    """
    mock_db = AsyncMock()
    mock_db.fetchval.return_value = "emp-user-001"
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
    mock_tx.__aexit__ = AsyncMock(return_value=False)
    mock_db.transaction = MagicMock(return_value=mock_tx)

    mock_benchmark = AsyncMock()
    mock_benchmark.build_career_context = AsyncMock(return_value={})

    _EMP_UUID = "12345678-1234-5678-1234-567812345678"
    _TENANT_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    svc = Stage06Route(db=mock_db, benchmark_svc=mock_benchmark)
    await svc.route(
        document_id="doc-003", tenant_id=_TENANT_UUID,
        employee_uuid=_EMP_UUID, pan_token="pan-tok-001",
        doc_type="SALARY_SLIP", doc_period="2025-05",
        extracted_fields={
            "designation": "Engineer",                    # known-safe — must survive
            "monthly_take_home": {"value": 92000},          # tenant-custom, unrecognized
            "some_new_field_nobody_allowlisted_yet": "x",   # unrecognized
        },
        resolution_method="PAN_TOKEN_EXACT", resolution_confidence=0.99,
        s3_key="t/e/SALARY_SLIP/2025-05_doc-003.pdf",
    )

    update_calls = [c for c in mock_db.execute.call_args_list if "UPDATE document" in str(c)]
    assert update_calls, "Stage06 must call UPDATE document"
    import json
    stored = json.loads(update_calls[0][0][4])
    assert stored == {"designation": "Engineer"}, (
        f"Unrecognized fields must be stripped by default (fail-closed). Got: {stored}"
    )


# ── Manifest-aware allowlist (tenant-custom fields via doc_type_field_manifest) ──

def _make_manifest_client(safe_fields=None, raises=False):
    from manifest.manifest_client import ManifestData
    client = AsyncMock()
    if raises:
        client.resolve = AsyncMock(side_effect=ValueError("no manifest"))
    else:
        client.resolve = AsyncMock(return_value=ManifestData(
            manifest_id="m-1", doc_type="SALARY_SLIP",
            required_fields=[], identity_fields=[], optional_fields=[],
            classification_signals=[], confidence_threshold=0.75,
            supported_formats=["pdf"], safe_fields=safe_fields or [],
        ))
    return client


@pytest.mark.asyncio
async def test_manifest_declared_safe_field_survives_strip():
    """A tenant-custom field the OA-Admin has explicitly marked safe in their
    manifest must survive, even though it's not in the static allowlist."""
    mock_db = AsyncMock()
    mock_db.fetchval.return_value = "emp-user-001"
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
    mock_tx.__aexit__ = AsyncMock(return_value=False)
    mock_db.transaction = MagicMock(return_value=mock_tx)

    mock_benchmark = AsyncMock()
    mock_benchmark.build_career_context = AsyncMock(return_value={})
    manifest_client = _make_manifest_client(safe_fields=["leave_balance_days"])

    svc = Stage06Route(db=mock_db, benchmark_svc=mock_benchmark, manifest_client=manifest_client)
    await svc.route(
        document_id="doc-010", tenant_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        employee_uuid="12345678-1234-5678-1234-567812345678",
        pan_token="pan-1", doc_type="SALARY_SLIP", doc_period="2025-05",
        extracted_fields={
            "designation": "Engineer",
            "leave_balance_days": {"value": 12},  # tenant-custom, manifest-approved safe
            "some_other_custom_field": {"value": "x"},  # tenant-custom, NOT approved
        },
        resolution_method="PAN_TOKEN_EXACT", resolution_confidence=0.99,
        s3_key="t/e/SALARY_SLIP/2025-05_doc-010.pdf",
    )

    import json
    update_calls = [c for c in mock_db.execute.call_args_list if "UPDATE document" in str(c)]
    stored = json.loads(update_calls[0][0][4])
    assert stored == {"designation": "Engineer", "leave_balance_days": {"value": 12}}


@pytest.mark.asyncio
async def test_manifest_fetch_failure_falls_back_to_static_allowlist():
    """If the manifest fetch itself fails, fall back to the static allowlist
    only — never fail open to 'keep everything'."""
    mock_db = AsyncMock()
    mock_db.fetchval.return_value = "emp-user-001"
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
    mock_tx.__aexit__ = AsyncMock(return_value=False)
    mock_db.transaction = MagicMock(return_value=mock_tx)

    mock_benchmark = AsyncMock()
    mock_benchmark.build_career_context = AsyncMock(return_value={})
    manifest_client = _make_manifest_client(raises=True)

    svc = Stage06Route(db=mock_db, benchmark_svc=mock_benchmark, manifest_client=manifest_client)
    await svc.route(
        document_id="doc-011", tenant_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        employee_uuid="12345678-1234-5678-1234-567812345678",
        pan_token="pan-1", doc_type="SALARY_SLIP", doc_period="2025-05",
        extracted_fields={
            "designation": "Engineer",       # static-allowlist safe
            "leave_balance_days": {"value": 12},  # would need manifest approval — fetch failed
        },
        resolution_method="PAN_TOKEN_EXACT", resolution_confidence=0.99,
        s3_key="t/e/SALARY_SLIP/2025-05_doc-011.pdf",
    )

    import json
    update_calls = [c for c in mock_db.execute.call_args_list if "UPDATE document" in str(c)]
    stored = json.loads(update_calls[0][0][4])
    assert stored == {"designation": "Engineer"}


@pytest.mark.asyncio
async def test_no_manifest_client_falls_back_to_static_allowlist():
    """Backward compat: Stage06Route constructed without a manifest_client
    (e.g. older callers) behaves exactly as before — static allowlist only."""
    mock_db = AsyncMock()
    mock_db.fetchval.return_value = "emp-user-001"
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
    mock_tx.__aexit__ = AsyncMock(return_value=False)
    mock_db.transaction = MagicMock(return_value=mock_tx)

    mock_benchmark = AsyncMock()
    mock_benchmark.build_career_context = AsyncMock(return_value={})

    svc = Stage06Route(db=mock_db, benchmark_svc=mock_benchmark)  # no manifest_client
    await svc.route(
        document_id="doc-012", tenant_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        employee_uuid="12345678-1234-5678-1234-567812345678",
        pan_token="pan-1", doc_type="SALARY_SLIP", doc_period="2025-05",
        extracted_fields={"designation": "Engineer", "leave_balance_days": {"value": 12}},
        resolution_method="PAN_TOKEN_EXACT", resolution_confidence=0.99,
        s3_key="t/e/SALARY_SLIP/2025-05_doc-012.pdf",
    )

    import json
    update_calls = [c for c in mock_db.execute.call_args_list if "UPDATE document" in str(c)]
    stored = json.loads(update_calls[0][0][4])
    assert stored == {"designation": "Engineer"}


@pytest.mark.asyncio
async def test_raise_exception_also_consults_manifest_when_doc_type_given():
    mock_db = AsyncMock()
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
    mock_tx.__aexit__ = AsyncMock(return_value=False)
    mock_db.transaction = MagicMock(return_value=mock_tx)
    mock_db.execute = AsyncMock()

    manifest_client = _make_manifest_client(safe_fields=["leave_balance_days"])
    svc = Stage06Route(db=mock_db, benchmark_svc=AsyncMock(), manifest_client=manifest_client)

    await svc.raise_exception(
        document_id="doc-013", tenant_id="tenant-1", exception_type="LOW_CONFIDENCE",
        extracted_fields={"designation": "Engineer", "leave_balance_days": {"value": 12}},
        candidates=[], doc_type="SALARY_SLIP",
    )

    import json
    insert_calls = [c for c in mock_db.execute.call_args_list if "INSERT INTO exception_queue" in str(c)]
    stored = json.loads(insert_calls[0][0][4])
    assert stored == {"designation": "Engineer", "leave_balance_days": {"value": 12}}
