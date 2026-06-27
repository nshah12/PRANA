"""
HRMSConnectorService — two-level HRMS connector management.

Level 1 (PA): connector_definition — which connectors the platform supports.
Level 2 (Tenant): hrms_connector_config — which connector a tenant uses + encrypted creds.

Privacy: credentials are always KMS-encrypted before DB write; never stored plaintext.
Tenant isolation: every DB call that touches hrms_connector_config includes tenant_id.
"""
from __future__ import annotations

import json
import logging
from uuid import UUID, uuid4

log = logging.getLogger(__name__)

_VALID_AUTH_METHODS = {"OAUTH2", "API_KEY", "WEBHOOK", "SFTP"}
_VALID_MODES        = {"PULL", "PUSH", "WEBHOOK", "SHARED_LOCATION"}
_VALID_STATUSES     = {"ACTIVE", "PAUSED", "REVOKED"}


class HRMSConnectorService:

    # ── PA: connector definition (factory) ────────────────────────────────────

    async def list_definitions(self, db) -> list[dict]:
        rows = await db.fetch(
            """
            SELECT connector_definition_id, connector_key, display_name,
                   auth_method, supported_modes, canonical_field_schema,
                   docs_url, is_active, created_at, updated_at
            FROM hrms_connector_definition
            WHERE is_active = TRUE
            ORDER BY display_name
            """
        )
        return [self._serialize_definition(r) for r in rows]

    async def get_definition(self, connector_key: str, db) -> dict | None:
        row = await db.fetchrow(
            """
            SELECT connector_definition_id, connector_key, display_name,
                   auth_method, supported_modes, canonical_field_schema,
                   docs_url, is_active, created_at, updated_at
            FROM hrms_connector_definition
            WHERE connector_key = $1
            """,
            connector_key,
        )
        return self._serialize_definition(row) if row else None

    async def get_definition_by_id(self, connector_definition_id: UUID, db) -> dict | None:
        row = await db.fetchrow(
            """
            SELECT connector_definition_id, connector_key, display_name,
                   auth_method, supported_modes, canonical_field_schema,
                   docs_url, is_active, created_at, updated_at
            FROM hrms_connector_definition
            WHERE connector_definition_id = $1
            """,
            connector_definition_id,
        )
        return self._serialize_definition(row) if row else None

    async def create_definition(
        self,
        connector_key: str,
        display_name: str,
        auth_method: str,
        supported_modes: list[str],
        canonical_field_schema: dict,
        db,
        docs_url: str | None = None,
        logo_url: str | None = None,
    ) -> UUID:
        if auth_method not in _VALID_AUTH_METHODS:
            raise ValueError(f"auth_method must be one of {_VALID_AUTH_METHODS}")
        invalid_modes = set(supported_modes) - _VALID_MODES
        if invalid_modes:
            raise ValueError(f"Unsupported modes: {invalid_modes}")

        connector_definition_id = await db.fetchval(
            """
            INSERT INTO hrms_connector_definition
              (connector_key, display_name, auth_method, supported_modes,
               canonical_field_schema, docs_url, logo_url)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING connector_definition_id
            """,
            connector_key,
            display_name,
            auth_method,
            supported_modes,
            json.dumps(canonical_field_schema),
            docs_url,
            logo_url,
        )
        return connector_definition_id

    async def set_definition_active(self, connector_definition_id: UUID, is_active: bool, db) -> None:
        await db.execute(
            """
            UPDATE hrms_connector_definition
            SET is_active = $1, updated_at = NOW()
            WHERE connector_definition_id = $2
            """,
            is_active,
            connector_definition_id,
        )

    # ── Tenant: connector instance config ─────────────────────────────────────

    async def list_tenant_configs(self, tenant_id: UUID, db) -> list[dict]:
        rows = await db.fetch(
            """
            SELECT c.connector_id, c.tenant_id, c.connector_definition_id,
                   c.display_name, c.integration_mode, c.last_pulled_at,
                   c.pull_schedule, c.status, c.field_mapping,
                   c.created_at, c.updated_at,
                   d.connector_key, d.display_name AS definition_name,
                   d.auth_method, d.supported_modes
            FROM hrms_connector_config c
            JOIN hrms_connector_definition d
              ON d.connector_definition_id = c.connector_definition_id
            WHERE c.tenant_id = $1
            ORDER BY c.created_at DESC
            """,
            tenant_id,
        )
        return [self._serialize_config(r) for r in rows]

    async def get_tenant_config(self, connector_id: UUID, tenant_id: UUID, db) -> dict | None:
        row = await db.fetchrow(
            """
            SELECT c.connector_id, c.tenant_id, c.connector_definition_id,
                   c.display_name, c.integration_mode, c.last_pulled_at,
                   c.pull_schedule, c.status, c.field_mapping,
                   c.created_at, c.updated_at,
                   d.connector_key, d.display_name AS definition_name,
                   d.auth_method, d.supported_modes
            FROM hrms_connector_config c
            JOIN hrms_connector_definition d
              ON d.connector_definition_id = c.connector_definition_id
            WHERE c.connector_id = $1
              AND c.tenant_id = $2
            """,
            connector_id,
            tenant_id,
        )
        return self._serialize_config(row) if row else None

    async def create_tenant_config(
        self,
        tenant_id: UUID,
        connector_definition_id: UUID,
        display_name: str,
        integration_mode: str,
        credentials: dict,
        kek_arn: str,
        kms,
        db,
        pull_schedule: str | None = None,
        field_mapping: dict | None = None,
        created_by: UUID | None = None,
    ) -> UUID:
        # Encrypt credentials with KMS before any DB write — never store plaintext
        creds_bytes   = json.dumps(credentials).encode()
        enc_credentials = kms.encrypt(creds_bytes, kek_arn)

        connector_id = await db.fetchval(
            """
            INSERT INTO hrms_connector_config
              (tenant_id, connector_definition_id, display_name,
               connector_type, integration_mode, enc_credentials, kek_arn,
               pull_schedule, field_mapping, created_by)
            VALUES ($1, $2, $3,
                    (SELECT connector_key FROM hrms_connector_definition
                     WHERE connector_definition_id = $2),
                    $4, $5, $6, $7, $8, $9)
            RETURNING connector_id
            """,
            tenant_id,
            connector_definition_id,
            display_name,
            integration_mode,
            enc_credentials,
            kek_arn,
            pull_schedule,
            json.dumps(field_mapping or {}),
            created_by,
        )
        log.info("Created HRMS connector config connector_id=%s tenant=%s", connector_id, tenant_id)
        return connector_id

    async def update_field_mapping(
        self,
        connector_id: UUID,
        tenant_id: UUID,
        field_mapping: dict,
        db,
    ) -> None:
        await db.execute(
            """
            UPDATE hrms_connector_config
            SET field_mapping = $1, updated_at = NOW()
            WHERE connector_id = $2
              AND tenant_id = $3
            """,
            json.dumps(field_mapping),
            connector_id,
            tenant_id,
        )

    async def set_status(
        self,
        connector_id: UUID,
        tenant_id: UUID,
        status: str,
        db,
    ) -> None:
        if status not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {_VALID_STATUSES}")
        await db.execute(
            """
            UPDATE hrms_connector_config
            SET status = $1, updated_at = NOW()
            WHERE connector_id = $2
              AND tenant_id = $3
            """,
            status,
            connector_id,
            tenant_id,
        )

    async def update_last_pulled(
        self,
        connector_id: UUID,
        tenant_id: UUID,
        cursor: str,
        db,
    ) -> None:
        await db.execute(
            """
            UPDATE hrms_connector_config
            SET last_pulled_at = NOW(), pull_schedule = $1, updated_at = NOW()
            WHERE connector_id = $2
              AND tenant_id = $3
            """,
            cursor,
            connector_id,
            tenant_id,
        )

    # ── Credential decryption ─────────────────────────────────────────────────

    async def decrypt_credentials(
        self,
        enc_credentials: bytes,
        kek_arn: str,
        kms,
    ) -> dict:
        decrypted = kms.decrypt(enc_credentials, kek_arn)
        return json.loads(decrypted)

    # ── Sync log ──────────────────────────────────────────────────────────────

    async def log_sync_start(
        self,
        connector_id: UUID,
        tenant_id: UUID,
        sync_mode: str,
        db,
        cursor_before: str | None = None,
        temporal_run_id: str | None = None,
    ) -> UUID:
        sync_id = await db.fetchval(
            """
            INSERT INTO hrms_sync_log
              (connector_id, tenant_id, sync_mode, cursor_before, temporal_run_id, status)
            VALUES ($1, $2, $3, $4, $5, 'RUNNING')
            RETURNING sync_id
            """,
            connector_id,
            tenant_id,
            sync_mode,
            cursor_before,
            temporal_run_id,
        )
        return sync_id

    async def log_sync_complete(
        self,
        sync_id: UUID,
        status: str,
        docs_pushed: int,
        docs_failed: int,
        db,
        cursor_after: str | None = None,
        error_message: str | None = None,
    ) -> None:
        await db.execute(
            """
            UPDATE hrms_sync_log
            SET status = $1, docs_pushed = $2, docs_failed = $3,
                cursor_after = $4, error_message = $5, completed_at = NOW()
            WHERE sync_id = $6
            """,
            status,
            docs_pushed,
            docs_failed,
            cursor_after,
            error_message,
            sync_id,
        )

    # ── Serializers ───────────────────────────────────────────────────────────

    @staticmethod
    def _serialize_definition(r) -> dict:
        schema = r["canonical_field_schema"]
        if isinstance(schema, str):
            schema = json.loads(schema)
        return {
            "connector_definition_id": str(r["connector_definition_id"]),
            "connector_key":           r["connector_key"],
            "display_name":            r["display_name"],
            "auth_method":             r["auth_method"],
            "supported_modes":         list(r["supported_modes"]),
            "canonical_field_schema":  schema or {},
            "docs_url":                r["docs_url"],
            "is_active":               bool(r["is_active"]),
        }

    @staticmethod
    def _serialize_config(r) -> dict:
        fm = r["field_mapping"]
        if isinstance(fm, str):
            fm = json.loads(fm)
        return {
            "connector_id":             str(r["connector_id"]),
            "tenant_id":                str(r["tenant_id"]),
            "connector_definition_id":  str(r["connector_definition_id"]),
            "display_name":             r["display_name"],
            "integration_mode":         r["integration_mode"],
            "last_pulled_at":           r["last_pulled_at"].isoformat() if r["last_pulled_at"] else None,
            "pull_schedule":            r["pull_schedule"],
            "status":                   r["status"],
            "field_mapping":            fm or {},
            "connector_key":            r["connector_key"],
            "definition_name":          r["definition_name"],
            "auth_method":              r["auth_method"],
            "supported_modes":          list(r["supported_modes"]),
        }
