"""
Shared notification_log INSERT — extracted from NotificationService so the
Communication Hub's per-channel consumers (EmailConsumer, SMSConsumer,
WhatsAppConsumer, IVRConsumer) can record delivery status without pulling in
NotificationService's inline channel-dispatch logic, which they no longer
call (each now dispatches via its own {Channel}Service directly). See
prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §7 step 4.
"""
import json
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg


async def write_notification_log(
    db: asyncpg.Connection,
    *,
    tenant_id: Optional[str],
    event_type: str,
    recipient_id: str,
    recipient_type: str,
    channel: str,
    template_id: str,
    template_data: dict[str, Any],
    status: str,
    recipient_email: Optional[str] = None,
    recipient_phone: Optional[str] = None,
    source_id: Optional[str] = None,
    source_table: Optional[str] = None,
    provider_ref: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    sent_at = datetime.now(timezone.utc) if status == "SENT" else None
    failed_at = datetime.now(timezone.utc) if status == "FAILED" else None

    await db.execute(
        """
        INSERT INTO notification_log
          (tenant_id, event_type, source_id, source_table,
           recipient_id, recipient_type, recipient_email, recipient_phone,
           channel, template_id, template_data,
           status, provider_ref, sent_at, failed_at, error_message)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
        """,
        tenant_id, event_type, source_id, source_table,
        recipient_id, recipient_type, recipient_email, recipient_phone,
        channel, template_id, json.dumps(template_data),
        status, provider_ref, sent_at, failed_at, error_message,
    )
