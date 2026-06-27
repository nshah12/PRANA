"""
HRMSSyncService — orchestrates pulling employee records from HRMS connectors.

Flow:
  1. Load connector config from DB (tenant-scoped)
  2. Skip if PAUSED or REVOKED
  3. Decrypt credentials via KMS
  4. Build the right adapter (Darwinbox / Keka)
  5. Call adapter.pull(cursor=last_pulled_at)
  6. For each record: strip salary fields → publish DOC_INGESTED via Kafka
  7. Update cursor (last_pulled_at) + log sync result

Privacy contract: salary/CTC fields are stripped before any record leaves the adapter.
The service does a second strip to be absolutely sure — defence in depth.
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

from connectors.base import strip_salary_fields
from connectors.darwinbox import DarwinboxConnector
from connectors.keka import KekaConnector
from services.hrms_connector_service import HRMSConnectorService

log = logging.getLogger(__name__)

_ADAPTER_REGISTRY = {
    "darwinbox": DarwinboxConnector,
    "keka":      KekaConnector,
}

_svc_conn = HRMSConnectorService()


class HRMSSyncService:

    # ── Config loading ────────────────────────────────────────────────────────

    async def load_connector_config(
        self,
        connector_id: UUID,
        tenant_id: UUID,
        db,
    ) -> dict | None:
        row = await db.fetchrow(
            """
            SELECT c.connector_id, c.tenant_id, c.connector_definition_id,
                   c.enc_credentials, c.kek_arn, c.field_mapping,
                   c.integration_mode, c.pull_schedule, c.status,
                   c.last_pulled_at,
                   d.connector_key
            FROM hrms_connector_config c
            JOIN hrms_connector_definition d
              ON d.connector_definition_id = c.connector_definition_id
            WHERE c.connector_id = $1
              AND c.tenant_id = $2
            """,
            connector_id,
            tenant_id,
        )
        if not row:
            return None
        fm = row["field_mapping"]
        return {
            "connector_id":    str(row["connector_id"]),
            "tenant_id":       str(row["tenant_id"]),
            "connector_key":   row["connector_key"],
            "integration_mode": row["integration_mode"],
            "status":          row["status"],
            "enc_credentials": row["enc_credentials"],
            "kek_arn":         row["kek_arn"],
            "field_mapping":   json.loads(fm) if isinstance(fm, str) else (fm or {}),
            "last_pulled_at":  row["last_pulled_at"].isoformat() if row["last_pulled_at"] else None,
        }

    # ── Adapter factory ───────────────────────────────────────────────────────

    def build_adapter(self, config: dict, kms):
        connector_key = config["connector_key"]
        adapter_cls   = _ADAPTER_REGISTRY.get(connector_key)
        if not adapter_cls:
            raise ValueError(f"Unknown connector_key '{connector_key}'. Supported: {list(_ADAPTER_REGISTRY)}")

        creds_bytes = kms.decrypt(config["enc_credentials"], config["kek_arn"])
        credentials = json.loads(creds_bytes)
        field_mapping = config.get("field_mapping") or {}

        return adapter_cls(credentials=credentials, field_mapping=field_mapping)

    # ── Pull sync ─────────────────────────────────────────────────────────────

    async def run_pull_sync(
        self,
        connector_id: UUID,
        tenant_id: UUID,
        db,
        kms,
        kafka,
        temporal_run_id: str | None = None,
    ) -> dict:
        """
        Full pull sync cycle. Returns summary: {docs_pushed, docs_failed, skipped}.
        """
        config = await self.load_connector_config(
            connector_id=connector_id, tenant_id=tenant_id, db=db
        )
        if not config:
            log.warning("HRMS sync: connector not found connector_id=%s tenant=%s", connector_id, tenant_id)
            return {"skipped": True, "reason": "NOT_FOUND"}

        if config["status"] != "ACTIVE":
            log.info("HRMS sync: connector is %s — skipping", config["status"])
            return {"skipped": True, "reason": config["status"]}

        cursor = config.get("last_pulled_at")

        # Log sync start
        sync_id = await _svc_conn.log_sync_start(
            connector_id=connector_id,
            tenant_id=tenant_id,
            sync_mode="PULL",
            cursor_before=cursor,
            temporal_run_id=temporal_run_id,
            db=db,
        )

        docs_pushed = 0
        docs_failed = 0
        next_cursor = cursor

        try:
            adapter = self.build_adapter(config=config, kms=kms)
            result  = await adapter.pull(cursor=cursor)
            records = result.get("records", [])
            next_cursor = result.get("next_cursor") or cursor

            for record in records:
                # Defence-in-depth salary strip
                clean = strip_salary_fields(record)
                try:
                    await self._publish_employee_record(
                        record=clean,
                        tenant_id=tenant_id,
                        connector_id=connector_id,
                        kafka=kafka,
                    )
                    docs_pushed += 1
                except Exception:
                    log.exception("Failed to publish HRMS record emp=%s", record.get("employee_id"))
                    docs_failed += 1

            await _svc_conn.log_sync_complete(
                sync_id=sync_id,
                status="SUCCESS" if docs_failed == 0 else "PARTIAL",
                docs_pushed=docs_pushed,
                docs_failed=docs_failed,
                cursor_after=str(next_cursor) if next_cursor else None,
                db=db,
            )

        except Exception as exc:
            log.exception("HRMS pull sync failed connector_id=%s", connector_id)
            await _svc_conn.log_sync_complete(
                sync_id=sync_id,
                status="FAILED",
                docs_pushed=docs_pushed,
                docs_failed=docs_failed,
                error_message=str(exc),
                db=db,
            )
            raise

        return {
            "sync_id":     str(sync_id),
            "docs_pushed": docs_pushed,
            "docs_failed": docs_failed,
            "next_cursor": next_cursor,
        }

    # ── Kafka publish ─────────────────────────────────────────────────────────

    async def _publish_employee_record(
        self,
        record: dict,
        tenant_id: UUID,
        connector_id: UUID,
        kafka,
    ) -> None:
        """Publish a salary-stripped employee record via the employee_event domain helper."""
        await kafka.employee_event({
            "event_type":    "HRMS_EMPLOYEE_SYNCED",
            "tenant_id":     str(tenant_id),
            "connector_id":  str(connector_id),
            "employee_data": record,
        })
