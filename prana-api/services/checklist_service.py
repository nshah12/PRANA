"""
ChecklistService — the Go-Live Checklist readiness gate.

Effective checklist for a tenant = platform baseline (setup_checklist_item
rows with tenant_id IS NULL, PA-owned) UNION that tenant's own items
(tenant_id = X, OA-Admin-owned), both filtered is_active = TRUE. Additive —
a tenant can add on top of the baseline but never remove or replace it.

Completion is a manual OA-Admin confirmation (tenant_checklist_completion
row) in V1 — no auto-detection against tenant.grievance_officer_name /
tenant.dpa_accepted_at etc. Absence of a completion row = incomplete; when PA
adds a new baseline item later, every existing tenant is simply incomplete on
it until an OA-Admin checks it off — no backfill needed.

Zero Temporal imports — plain service class per project convention.
"""

import logging
from typing import Optional
from uuid import UUID

log = logging.getLogger(__name__)


class ChecklistIncompleteError(Exception):
    """
    Raised by assert_upload_allowed() when required checklist items are
    incomplete. Callers (ingest.py's upload entrypoints) catch this and
    translate it to HTTPException(403, PranaError.SETUP_CHECKLIST_INCOMPLETE)
    — kept framework-agnostic here like every other service in this codebase.
    """

    def __init__(self, missing_item_keys: list[str]):
        self.missing_item_keys = missing_item_keys
        super().__init__(f"Incomplete required setup checklist items: {missing_item_keys}")


class ChecklistService:

    def __init__(self, db):
        self._db = db

    async def get_effective_checklist(self, tenant_id: UUID) -> list[dict]:
        """Baseline ∪ tenant's own active items, joined with this tenant's completion status."""
        rows = await self._db.fetch(
            """
            SELECT i.item_id, i.tenant_id, i.item_key, i.title, i.description,
                   i.display_order, i.is_required,
                   c.completed_at, c.completed_by, c.notes
            FROM setup_checklist_item i
            LEFT JOIN tenant_checklist_completion c
              ON c.item_id = i.item_id AND c.tenant_id = $1
            WHERE (i.tenant_id = $1 OR i.tenant_id IS NULL) AND i.is_active = TRUE
            ORDER BY i.display_order, i.item_key
            """,
            tenant_id,
        )
        return [_serialize_checklist_row(dict(r)) for r in rows]

    async def assert_upload_allowed(self, tenant_id: UUID) -> None:
        """Raises ChecklistIncompleteError if any required active item lacks a completion row."""
        items = await self.get_effective_checklist(tenant_id)
        missing = [i["item_key"] for i in items if i["is_required"] and not i["completed"]]
        if missing:
            raise ChecklistIncompleteError(missing)

    async def complete_item(
        self, tenant_id: UUID, item_key: str, completed_by: UUID, notes: Optional[str] = None,
    ) -> None:
        """OA-Admin manually confirms a checklist item (baseline or their own) is done."""
        item = await self._db.fetchrow(
            "SELECT item_id FROM setup_checklist_item "
            "WHERE item_key=$1 AND (tenant_id=$2 OR tenant_id IS NULL) AND is_active=TRUE",
            item_key, tenant_id,
        )
        if not item:
            raise ValueError(f"No active checklist item with key {item_key!r} visible to this tenant")
        await self._db.execute(
            """
            INSERT INTO tenant_checklist_completion (tenant_id, item_id, completed_by, notes)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (tenant_id, item_id) DO UPDATE SET
              completed_at = NOW(), completed_by = EXCLUDED.completed_by, notes = EXCLUDED.notes
            """,
            tenant_id, item["item_id"], completed_by, notes,
        )

    async def uncomplete_item(self, tenant_id: UUID, item_key: str) -> bool:
        """Undo a completion (e.g. the underlying condition regressed). False if nothing to undo."""
        item = await self._db.fetchrow(
            "SELECT item_id FROM setup_checklist_item WHERE item_key=$1 AND (tenant_id=$2 OR tenant_id IS NULL)",
            item_key, tenant_id,
        )
        if not item:
            return False
        result = await self._db.execute(
            "DELETE FROM tenant_checklist_completion WHERE tenant_id=$1 AND item_id=$2",
            tenant_id, item["item_id"],
        )
        return result != "DELETE 0"

    async def add_tenant_item(
        self, tenant_id: UUID, item_key: str, title: str,
        description: Optional[str], is_required: bool, created_by_oa: UUID,
    ) -> dict:
        """OA-Admin adds a tenant-specific checklist item on top of the platform baseline."""
        existing = await self._db.fetchrow(
            "SELECT item_id FROM setup_checklist_item WHERE tenant_id=$1 AND item_key=$2",
            tenant_id, item_key,
        )
        if existing:
            raise ValueError(f"item_key {item_key!r} already exists for this tenant")
        row = await self._db.fetchrow(
            """
            INSERT INTO setup_checklist_item
              (tenant_id, item_key, title, description, is_required, created_by_oa)
            VALUES ($1,$2,$3,$4,$5,$6)
            RETURNING item_id, tenant_id, item_key, title, description,
                      display_order, is_active, is_required, created_at, updated_at
            """,
            tenant_id, item_key, title, description, is_required, created_by_oa,
        )
        return _serialize_item(dict(row))

    async def delete_tenant_item(self, tenant_id: UUID, item_key: str) -> bool:
        """OA-Admin removes their own tenant-specific item. Never touches the platform baseline."""
        result = await self._db.execute(
            "DELETE FROM setup_checklist_item WHERE tenant_id=$1 AND item_key=$2",
            tenant_id, item_key,
        )
        return result != "DELETE 0"

    # ── Portal Admin — platform-baseline management ────────────────────────

    async def list_platform_items(self) -> list[dict]:
        rows = await self._db.fetch(
            """
            SELECT item_id, tenant_id, item_key, title, description,
                   display_order, is_active, is_required, created_at, updated_at
            FROM setup_checklist_item
            WHERE tenant_id IS NULL
            ORDER BY display_order, item_key
            """
        )
        return [_serialize_item(dict(r)) for r in rows]

    async def add_platform_item(
        self, item_key: str, title: str, description: Optional[str],
        is_required: bool, created_by_pa: UUID, display_order: int = 0,
    ) -> dict:
        existing = await self._db.fetchrow(
            "SELECT item_id FROM setup_checklist_item WHERE tenant_id IS NULL AND item_key=$1",
            item_key,
        )
        if existing:
            raise ValueError(f"item_key {item_key!r} already exists as a platform baseline item")
        row = await self._db.fetchrow(
            """
            INSERT INTO setup_checklist_item
              (tenant_id, item_key, title, description, display_order, is_required, created_by_pa)
            VALUES (NULL,$1,$2,$3,$4,$5,$6)
            RETURNING item_id, tenant_id, item_key, title, description,
                      display_order, is_active, is_required, created_at, updated_at
            """,
            item_key, title, description, display_order, is_required, created_by_pa,
        )
        return _serialize_item(dict(row))

    async def update_platform_item(
        self,
        item_id: UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        display_order: Optional[int] = None,
        is_required: Optional[bool] = None,
        is_active: Optional[bool] = None,
    ) -> dict:
        """PA edits or deactivates a baseline item. None means unchanged (COALESCE)."""
        row = await self._db.fetchrow(
            """
            UPDATE setup_checklist_item SET
              title          = COALESCE($2, title),
              description    = COALESCE($3, description),
              display_order  = COALESCE($4, display_order),
              is_required    = COALESCE($5, is_required),
              is_active      = COALESCE($6, is_active),
              updated_at     = NOW()
            WHERE item_id=$1 AND tenant_id IS NULL
            RETURNING item_id, tenant_id, item_key, title, description,
                      display_order, is_active, is_required, created_at, updated_at
            """,
            item_id, title, description, display_order, is_required, is_active,
        )
        if not row:
            raise ValueError(f"No platform-baseline checklist item with id {item_id}")
        return _serialize_item(dict(row))


def _serialize_checklist_row(row: dict) -> dict:
    return {
        "item_id":              str(row["item_id"]),
        "is_platform_baseline": row["tenant_id"] is None,
        "item_key":             row["item_key"],
        "title":                row["title"],
        "description":          row.get("description"),
        "display_order":        row["display_order"],
        "is_required":          row["is_required"],
        "completed":            row["completed_at"] is not None,
        "completed_at":         row["completed_at"].isoformat() if row.get("completed_at") else None,
        "completed_by":         str(row["completed_by"]) if row.get("completed_by") else None,
        "notes":                row.get("notes"),
    }


def _serialize_item(row: dict) -> dict:
    return {
        "item_id":       str(row["item_id"]),
        "tenant_id":     str(row["tenant_id"]) if row.get("tenant_id") else None,
        "item_key":      row["item_key"],
        "title":         row["title"],
        "description":   row.get("description"),
        "display_order": row["display_order"],
        "is_active":     row["is_active"],
        "is_required":   row["is_required"],
        "created_at":    row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at":    row["updated_at"].isoformat() if row.get("updated_at") else None,
    }
