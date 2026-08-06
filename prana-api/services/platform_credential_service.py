"""
PlatformCredentialService — PA-only credential management for paid external
services that aren't a Communication Hub channel (see
services/communication_settings_service.py for email/sms/whatsapp/ivr
vendors, which keep their own dedicated methods since they're tied to
CHANNEL_VENDORS/vendor-chain concepts this doesn't have).

Same table (platform_vendor_credential), same KMS-encryption-at-rest model
(platform auth CMK, same as enc_mobile/totp_secret_enc), same
Immudb-audited tenant_event() pattern — just a different, smaller field map
for services with no "vendor chain" (a channel can fail over between
vendors; Qdrant is just Qdrant).

Explicitly NOT covering AWS-family services (S3, KMS, Textract, SES) —
those default to IAM roles in production (see config.py's aws_access_key_id
comment: "Empty = use IAM role in production"); adding a web form to type
static AWS keys would undercut that already-adopted best practice, not
close a gap. Revisit only if that default is deliberately overridden.

prana-ask (separate deployed service, own config.py, no shared packages
with prana-api per prana-ask/CLAUDE.md) must independently read a
DB-stored qdrant credential and decrypt it via its own boto3 KMS call if
it wants to prefer it over its QDRANT_API_KEY env var — not wired yet,
flagged as follow-up, not claimed done here.
"""
from typing import Optional

import asyncpg

from config import Settings

PLATFORM_CREDENTIAL_FIELDS = {
    "qdrant": ["qdrant_url", "qdrant_api_key"],
}


class PlatformCredentialService:
    def __init__(self, db: asyncpg.Connection) -> None:
        self._db = db

    async def get_status(self, settings: Settings) -> dict:
        db_rows = await self._db.fetch("SELECT vendor, field_name FROM platform_vendor_credential")
        db_configured: dict[str, set[str]] = {}
        for r in db_rows:
            db_configured.setdefault(r["vendor"], set()).add(r["field_name"])

        env_configured = {
            "qdrant": bool(settings.qdrant_api_key),
        }

        status = {}
        for vendor, env_ok in env_configured.items():
            db_ok = vendor in db_configured
            status[vendor] = {
                "configured": db_ok or env_ok,
                "source": "db" if db_ok else ("env" if env_ok else "none"),
            }
        return status

    async def set_credential(
        self, *, vendor: str, field_name: str, value: str, updated_by: str, kms, kek_arn: str,
    ) -> None:
        if vendor not in PLATFORM_CREDENTIAL_FIELDS:
            raise ValueError(f"UNKNOWN_VENDOR: {vendor}")
        if field_name not in PLATFORM_CREDENTIAL_FIELDS[vendor]:
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
            "event_type": "PLATFORM_CREDENTIAL_ROTATED",
            "tenant_id": None,
            "vendor": vendor,
            "field_name": field_name,
            "actor_id": updated_by,
        })
