"""
CommunicationSettingsService — backs the PA + OA-Admin Communication Settings
screens (prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §8).

Channel policy: per-NotificationTemplate channel set, tenant override with
platform-default fallback (notification_channel_policy table, Phase 1).
Vendor chains: per-channel ordered vendor list, same tenant->platform
resolution (platform_config/tenant_config, Phase 1) — an OA-Admin can only
choose among vendors PA has already enabled platform-wide (§8.2's "ceiling").

Every write publishes an Immudb-audited kafka.tenant_event() (§9) — same
pipeline (TOPIC_AUDIT -> AuditConsumer -> audit_event -> Immudb dual-write)
already used for TENANT_CONFIG_UPDATED/KEK_ROTATED/etc, no new plumbing.

Cache staleness (fixed 2026-07-24, found via a real live run): vendor chains
are the only config here actually read through ConfigService's Redis cache
(email/sms/whatsapp/ivr_service.py's get_list(f"{channel}_vendor_chain", ...)
at dispatch time) — channel policy reads go straight to notification_channel_policy
via ChannelPolicyService, no cache involved, so those need no invalidation.
org_settings.py/chro.py/tenant_service.py/digest_service.py's tenant_config
writes (self_upload_policy, employee_activation_channels, chro_alert_*, digest
config) are read back via direct SQL everywhere else too — never through
ConfigService — so they were never actually stale, despite the superficially
identical "INSERT ... ON CONFLICT" shape. update_vendor_chain() below now
invalidates: invalidate_all() (SCAN-based, clears every tenant's cached copy
of the fallback) for a platform-default edit, invalidate() (single key) for
a tenant-scoped edit.
"""
import json
import logging
from typing import Optional

import asyncpg
import redis.asyncio as redis_lib

from config import Settings
from messages import NotificationTemplate
from services.config_service import ConfigService

log = logging.getLogger(__name__)

VALID_CHANNELS = {"email", "sms", "whatsapp", "portal_bell", "ivr", "push"}
CHANNEL_VENDORS = {
    "email": {"ses", "smtp"},
    "sms": {"aws", "exotel", "msg91"},
    "whatsapp": {"waba"},
    "ivr": {"exotel", "ozonetel"},
}

# PA-editable secret fields per vendor — the auth-relevant secrets only, not
# every tunable (sender_id/template_id/flow_id/api_version/caller_id stay
# env-configured). ses/aws_sns have no entry — IAM role, nothing to edit here.
VENDOR_CREDENTIAL_FIELDS = {
    "smtp":     ["smtp_host", "smtp_user", "smtp_password"],
    "exotel":   ["exotel_sid", "exotel_api_key", "exotel_api_token"],
    "msg91":    ["msg91_auth_key"],
    "waba":     ["whatsapp_waba_token", "whatsapp_waba_phone_number_id"],
    "ozonetel": ["ozonetel_api_key"],
}


class CommunicationSettingsService:
    def __init__(self, db: asyncpg.Connection, redis_client: Optional[redis_lib.Redis] = None) -> None:
        self._db = db
        self._redis = redis_client

    # -----------------------------------------------------------------------
    # Channel policy
    # -----------------------------------------------------------------------

    async def get_channel_policy(self, tenant_id: Optional[str] = None) -> list[dict]:
        platform_rows = await self._db.fetch(
            "SELECT template_id, channels FROM notification_channel_policy WHERE tenant_id IS NULL"
        )
        platform_map = {r["template_id"]: list(r["channels"]) for r in platform_rows}

        tenant_map: dict[str, list[str]] = {}
        if tenant_id:
            tenant_rows = await self._db.fetch(
                "SELECT template_id, channels FROM notification_channel_policy WHERE tenant_id = $1",
                tenant_id,
            )
            tenant_map = {r["template_id"]: list(r["channels"]) for r in tenant_rows}

        items = []
        for member in NotificationTemplate:
            template_id = member.value
            platform_channels = platform_map.get(template_id, [])
            is_override = template_id in tenant_map
            channels = tenant_map[template_id] if is_override else platform_channels
            items.append({
                "template_id": template_id,
                "channels": channels,
                "platform_channels": platform_channels,
                "is_tenant_override": is_override,
            })
        return items

    async def update_channel_policy(
        self, *, template_id: str, channels: list[str], tenant_id: Optional[str], updated_by: str,
    ) -> dict:
        if template_id not in {m.value for m in NotificationTemplate}:
            raise ValueError(f"UNKNOWN_TEMPLATE_ID: {template_id}")
        invalid = set(channels) - VALID_CHANNELS
        if invalid:
            raise ValueError(f"INVALID_CHANNELS: {sorted(invalid)}")
        if not channels:
            raise ValueError("AT_LEAST_ONE_CHANNEL_REQUIRED")

        if tenant_id:
            old_row = await self._db.fetchrow(
                "SELECT channels FROM notification_channel_policy "
                "WHERE template_id = $1 AND tenant_id = $2",
                template_id, tenant_id,
            )
        else:
            old_row = await self._db.fetchrow(
                "SELECT channels FROM notification_channel_policy "
                "WHERE template_id = $1 AND tenant_id IS NULL",
                template_id,
            )
        old_channels = list(old_row["channels"]) if old_row else []

        if tenant_id:
            await self._db.execute(
                """
                INSERT INTO notification_channel_policy (template_id, tenant_id, channels, updated_by)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (template_id, tenant_id) WHERE tenant_id IS NOT NULL
                DO UPDATE SET channels = $3, updated_by = $4, updated_at = NOW()
                """,
                template_id, tenant_id, channels, updated_by,
            )
        else:
            await self._db.execute(
                """
                INSERT INTO notification_channel_policy (template_id, tenant_id, channels, updated_by)
                VALUES ($1, NULL, $2, $3)
                ON CONFLICT (template_id) WHERE tenant_id IS NULL
                DO UPDATE SET channels = $2, updated_by = $3, updated_at = NOW()
                """,
                template_id, channels, updated_by,
            )

        from kafka.producer import get_kafka_producer
        kafka = await get_kafka_producer()
        await kafka.tenant_event({
            "event_type": "COMM_CHANNEL_POLICY_UPDATED",
            "tenant_id": tenant_id,
            "template_id": template_id,
            "old_channels": old_channels,
            "new_channels": channels,
            "actor_id": updated_by,
        })

        return {"template_id": template_id, "channels": channels, "tenant_id": tenant_id}

    # -----------------------------------------------------------------------
    # Vendor chains
    # -----------------------------------------------------------------------

    async def _resolve_chain(self, key: str, tenant_id: Optional[str]) -> list[str]:
        value = None
        if tenant_id:
            value = await self._db.fetchval(
                "SELECT config_value FROM tenant_config WHERE tenant_id = $1 AND config_key = $2",
                tenant_id, key,
            )
        if value is None:
            value = await self._db.fetchval(
                "SELECT config_value FROM platform_config WHERE config_key = $1", key,
            )
        return json.loads(value) if value else []

    async def get_vendor_chains(self, tenant_id: Optional[str] = None) -> dict:
        chains = {}
        for channel in CHANNEL_VENDORS:
            key = f"{channel}_vendor_chain"
            chains[channel] = {
                "chain": await self._resolve_chain(key, tenant_id),
                "available_vendors": sorted(CHANNEL_VENDORS[channel]),
            }
        return chains

    async def update_vendor_chain(
        self, *, channel: str, vendors: list[str], tenant_id: Optional[str], updated_by: str,
    ) -> dict:
        if channel not in CHANNEL_VENDORS:
            raise ValueError(f"UNKNOWN_CHANNEL: {channel}")
        invalid = set(vendors) - CHANNEL_VENDORS[channel]
        if invalid:
            raise ValueError(f"INVALID_VENDORS: {sorted(invalid)}")
        if not vendors:
            raise ValueError("AT_LEAST_ONE_VENDOR_REQUIRED")

        key = f"{channel}_vendor_chain"
        if tenant_id:
            # An OA-Admin can only choose among vendors PA already enabled
            # platform-wide — §8.2's "ceiling".
            platform_chain = await self._resolve_chain(key, None)
            not_enabled = set(vendors) - set(platform_chain)
            if not_enabled:
                raise ValueError(f"VENDOR_NOT_ENABLED_BY_PLATFORM: {sorted(not_enabled)}")

            await self._db.execute(
                """
                INSERT INTO tenant_config (tenant_id, config_key, config_value, updated_by)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (tenant_id, config_key)
                DO UPDATE SET config_value = $3, updated_by = $4, updated_at = NOW()
                """,
                tenant_id, key, json.dumps(vendors), updated_by,
            )
        else:
            # value_type is NOT NULL with no default — must be supplied even though
            # ON CONFLICT always hits in practice (these 4 keys are always pre-seeded
            # by schema.sql), because Postgres/Yugabyte validates the candidate row's
            # constraints before checking for a conflict, not just on actual insert.
            await self._db.execute(
                """
                INSERT INTO platform_config (config_key, config_value, value_type)
                VALUES ($1, $2, 'STRING')
                ON CONFLICT (config_key)
                DO UPDATE SET config_value = $2, updated_by = $3, updated_at = NOW()
                """,
                key, json.dumps(vendors), updated_by,
            )

        if self._redis is not None:
            config = ConfigService(self._db, self._redis)
            if tenant_id:
                await config.invalidate(key, tenant_id)
            else:
                # Platform-default edit: every tenant without its own override
                # cached the fallback value under its OWN cfg:{tenant_id}:{key}
                # entry — a single invalidate() would miss all of them.
                await config.invalidate_all(key)

        from kafka.producer import get_kafka_producer
        kafka = await get_kafka_producer()
        await kafka.tenant_event({
            "event_type": "COMM_VENDOR_CHAIN_UPDATED",
            "tenant_id": tenant_id,
            "channel": channel,
            "new_chain": vendors,
            "actor_id": updated_by,
        })

        return {"channel": channel, "chain": vendors, "tenant_id": tenant_id}

    # -----------------------------------------------------------------------
    # Vendor credentials — PA only. Reads never expose secret values, only
    # configuration status. Writes are KMS-encrypted (platform auth CMK, same
    # as enc_mobile/totp_secret_enc) and Immudb-audited without the secret.
    # -----------------------------------------------------------------------

    async def get_vendor_credential_status(self, settings: Settings) -> dict:
        db_rows = await self._db.fetch("SELECT vendor, field_name FROM platform_vendor_credential")
        db_configured: dict[str, set[str]] = {}
        for r in db_rows:
            db_configured.setdefault(r["vendor"], set()).add(r["field_name"])

        env_configured = {
            "smtp":     bool(settings.smtp_host),
            "exotel":   bool(settings.exotel_sid and settings.exotel_api_key),
            "msg91":    bool(settings.msg91_auth_key),
            "waba":     bool(settings.whatsapp_waba_token and settings.whatsapp_waba_phone_number_id),
            "ozonetel": bool(settings.ozonetel_api_key),
        }

        status = {
            # AWS SES/SNS commonly run under an IAM role in production (no
            # explicit key/secret needed) — cannot be verified from Settings
            # alone, so always reported as configured.
            "ses":     {"configured": True, "source": "env"},
            "aws_sns": {"configured": True, "source": "env"},
        }
        for vendor, env_ok in env_configured.items():
            db_ok = vendor in db_configured
            status[vendor] = {
                "configured": db_ok or env_ok,
                "source": "db" if db_ok else ("env" if env_ok else "none"),
            }
        return status

    async def set_vendor_credential(
        self, *, vendor: str, field_name: str, value: str, updated_by: str, kms, kek_arn: str,
    ) -> None:
        if vendor not in VENDOR_CREDENTIAL_FIELDS:
            raise ValueError(f"UNKNOWN_VENDOR: {vendor}")
        if field_name not in VENDOR_CREDENTIAL_FIELDS[vendor]:
            raise ValueError(f"UNKNOWN_FIELD: {field_name} for vendor {vendor}")

        enc_value = kms.encrypt_value(value, kek_arn)
        await self._db.execute(
            """
            INSERT INTO platform_vendor_credential (vendor, field_name, enc_value, updated_by)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (vendor, field_name)
            DO UPDATE SET enc_value = $3, updated_by = $4, updated_at = NOW()
            """,
            vendor, field_name, enc_value, updated_by,
        )

        from kafka.producer import get_kafka_producer
        kafka = await get_kafka_producer()
        await kafka.tenant_event({
            "event_type": "COMM_VENDOR_CREDENTIAL_ROTATED",
            "tenant_id": None,
            "vendor": vendor,
            "field_name": field_name,
            "actor_id": updated_by,
        })

    async def get_effective_settings(self, base_settings: Settings, kms, kek_arn: str) -> Settings:
        """Returns a copy of base_settings with any DB-stored (KMS-decrypted)
        vendor credentials overlaid — the actual dispatch path channel
        consumers use, so editing a credential via the PA screen genuinely
        changes what the next send uses, not just what the screen displays."""
        rows = await self._db.fetch("SELECT field_name, enc_value FROM platform_vendor_credential")
        if not rows:
            return base_settings
        overrides = {}
        for r in rows:
            try:
                overrides[r["field_name"]] = kms.decrypt_value(r["enc_value"], kek_arn)
            except Exception:
                log.exception("get_effective_settings: failed to decrypt field_name=%s — using env fallback", r["field_name"])
        return base_settings.model_copy(update=overrides) if overrides else base_settings
