"""
Resolution ladder unit tests.

Verifies that each of the 4 levels fires in the correct priority order
and that UNRESOLVED is returned only when all levels fail.
"""
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from resolution.resolution_service import ResolutionService, ResolutionMethod


_EMP_UUID = UUID("11111111-1111-1111-1111-111111111111")
_PAN_TOKEN = "abc123pantokenhmac"


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_embedding():
    return AsyncMock()


@pytest.fixture
def mock_fuzzy():
    svc = AsyncMock()
    svc.match = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def mock_qdrant():
    q = AsyncMock()
    q.search = AsyncMock(return_value=[])
    return q


def _make_svc(mock_db, mock_embedding, mock_fuzzy, mock_qdrant):
    return ResolutionService(
        db=mock_db,
        embedding_client=mock_embedding,
        fuzzy_service=mock_fuzzy,
        qdrant_client=mock_qdrant,
    )


@pytest.mark.asyncio
async def test_level1_pan_exact_match(mock_db, mock_embedding, mock_fuzzy, mock_qdrant):
    """Level 1: direct pan_token hit returns EXACT_PAN at confidence 1.0."""
    mock_db.fetchrow = AsyncMock(return_value={
        "employee_uuid": str(_EMP_UUID),
        "tenant_id": "tenant-001",
    })
    svc = _make_svc(mock_db, mock_embedding, mock_fuzzy, mock_qdrant)

    result = await svc.resolve(
        pan_token=_PAN_TOKEN,
        tenant_id="tenant-001",
        extracted_fields={"employee_name": {"value": "Rahul", "confidence": 0.97}},
    )

    assert result.method == ResolutionMethod.EXACT_PAN
    assert result.confidence == pytest.approx(1.0)
    assert result.employee_uuid is not None
    # Level 2–4 must NOT have been attempted
    mock_fuzzy.match.assert_not_called()
    mock_qdrant.search.assert_not_called()


@pytest.mark.asyncio
async def test_level2_emp_id_match(mock_db, mock_embedding, mock_fuzzy, mock_qdrant):
    """Level 2: emp_id field in extracted_fields triggers EMP_ID lookup."""
    # Level 1 misses (no pan_token row)
    mock_db.fetchrow = AsyncMock(side_effect=[
        None,  # Level 1 — pan_token miss
        {"employee_uuid": str(_EMP_UUID), "tenant_id": "tenant-001"},  # Level 2 — emp_id hit
    ])
    svc = _make_svc(mock_db, mock_embedding, mock_fuzzy, mock_qdrant)

    result = await svc.resolve(
        pan_token=_PAN_TOKEN,
        tenant_id="tenant-001",
        extracted_fields={
            "employee_name": {"value": "Priya", "confidence": 0.95},
            "employee_id":   {"value": "EMP001", "confidence": 0.98},
        },
    )

    assert result.method == ResolutionMethod.EMP_ID
    assert result.employee_uuid == _EMP_UUID
    mock_fuzzy.match.assert_not_called()


@pytest.mark.asyncio
async def test_level3_fuzzy_name_match(mock_db, mock_embedding, mock_fuzzy, mock_qdrant):
    """Level 3: fuzzy name+DOJ match when pan_token and emp_id both miss."""
    mock_db.fetchrow = AsyncMock(return_value=None)  # Levels 1 & 2 miss
    mock_fuzzy.match = AsyncMock(return_value={
        "employee_uuid": str(_EMP_UUID),
        "score": 0.91,
    })
    svc = _make_svc(mock_db, mock_embedding, mock_fuzzy, mock_qdrant)

    result = await svc.resolve(
        pan_token=_PAN_TOKEN,
        tenant_id="tenant-001",
        extracted_fields={
            "employee_name": {"value": "Amit Patel", "confidence": 0.95},
            "date_of_joining": {"value": "2021-06-01", "confidence": 0.88},
        },
    )

    assert result.method == ResolutionMethod.FUZZY_NAME
    assert result.confidence >= 0.88
    mock_qdrant.search.assert_not_called()


@pytest.mark.asyncio
async def test_level4_embedding_match(mock_db, mock_embedding, mock_fuzzy, mock_qdrant):
    """Level 4: embedding cosine similarity when levels 1–3 all miss."""
    mock_db.fetchrow = AsyncMock(return_value=None)
    mock_fuzzy.match = AsyncMock(return_value=None)
    mock_embedding.embed = AsyncMock(return_value=[0.1] * 1024)
    mock_qdrant.search = AsyncMock(return_value=[{
        "payload": {"employee_uuid": str(_EMP_UUID)},
        "score": 0.94,
    }])
    svc = _make_svc(mock_db, mock_embedding, mock_fuzzy, mock_qdrant)

    result = await svc.resolve(
        pan_token=_PAN_TOKEN,
        tenant_id="tenant-001",
        extracted_fields={
            "employee_name": {"value": "Ravi Kumar", "confidence": 0.80},
        },
    )

    assert result.method == ResolutionMethod.EMBEDDING
    assert result.confidence >= 0.92


@pytest.mark.asyncio
async def test_all_levels_miss_returns_unresolved(mock_db, mock_embedding, mock_fuzzy, mock_qdrant):
    """UNRESOLVED when all 4 levels fail."""
    mock_db.fetchrow = AsyncMock(return_value=None)
    mock_fuzzy.match = AsyncMock(return_value=None)
    mock_embedding.embed = AsyncMock(return_value=[0.1] * 1024)
    mock_qdrant.search = AsyncMock(return_value=[])  # no embeddings either
    svc = _make_svc(mock_db, mock_embedding, mock_fuzzy, mock_qdrant)

    result = await svc.resolve(
        pan_token=_PAN_TOKEN,
        tenant_id="tenant-001",
        extracted_fields={"employee_name": {"value": "Unknown Person", "confidence": 0.60}},
    )

    assert result.method == ResolutionMethod.UNRESOLVED
    assert result.employee_uuid is None
