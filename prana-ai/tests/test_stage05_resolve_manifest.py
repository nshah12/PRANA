"""
Tests for the manifest-driven Stage05Resolve.

Verifies that identity_fields in the manifest correctly toggles
which resolution ladder levels are attempted.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from pipeline.stage05_resolve import Stage05Resolve, Stage05Result, CrossTenantViolation
from resolution.resolution_service import ResolutionMethod
from manifest.manifest_client import ManifestData


# ── Helpers ────────────────────────────────────────────────────────────────────

def _manifest(identity_fields=None) -> ManifestData:
    return ManifestData(
        manifest_id="m-001",
        tenant_id=None,
        doc_type="SALARY_SLIP",
        required_fields=["employee_name", "net_pay"],
        identity_fields=identity_fields or ["pan_number", "employee_id", "employee_name"],
        optional_fields=[],
        classification_signals=[],
        confidence_threshold=0.75,
        supported_formats=["pdf"],
        is_tenant_override=False,
    )


def _extracted(
    employee_name="Rahul Kumar",
    employee_id=None,
    date_of_joining=None,
    designation=None,
):
    fields = {
        "employee_name": {"value": employee_name, "confidence": 0.95},
    }
    if employee_id:
        fields["employee_id"] = {"value": employee_id, "confidence": 0.95}
    if date_of_joining:
        fields["date_of_joining"] = {"value": date_of_joining, "confidence": 0.90}
    if designation:
        fields["designation"] = {"value": designation, "confidence": 0.88}
    return fields


def _make_stage05(resolution_result=None):
    """Build a Stage05Resolve with a mocked ResolutionService."""
    mock_db = AsyncMock()
    mock_emb = AsyncMock()

    svc = Stage05Resolve(db=mock_db, embedding_client=mock_emb, qdrant_client=None)

    if resolution_result is not None:
        svc._svc.resolve = AsyncMock(return_value=resolution_result)

    return svc


# ── Happy path ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolved_by_pan_token():
    from resolution.resolution_service import ResolutionResult

    emp_uuid = uuid4()
    result = ResolutionResult(
        employee_uuid=emp_uuid,
        method=ResolutionMethod.EXACT_PAN,
        confidence=1.0,
        candidates=[],
    )
    svc = _make_stage05(result)

    manifest = _manifest(identity_fields=["pan_number", "employee_id", "employee_name"])
    output = await svc.run(
        pan_token="abc123",
        tenant_id=str(uuid4()),
        extracted_fields=_extracted(),
        manifest=manifest,
    )

    assert output.employee_uuid == str(emp_uuid)
    assert output.needs_exception is False
    assert output.method == "EXACT_PAN"


@pytest.mark.asyncio
async def test_resolved_by_employee_id():
    from resolution.resolution_service import ResolutionResult

    emp_uuid = uuid4()
    result = ResolutionResult(
        employee_uuid=emp_uuid,
        method=ResolutionMethod.EMP_ID,
        confidence=1.0,
        candidates=[],
    )
    svc = _make_stage05(result)

    manifest = _manifest(identity_fields=["employee_id", "employee_name"])
    output = await svc.run(
        pan_token=None,
        tenant_id=str(uuid4()),
        extracted_fields=_extracted(employee_id="EMP-789"),
        manifest=manifest,
    )

    assert output.needs_exception is False
    assert output.method == "EMP_ID"


# ── Skip flags from manifest ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pan_not_in_identity_fields_skips_pan_token():
    """When pan_number not in manifest.identity_fields, skip_emp_id flag must be respected."""
    from resolution.resolution_service import ResolutionResult

    emp_uuid = uuid4()
    result = ResolutionResult(
        employee_uuid=emp_uuid,
        method=ResolutionMethod.EMP_ID,
        confidence=1.0,
        candidates=[],
    )
    svc = _make_stage05(result)

    # No pan_number in identity_fields → pan_token passed as None to ResolutionService
    manifest = _manifest(identity_fields=["employee_id", "employee_name"])

    output = await svc.run(
        pan_token="should_be_ignored",
        tenant_id=str(uuid4()),
        extracted_fields=_extracted(employee_id="EMP-001"),
        manifest=manifest,
    )

    # Verify ResolutionService was called with pan_token=None (skipped)
    call_kwargs = svc._svc.resolve.call_args[1]
    assert call_kwargs.get("pan_token") is None


@pytest.mark.asyncio
async def test_employee_id_not_in_identity_fields_sets_skip_emp_id():
    """When employee_id absent from manifest.identity_fields, skip_emp_id=True."""
    from resolution.resolution_service import ResolutionResult

    emp_uuid = uuid4()
    result = ResolutionResult(
        employee_uuid=emp_uuid,
        method=ResolutionMethod.FUZZY_NAME,
        confidence=0.91,
        candidates=[],
    )
    svc = _make_stage05(result)

    manifest = _manifest(identity_fields=["pan_number", "employee_name"])  # no employee_id

    await svc.run(
        pan_token=None,
        tenant_id=str(uuid4()),
        extracted_fields=_extracted(employee_id="EMP-001"),
        manifest=manifest,
    )

    call_kwargs = svc._svc.resolve.call_args[1]
    assert call_kwargs.get("skip_emp_id") is True


@pytest.mark.asyncio
async def test_no_name_in_identity_skips_fuzzy_and_embedding():
    """When employee_name not in identity_fields, both fuzzy and embedding are skipped."""
    from resolution.resolution_service import ResolutionResult

    emp_uuid = uuid4()
    result = ResolutionResult(
        employee_uuid=emp_uuid,
        method=ResolutionMethod.EMP_ID,
        confidence=1.0,
        candidates=[],
    )
    svc = _make_stage05(result)

    # Only employee_id — no name-based matching
    manifest = _manifest(identity_fields=["employee_id"])

    await svc.run(
        pan_token=None,
        tenant_id=str(uuid4()),
        extracted_fields=_extracted(),
        manifest=manifest,
    )

    call_kwargs = svc._svc.resolve.call_args[1]
    assert call_kwargs.get("skip_fuzzy") is True
    assert call_kwargs.get("skip_embedding") is True


# ── Exception paths ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unresolved_sets_needs_exception():
    from resolution.resolution_service import ResolutionResult

    result = ResolutionResult(
        employee_uuid=None,
        method=ResolutionMethod.UNRESOLVED,
        confidence=0.0,
        candidates=[],
    )
    svc = _make_stage05(result)

    manifest = _manifest()
    output = await svc.run(
        pan_token=None,
        tenant_id=str(uuid4()),
        extracted_fields=_extracted(),
        manifest=manifest,
    )

    assert output.needs_exception is True
    assert output.exception_type == "NO_MATCH"
    assert output.employee_uuid is None


@pytest.mark.asyncio
async def test_multiple_low_confidence_candidates_triggers_exception():
    from resolution.resolution_service import ResolutionResult

    emp_uuid = uuid4()
    result = ResolutionResult(
        employee_uuid=emp_uuid,
        method=ResolutionMethod.EMBEDDING,
        confidence=0.87,  # below 0.88 threshold
        candidates=[
            {"employee_uuid": str(emp_uuid), "score": 0.87},
            {"employee_uuid": str(uuid4()), "score": 0.86},  # 2nd candidate
        ],
    )
    svc = _make_stage05(result)

    manifest = _manifest()
    output = await svc.run(
        pan_token=None,
        tenant_id=str(uuid4()),
        extracted_fields=_extracted(),
        manifest=manifest,
    )

    assert output.needs_exception is True
    assert output.exception_type == "MULTIPLE_CANDIDATES"


@pytest.mark.asyncio
async def test_exact_match_never_triggers_exception():
    from resolution.resolution_service import ResolutionResult

    emp_uuid = uuid4()
    result = ResolutionResult(
        employee_uuid=emp_uuid,
        method=ResolutionMethod.EXACT_PAN,
        confidence=1.0,
        candidates=[],
    )
    svc = _make_stage05(result)

    manifest = _manifest()
    output = await svc.run("pan_tok", str(uuid4()), _extracted(), manifest)

    assert output.needs_exception is False
    assert output.exception_type is None


# ── Cross-tenant detection ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cross_tenant_violation_returned_when_pan_belongs_to_other_tenant():
    """
    If pan_token exists in employee_master under a different tenant,
    run() must return CrossTenantViolation before attempting normal resolution.
    """
    uploading_tenant = str(uuid4())
    owner_tenant     = str(uuid4())
    pan_token        = "abc123deadbeef"

    svc = _make_stage05()
    # Simulate DB returning a row from a DIFFERENT tenant
    svc._svc._db.fetchrow = AsyncMock(
        return_value={"tenant_id": owner_tenant}
    )

    manifest = _manifest()
    output = await svc.run(
        pan_token=pan_token,
        tenant_id=uploading_tenant,
        extracted_fields=_extracted(),
        manifest=manifest,
    )

    assert isinstance(output, CrossTenantViolation)
    assert output.violation_type == "CROSS_TENANT"
    assert output.uploading_tenant_id == uploading_tenant
    assert output.owner_tenant_id == owner_tenant
    assert output.pan_token == pan_token


@pytest.mark.asyncio
async def test_no_violation_when_pan_belongs_to_same_tenant():
    """
    If pan_token exists in employee_master for the SAME uploading tenant,
    resolution proceeds normally — no CrossTenantViolation.
    """
    from resolution.resolution_service import ResolutionResult

    tenant_id = str(uuid4())
    emp_uuid  = uuid4()

    svc = _make_stage05(ResolutionResult(
        employee_uuid=emp_uuid,
        method=ResolutionMethod.EXACT_PAN,
        confidence=1.0,
        candidates=[],
    ))
    # DB returns the SAME tenant
    svc._svc._db.fetchrow = AsyncMock(return_value={"tenant_id": tenant_id})

    output = await svc.run(
        pan_token="samepan123",
        tenant_id=tenant_id,
        extracted_fields=_extracted(),
        manifest=_manifest(),
    )

    assert isinstance(output, Stage05Result)
    assert output.needs_exception is False


@pytest.mark.asyncio
async def test_no_violation_when_pan_token_not_in_any_tenant():
    """
    New employee — pan_token not yet in employee_master.
    Resolution proceeds to the normal ladder (may return NO_MATCH).
    """
    from resolution.resolution_service import ResolutionResult

    svc = _make_stage05(ResolutionResult(
        employee_uuid=None,
        method=ResolutionMethod.UNRESOLVED,
        confidence=0.0,
        candidates=[],
    ))
    # DB returns no row — pan_token unknown system-wide
    svc._svc._db.fetchrow = AsyncMock(return_value=None)

    output = await svc.run(
        pan_token="brandnew999",
        tenant_id=str(uuid4()),
        extracted_fields=_extracted(),
        manifest=_manifest(),
    )

    assert isinstance(output, Stage05Result)
    assert output.needs_exception is True
    assert output.exception_type == "NO_MATCH"


@pytest.mark.asyncio
async def test_cross_tenant_check_skipped_when_no_pan_token():
    """
    When pan_token is None (PAN not found in doc), cross-tenant check is skipped entirely.
    Resolution proceeds with employee_id / name fallbacks.
    """
    from resolution.resolution_service import ResolutionResult

    emp_uuid = uuid4()
    svc = _make_stage05(ResolutionResult(
        employee_uuid=emp_uuid,
        method=ResolutionMethod.EMP_ID,
        confidence=1.0,
        candidates=[],
    ))
    # fetchrow should never be called with no pan_token
    svc._svc._db.fetchrow = AsyncMock(return_value={"tenant_id": "should-not-be-checked"})

    output = await svc.run(
        pan_token=None,
        tenant_id=str(uuid4()),
        extracted_fields=_extracted(employee_id="EMP-007"),
        manifest=_manifest(identity_fields=["employee_id", "employee_name"]),
    )

    # fetchrow was not called (pan_token is None, guard is `if pan_token:`)
    svc._svc._db.fetchrow.assert_not_called()
    assert isinstance(output, Stage05Result)
    assert output.needs_exception is False
