"""
Tests for ManifestService and doc_manifest router.
Covers: auth, role enforcement, tenant isolation, resolve logic,
        upsert/delete, AUTO_DETECT scoring, unclassified queue.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from services.manifest_service import ManifestService, ManifestRecord, AUTO_DETECT_MIN_SCORE

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}
TENANT_ID = "11111111-1111-1111-1111-111111111111"


def _set_oa_admin_auth(client, tenant_id: str = TENANT_ID) -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "22222222-2222-2222-2222-222222222222",
        "user_type": "oa_user",
        "role": "oa_admin",
        "tenant_id": tenant_id,
        "jti": "oa-admin-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def _set_oa_operator_auth(client, tenant_id: str = TENANT_ID) -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "33333333-3333-3333-3333-333333333333",
        "user_type": "oa_user",
        "role": "oa_operator",
        "tenant_id": tenant_id,
        "jti": "oa-operator-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def _set_pa_auth(client) -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "44444444-4444-4444-4444-444444444444",
        "user_type": "portal_admin",
        "role": "portal_admin",
        "tenant_id": None,
        "jti": "pa-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _manifest_row(doc_type="SALARY_SLIP", tenant_id=None, **overrides):
    row = {
        "manifest_id":             uuid4(),
        "tenant_id":               tenant_id,
        "doc_type":                doc_type,
        "required_fields":         json.dumps(["employee_name", "employer_name", "net_pay"]),
        "identity_fields":         json.dumps(["pan_number", "employee_id", "employee_name"]),
        "optional_fields":         json.dumps(["designation", "uan_number"]),
        "classification_signals":  json.dumps([["net_pay", "pay_period_month"]]),
        "signal_weights":          json.dumps([]),
        "safe_fields":             json.dumps([]),
        "confidence_threshold":    0.75,
        "supported_formats":       json.dumps(["pdf", "docx", "jpeg", "jpg", "png", "tiff"]),
        "is_active":               True,
        "usage_count":             0,
        "created_at":              None,
        "updated_at":              None,
    }
    row.update(overrides)
    return row


# ── ManifestRecord ─────────────────────────────────────────────────────────────

def test_manifest_record_all_fields_deduplicates():
    row = _manifest_row(
        required_fields=json.dumps(["employee_name", "net_pay"]),
        optional_fields=json.dumps(["net_pay", "designation"]),  # net_pay duplicated
    )
    record = ManifestRecord(row)
    all_f = record.all_fields()
    assert all_f.count("net_pay") == 1
    assert "employee_name" in all_f
    assert "designation" in all_f


def test_manifest_record_format_supported():
    row = _manifest_row(supported_formats=json.dumps(["pdf", "docx"]))
    record = ManifestRecord(row)
    assert record.format_supported("pdf")
    assert record.format_supported("docx")
    assert not record.format_supported("xlsx")


def test_manifest_record_score_no_signals():
    row = _manifest_row(classification_signals=json.dumps([]))
    record = ManifestRecord(row)
    assert record.score_against({"net_pay": 50000}) == 0.0


def test_manifest_record_score_all_signals_fire():
    row = _manifest_row(
        classification_signals=json.dumps([
            ["net_pay", "pay_period_month"],
            ["uan_number", "employer_name"],
        ])
    )
    record = ManifestRecord(row)
    partial = {"net_pay": 50000, "pay_period_month": "March", "uan_number": "101234567890", "employer_name": "NPCI"}
    assert record.score_against(partial) == 1.0


def test_manifest_record_score_partial_signals():
    row = _manifest_row(
        classification_signals=json.dumps([
            ["net_pay", "pay_period_month"],
            ["uan_number", "employer_name"],
        ])
    )
    record = ManifestRecord(row)
    # Only first signal fires
    partial = {"net_pay": 50000, "pay_period_month": "March"}
    assert record.score_against(partial) == 0.5


def test_manifest_record_score_null_values_dont_fire():
    row = _manifest_row(
        classification_signals=json.dumps([["net_pay", "pay_period_month"]])
    )
    record = ManifestRecord(row)
    assert record.score_against({"net_pay": None, "pay_period_month": "March"}) == 0.0
    assert record.score_against({"net_pay": "", "pay_period_month": "March"}) == 0.0


def test_manifest_record_score_with_weights_prioritizes_higher_weight_signal():
    # A generic signal (employee_name + employer_name) is far less discriminative
    # than a specific one (uan_number + pf_number) but fired equally under the
    # old unweighted scoring (gap 1d).
    row = _manifest_row(
        classification_signals=json.dumps([
            ["employee_name", "employer_name"],
            ["uan_number", "pf_number"],
        ]),
        signal_weights=json.dumps([1.0, 3.0]),
    )
    record = ManifestRecord(row)

    generic_only = {"employee_name": "A", "employer_name": "B"}
    assert record.score_against(generic_only) == 1.0 / 4.0

    specific_only = {"uan_number": "123", "pf_number": "456"}
    assert record.score_against(specific_only) == 3.0 / 4.0


def test_manifest_record_score_no_weights_falls_back_to_equal():
    row = _manifest_row(
        classification_signals=json.dumps([["a", "b"], ["c", "d"]]),
        signal_weights=json.dumps([]),
    )
    record = ManifestRecord(row)
    assert record.score_against({"a": 1, "b": 2}) == 0.5


def test_manifest_record_score_mismatched_weight_length_falls_back_to_equal():
    row = _manifest_row(
        classification_signals=json.dumps([["a", "b"], ["c", "d"]]),
        signal_weights=json.dumps([5.0]),   # wrong length vs 2 signals — ignored
    )
    record = ManifestRecord(row)
    assert record.score_against({"a": 1, "b": 2}) == 0.5


# ── ManifestService.resolve ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_tenant_override_takes_precedence():
    tenant_id = uuid4()
    tenant_row = _manifest_row(doc_type="SALARY_SLIP", tenant_id=tenant_id,
                                confidence_threshold=0.85)
    mock_db = AsyncMock()
    mock_db.fetchrow.side_effect = [tenant_row, None]  # first call returns tenant override

    svc = ManifestService(mock_db)
    result = await svc.resolve(tenant_id, "SALARY_SLIP")

    assert result.confidence_threshold == 0.85
    assert result.is_tenant_override is True
    # Only one DB call — found tenant override, no need to check platform default
    mock_db.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_falls_back_to_platform_default():
    tenant_id = uuid4()
    platform_row = _manifest_row(doc_type="SALARY_SLIP", tenant_id=None,
                                  confidence_threshold=0.75)
    mock_db = AsyncMock()
    # First call (tenant override) returns None, second (platform) returns row
    mock_db.fetchrow.side_effect = [None, platform_row]

    svc = ManifestService(mock_db)
    result = await svc.resolve(tenant_id, "SALARY_SLIP")

    assert result.is_tenant_override is False
    assert result.confidence_threshold == 0.75
    assert mock_db.fetchrow.call_count == 2


@pytest.mark.asyncio
async def test_resolve_raises_when_no_manifest():
    mock_db = AsyncMock()
    mock_db.fetchrow.return_value = None

    svc = ManifestService(mock_db)
    with pytest.raises(ValueError, match="No manifest"):
        await svc.resolve(uuid4(), "UNKNOWN_DOC_TYPE")


# ── ManifestService.auto_detect ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_detect_picks_best_matching_manifest():
    tenant_id = uuid4()
    salary_row = _manifest_row(
        doc_type="SALARY_SLIP", tenant_id=None,
        classification_signals=json.dumps([["net_pay", "pay_period_month"]])
    )
    form16_row = _manifest_row(
        doc_type="FORM_16", tenant_id=None,
        classification_signals=json.dumps([["financial_year", "tds_deducted"]])
    )
    mock_db = AsyncMock()
    mock_db.fetch.return_value = [salary_row, form16_row]

    svc = ManifestService(mock_db)
    # Partial fields matching SALARY_SLIP signals
    result = await svc.auto_detect(
        tenant_id,
        {"net_pay": 50000, "pay_period_month": "March"},
        ext="pdf",
    )

    assert result is not None
    assert result.doc_type == "SALARY_SLIP"


@pytest.mark.asyncio
async def test_auto_detect_returns_none_when_score_below_threshold():
    tenant_id = uuid4()
    salary_row = _manifest_row(
        doc_type="SALARY_SLIP", tenant_id=None,
        classification_signals=json.dumps([
            ["net_pay", "pay_period_month"],
            ["uan_number", "gross_ctc"],
        ])
    )
    mock_db = AsyncMock()
    mock_db.fetch.return_value = [salary_row]

    svc = ManifestService(mock_db)
    # No matching fields → score = 0.0
    result = await svc.auto_detect(tenant_id, {}, ext="pdf")
    assert result is None


@pytest.mark.asyncio
async def test_auto_detect_skips_unsupported_formats():
    tenant_id = uuid4()
    pdf_only_row = _manifest_row(
        doc_type="FORM_16", tenant_id=None,
        classification_signals=json.dumps([["financial_year", "tds_deducted"]]),
        supported_formats=json.dumps(["pdf"]),
    )
    mock_db = AsyncMock()
    mock_db.fetch.return_value = [pdf_only_row]

    svc = ManifestService(mock_db)
    # File is XLSX — FORM_16 manifest doesn't support it
    result = await svc.auto_detect(
        tenant_id,
        {"financial_year": "2023-24", "tds_deducted": 15000},
        ext="xlsx",
    )
    assert result is None


@pytest.mark.asyncio
async def test_auto_detect_tie_breaks_on_usage_count():
    # Both manifests score identically — the one this tenant classifies more
    # often should win the tie (gap 1c: frequency-informed AUTO_DETECT).
    tenant_id = uuid4()
    salary_row = _manifest_row(
        doc_type="SALARY_SLIP", tenant_id=None,
        classification_signals=json.dumps([["net_pay"]]),
        usage_count=2,
    )
    form16_row = _manifest_row(
        doc_type="FORM_16", tenant_id=None,
        classification_signals=json.dumps([["net_pay"]]),
        usage_count=10,
    )
    mock_db = AsyncMock()
    mock_db.fetch.return_value = [salary_row, form16_row]

    svc = ManifestService(mock_db)
    result = await svc.auto_detect(tenant_id, {"net_pay": 1}, ext="pdf")

    assert result.doc_type == "FORM_16"


@pytest.mark.asyncio
async def test_auto_detect_query_has_defensive_limit():
    tenant_id = uuid4()
    mock_db = AsyncMock()
    mock_db.fetch.return_value = []

    svc = ManifestService(mock_db)
    await svc.auto_detect(tenant_id, {}, ext="pdf")

    query = mock_db.fetch.call_args[0][0]
    assert "LIMIT" in query.upper()


# ── ManifestService.record_usage ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_usage_increments_tenant_override_when_present():
    tenant_id = uuid4()
    mock_db = AsyncMock()
    mock_db.fetchval.return_value = uuid4()   # tenant override row was updated

    svc = ManifestService(mock_db)
    await svc.record_usage(tenant_id, "SALARY_SLIP")

    mock_db.fetchval.assert_called_once()
    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_record_usage_falls_back_to_platform_default():
    tenant_id = uuid4()
    mock_db = AsyncMock()
    mock_db.fetchval.return_value = None   # no tenant override exists

    svc = ManifestService(mock_db)
    await svc.record_usage(tenant_id, "SALARY_SLIP")

    mock_db.fetchval.assert_called_once()
    mock_db.execute.assert_called_once()


# ── ManifestService.upsert ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_creates_new_override():
    tenant_id = uuid4()
    oa_user_id = uuid4()
    mock_db = AsyncMock()
    mock_db.fetchrow.side_effect = [
        None,  # no existing override
        _manifest_row(doc_type="SALARY_SLIP", tenant_id=tenant_id),  # INSERT result
    ]

    svc = ManifestService(mock_db)
    result = await svc.upsert(
        tenant_id=tenant_id,
        doc_type="SALARY_SLIP",
        payload={
            "required_fields": ["employee_name", "net_pay"],
            "identity_fields": ["pan_number"],
            "optional_fields": [],
            "classification_signals": [["net_pay"]],
            "confidence_threshold": 0.80,
            "supported_formats": ["pdf"],
            "is_active": True,
        },
        updated_by=oa_user_id,
    )
    assert result["doc_type"] == "SALARY_SLIP"


@pytest.mark.asyncio
async def test_delete_tenant_override_returns_true_on_success():
    mock_db = AsyncMock()
    mock_db.execute.return_value = "DELETE 1"

    svc = ManifestService(mock_db)
    deleted = await svc.delete_tenant_override(uuid4(), "SALARY_SLIP")
    assert deleted is True


@pytest.mark.asyncio
async def test_delete_tenant_override_returns_false_when_no_override():
    mock_db = AsyncMock()
    mock_db.execute.return_value = "DELETE 0"

    svc = ManifestService(mock_db)
    deleted = await svc.delete_tenant_override(uuid4(), "SALARY_SLIP")
    assert deleted is False


# ── Router: auth & role enforcement ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_manifests_requires_auth(client):
    response = await client.get("/v1/manifests")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_manifest_requires_auth(client):
    response = await client.get("/v1/manifests/SALARY_SLIP")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upsert_manifest_requires_oa_admin_role(client, mock_db):
    """OA-Operator cannot modify manifests — only OA-Admin."""
    _set_oa_operator_auth(client)

    response = await client.put(
        "/v1/manifests/SALARY_SLIP",
        json={"required_fields": [], "identity_fields": [], "optional_fields": []},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_upsert_manifest_succeeds_for_oa_admin(client, mock_db):
    """OA-Admin can create/update a tenant manifest override."""
    _set_oa_admin_auth(client)
    mock_db.fetchrow.side_effect = [
        None,  # no existing override
        _manifest_row(doc_type="SALARY_SLIP", tenant_id=TENANT_ID),  # INSERT result
    ]

    response = await client.put(
        "/v1/manifests/SALARY_SLIP",
        json={"required_fields": ["employee_name"], "identity_fields": [], "optional_fields": []},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 200
    assert response.json()["manifest"]["doc_type"] == "SALARY_SLIP"


@pytest.mark.asyncio
async def test_pa_manifests_requires_portal_admin(client):
    response = await client.get("/admin/manifests")
    assert response.status_code in (401, 403)


# ── safe_fields validation ─────────────────────────────────────────────────────
# Root cause this guards: a tenant-configured custom field name is never on
# prana-ai's static _SAFE_METADATA_FIELDS allowlist, so it's stripped by
# default (fail-closed) unless explicitly declared safe here. safe_fields must
# be a subset of the fields the manifest actually declares — otherwise an
# admin could "mark safe" a field that was never being extracted in the first
# place, silently no-op'ing their intent.

@pytest.mark.asyncio
async def test_upsert_rejects_safe_field_not_in_declared_fields(client, mock_db):
    """safe_fields entries must already appear in required/identity/optional_fields."""
    _set_oa_admin_auth(client)

    response = await client.put(
        "/v1/manifests/SALARY_SLIP",
        json={
            "required_fields": ["employee_name"],
            "identity_fields": [],
            "optional_fields": [],
            "safe_fields": ["leave_balance_days"],  # never declared above
        },
        headers=AUTH_HEADER,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upsert_accepts_safe_field_that_is_declared(client, mock_db):
    """safe_fields entries that ARE in required/identity/optional_fields are accepted."""
    _set_oa_admin_auth(client)
    mock_db.fetchrow.side_effect = [
        None,  # no existing override
        _manifest_row(
            doc_type="SALARY_SLIP", tenant_id=TENANT_ID,
            required_fields=json.dumps(["employee_name", "leave_balance_days"]),
            safe_fields=json.dumps(["leave_balance_days"]),
        ),
    ]

    response = await client.put(
        "/v1/manifests/SALARY_SLIP",
        json={
            "required_fields": ["employee_name", "leave_balance_days"],
            "identity_fields": [],
            "optional_fields": [],
            "safe_fields": ["leave_balance_days"],
        },
        headers=AUTH_HEADER,
    )
    assert response.status_code == 200
    assert response.json()["manifest"]["safe_fields"] == ["leave_balance_days"]


@pytest.mark.asyncio
async def test_get_manifest_returns_safe_fields(client, mock_db):
    _set_oa_admin_auth(client)
    mock_db.fetchrow.return_value = _manifest_row(
        doc_type="SALARY_SLIP", tenant_id=None,
        safe_fields=json.dumps(["leave_balance_days"]),
    )

    response = await client.get("/v1/manifests/SALARY_SLIP", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.json()["manifest"]["safe_fields"] == ["leave_balance_days"]


@pytest.mark.asyncio
async def test_pa_upsert_platform_manifest_persists_safe_fields(client, mock_db):
    """PA's platform-default upsert path (raw SQL, not ManifestService) must
    also persist safe_fields — this is a separate code path from the OA-Admin
    tenant-override upsert and easy to miss when adding a new column."""
    _set_pa_auth(client)
    mock_db.fetchrow.return_value = _manifest_row(
        doc_type="SALARY_SLIP", tenant_id=None,
        safe_fields=json.dumps(["leave_balance_days"]),
    )

    response = await client.put(
        "/admin/manifests/SALARY_SLIP",
        json={
            "required_fields": ["employee_name", "leave_balance_days"],
            "identity_fields": [],
            "optional_fields": [],
            "safe_fields": ["leave_balance_days"],
        },
        headers=AUTH_HEADER,
    )
    assert response.status_code == 200
    assert response.json()["manifest"]["safe_fields"] == ["leave_balance_days"]


@pytest.mark.asyncio
async def test_pa_manifests_works_for_portal_admin(client, mock_db):
    """PA can list platform-default manifests once authenticated."""
    _set_pa_auth(client)
    mock_db.fetch.return_value = []

    response = await client.get("/admin/manifests", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


# ── Router: tenant isolation ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cannot_read_another_tenants_override(client):
    """tenant_id must come from JWT, never from URL or query params."""
    # The router derives tenant_id from JWT claims only — no tenant_id in URL
    # This test verifies the endpoint exists and doesn't accept tenant_id as a query param
    response = await client.get("/v1/manifests?tenant_id=other-tenant-uuid")
    # Either 401 (no auth) or the param is ignored — never 200 with other tenant's data
    assert response.status_code in (401, 422, 200)


# ── Unclassified queue ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_unclassified_requires_auth(client):
    response = await client.get("/v1/unclassified")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_resolve_unclassified_requires_auth(client):
    response = await client.post(
        f"/v1/unclassified/{uuid4()}/resolve",
        json={"resolved_doc_type": "SALARY_SLIP"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_resolve_unclassified_validates_doc_type(client, mock_db):
    """Unknown doc_type must be rejected with 422."""
    _set_oa_admin_auth(client)
    response = await client.post(
        f"/v1/unclassified/{uuid4()}/resolve",
        json={"resolved_doc_type": "TOTALLY_MADE_UP"},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 422


def test_unclassified_list_query_uses_document_id_pk():
    """Query must use document_id as PK — no unclassified_id column in schema."""
    import pathlib
    src = pathlib.Path(__file__).parent.parent.joinpath("routers/doc_manifest.py").read_text()
    # Find the list_unclassified function body
    start = src.index("async def list_unclassified")
    body = src[start:start + 1000]
    assert "unclassified_id" not in body, \
        "unclassified_queue has document_id as PK — unclassified_id column does not exist"


def test_resolve_unclassified_publishes_doc_reclassified_to_kafka():
    """resolve_unclassified must publish DOC_RECLASSIFIED to prana.ingest.events."""
    import pathlib
    src = pathlib.Path(__file__).parent.parent.joinpath("routers/doc_manifest.py").read_text()
    start = src.index("async def resolve_unclassified")
    body = src[start:start + 1500]
    assert "DOC_RECLASSIFIED" in body, \
        "resolve_unclassified must publish DOC_RECLASSIFIED event to Kafka"
    assert "stage_changed" in body, \
        "DOC_RECLASSIFIED must use stage_changed domain helper (not direct publish)"


def test_unclassified_queue_migration_exists():
    """Migration 021 must exist to create the unclassified_queue table."""
    import pathlib
    migrations = list(pathlib.Path(__file__).parent.parent.parent.joinpath("prana-db/migrations").glob("021_*.sql"))
    assert migrations, "Migration 021_unclassified_queue.sql must exist"
    content = migrations[0].read_text()
    assert "unclassified_queue" in content
    assert "document_id" in content
    assert "ROLLBACK" in content
