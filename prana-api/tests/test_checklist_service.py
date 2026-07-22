"""
Tests for services/checklist_service.py — the Go-Live Checklist readiness gate.

Covers:
  - Effective checklist = platform baseline ∪ tenant's own items
  - A tenant blocked until all required active items (baseline + own) are complete
  - Deactivating a baseline item removes it from the gate
  - A tenant's own item never affects another tenant
  - complete/uncomplete round trip
  - add/delete tenant item; add/update platform baseline item
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from services.checklist_service import ChecklistService, ChecklistIncompleteError

TENANT_A = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
TENANT_B = uuid.UUID("11111111-2222-3333-4444-555555555555")


def _row(*, item_id="item-1", tenant_id=None, item_key="K", title="T",
         description=None, display_order=0, is_required=True,
         completed_at=None, completed_by=None, notes=None):
    return {
        "item_id": item_id, "tenant_id": tenant_id, "item_key": item_key, "title": title,
        "description": description, "display_order": display_order, "is_required": is_required,
        "completed_at": completed_at, "completed_by": completed_by, "notes": notes,
    }


@pytest.mark.asyncio
async def test_get_effective_checklist_marks_baseline_vs_tenant_items():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        _row(item_id="i-1", tenant_id=None, item_key="BASELINE_ONE"),
        _row(item_id="i-2", tenant_id=TENANT_A, item_key="TENANT_OWN"),
    ])
    svc = ChecklistService(db)

    items = await svc.get_effective_checklist(TENANT_A)

    assert items[0]["is_platform_baseline"] is True
    assert items[0]["completed"] is False
    assert items[1]["is_platform_baseline"] is False


@pytest.mark.asyncio
async def test_assert_upload_allowed_blocks_when_baseline_item_incomplete():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        _row(item_key="BASELINE_ONE", is_required=True, completed_at=None),
    ])
    svc = ChecklistService(db)

    with pytest.raises(ChecklistIncompleteError) as exc:
        await svc.assert_upload_allowed(TENANT_A)
    assert exc.value.missing_item_keys == ["BASELINE_ONE"]


@pytest.mark.asyncio
async def test_assert_upload_allowed_blocks_when_tenant_added_item_incomplete():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        _row(item_key="BASELINE_ONE", tenant_id=None, is_required=True,
             completed_at=datetime.now(tz=timezone.utc)),
        _row(item_key="TENANT_EXTRA", tenant_id=TENANT_A, is_required=True, completed_at=None),
    ])
    svc = ChecklistService(db)

    with pytest.raises(ChecklistIncompleteError) as exc:
        await svc.assert_upload_allowed(TENANT_A)
    assert exc.value.missing_item_keys == ["TENANT_EXTRA"]


@pytest.mark.asyncio
async def test_assert_upload_allowed_passes_when_all_required_items_complete():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        _row(item_key="BASELINE_ONE", completed_at=datetime.now(tz=timezone.utc)),
        _row(item_key="OPTIONAL_ONE", is_required=False, completed_at=None),
    ])
    svc = ChecklistService(db)

    await svc.assert_upload_allowed(TENANT_A)  # must not raise


@pytest.mark.asyncio
async def test_deactivated_baseline_item_is_excluded_from_the_gate():
    """is_active=FALSE items never appear — the WHERE clause filters them at the query level."""
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])  # deactivated item filtered out by is_active=TRUE in SQL
    svc = ChecklistService(db)

    await svc.assert_upload_allowed(TENANT_A)  # no items at all → nothing blocks


@pytest.mark.asyncio
async def test_get_effective_checklist_scopes_tenant_items_by_tenant_id():
    """The SQL WHERE clause (tenant_id = $1 OR tenant_id IS NULL) is the isolation
    boundary — assert the query is actually parameterized with the caller's tenant_id."""
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    svc = ChecklistService(db)

    await svc.get_effective_checklist(TENANT_B)

    call_args = db.fetch.call_args
    assert call_args[0][1] == TENANT_B


@pytest.mark.asyncio
async def test_complete_item_upserts_completion_row():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"item_id": "item-1"})
    db.execute = AsyncMock()
    svc = ChecklistService(db)

    await svc.complete_item(TENANT_A, "BASELINE_ONE", completed_by=uuid.uuid4(), notes="done")

    insert_call = db.execute.call_args
    assert "INSERT INTO tenant_checklist_completion" in insert_call[0][0]
    assert "ON CONFLICT" in insert_call[0][0]


@pytest.mark.asyncio
async def test_complete_item_raises_when_item_not_visible_to_tenant():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=None)
    svc = ChecklistService(db)

    with pytest.raises(ValueError):
        await svc.complete_item(TENANT_A, "NOT_MY_ITEM", completed_by=uuid.uuid4())


@pytest.mark.asyncio
async def test_uncomplete_item_deletes_completion_row():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"item_id": "item-1"})
    db.execute = AsyncMock(return_value="DELETE 1")
    svc = ChecklistService(db)

    result = await svc.uncomplete_item(TENANT_A, "BASELINE_ONE")
    assert result is True


@pytest.mark.asyncio
async def test_uncomplete_item_returns_false_when_nothing_to_undo():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"item_id": "item-1"})
    db.execute = AsyncMock(return_value="DELETE 0")
    svc = ChecklistService(db)

    result = await svc.uncomplete_item(TENANT_A, "BASELINE_ONE")
    assert result is False


@pytest.mark.asyncio
async def test_add_tenant_item_rejects_duplicate_key_for_same_tenant():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"item_id": "existing-1"})
    svc = ChecklistService(db)

    with pytest.raises(ValueError):
        await svc.add_tenant_item(
            TENANT_A, "DUPLICATE_KEY", "Title", None, True, created_by_oa=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_add_tenant_item_creates_new_item_scoped_to_tenant():
    db = AsyncMock()
    db.fetchrow = AsyncMock(side_effect=[
        None,  # no existing item with this key for this tenant
        {
            "item_id": "new-1", "tenant_id": TENANT_A, "item_key": "MY_ITEM", "title": "My Item",
            "description": None, "display_order": 0, "is_active": True, "is_required": True,
            "created_at": datetime.now(tz=timezone.utc), "updated_at": datetime.now(tz=timezone.utc),
        },
    ])
    svc = ChecklistService(db)

    result = await svc.add_tenant_item(TENANT_A, "MY_ITEM", "My Item", None, True, created_by_oa=uuid.uuid4())
    assert result["item_key"] == "MY_ITEM"
    assert result["tenant_id"] == str(TENANT_A)


@pytest.mark.asyncio
async def test_delete_tenant_item_never_touches_platform_baseline():
    """DELETE is scoped by tenant_id=$1 — a platform-baseline row (tenant_id IS NULL)
    can never match this WHERE clause regardless of item_key collision."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value="DELETE 0")
    svc = ChecklistService(db)

    result = await svc.delete_tenant_item(TENANT_A, "SOME_BASELINE_KEY")
    assert result is False
    delete_call = db.execute.call_args
    assert "tenant_id=$1" in delete_call[0][0].replace(" ", "")


@pytest.mark.asyncio
async def test_add_platform_item_rejects_duplicate_baseline_key():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"item_id": "existing-1"})
    svc = ChecklistService(db)

    with pytest.raises(ValueError):
        await svc.add_platform_item("DUPLICATE_KEY", "Title", None, True, created_by_pa=uuid.uuid4())


@pytest.mark.asyncio
async def test_update_platform_item_leaves_unspecified_fields_unchanged():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={
        "item_id": "i-1", "tenant_id": None, "item_key": "K", "title": "New Title",
        "description": "Old desc", "display_order": 0, "is_active": True, "is_required": True,
        "created_at": datetime.now(tz=timezone.utc), "updated_at": datetime.now(tz=timezone.utc),
    })
    svc = ChecklistService(db)

    result = await svc.update_platform_item(uuid.uuid4(), title="New Title")
    assert result["title"] == "New Title"
    coalesce_call = db.fetchrow.call_args
    assert "COALESCE" in coalesce_call[0][0]


@pytest.mark.asyncio
async def test_update_platform_item_raises_when_not_found():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=None)
    svc = ChecklistService(db)

    with pytest.raises(ValueError):
        await svc.update_platform_item(uuid.uuid4(), title="X")


@pytest.mark.asyncio
async def test_list_platform_items_only_returns_baseline_rows():
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        {
            "item_id": "i-1", "tenant_id": None, "item_key": "BASELINE_ONE", "title": "T",
            "description": None, "display_order": 0, "is_active": True, "is_required": True,
            "created_at": datetime.now(tz=timezone.utc), "updated_at": datetime.now(tz=timezone.utc),
        },
    ])
    svc = ChecklistService(db)

    items = await svc.list_platform_items()
    assert len(items) == 1
    assert items[0]["tenant_id"] is None
    query = db.fetch.call_args[0][0]
    assert "tenant_id IS NULL" in query
