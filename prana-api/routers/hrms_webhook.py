"""
HRMS Webhook receiver — POST /v1/hrms/webhook/{connector_id}

Called by Darwinbox / Keka when an employee record changes.
No auth token required — validated by HMAC-SHA256 signature instead.

Contract:
  1. Read raw body (must compute HMAC before JSON parsing)
  2. Validate X-PRANA-Webhook-Sig: HMAC-SHA256(body, webhook_secret)
  3. Load connector config to get tenant_id + adapter class
  4. adapter.handle_webhook(payload) → list of employee events
  5. Publish each event via kafka.employee_event() domain helper
  6. Return 200 {"received": true}

HTTP handler rule: validate → load → dispatch → 202. No DB side-effects here.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status

from connectors.base import strip_salary_fields
from services.hrms_sync_service import HRMSSyncService

log    = logging.getLogger(__name__)
router = APIRouter()


def _get_svc() -> HRMSSyncService:
    return HRMSSyncService()


def _verify_hmac(body: bytes, secret: str, provided_sig: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided_sig)


@router.post("/{connector_id}", status_code=status.HTTP_200_OK)
async def receive_webhook(
    connector_id: UUID,
    request: Request,
    x_prana_webhook_sig: Optional[str] = Header(default=None, alias="X-PRANA-Webhook-Sig"),
    x_prana_connector_key: Optional[str] = Header(default=None, alias="X-PRANA-Connector-Key"),
):
    # Read raw body before JSON parsing (signature is over raw bytes)
    body = await request.body()

    if not x_prana_webhook_sig:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "MISSING_SIGNATURE", "message": "X-PRANA-Webhook-Sig header required"},
        )

    db    = request.app.state.db_pool
    kafka = request.app.state.kafka_producer
    svc   = _get_svc()

    # Load config via service (tenant_id from DB, not from caller)
    async with db.acquire() as conn:
        config = await _load_config_with_secret(connector_id, conn)

    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "CONNECTOR_NOT_FOUND", "message": "Unknown connector"},
        )

    webhook_secret = config.get("webhook_secret") or ""
    if not _verify_hmac(body, webhook_secret, x_prana_webhook_sig):
        log.warning("HRMS webhook: bad signature connector_id=%s", connector_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "INVALID_SIGNATURE", "message": "Signature mismatch"},
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail={"error": "INVALID_JSON"})

    # Delegate to adapter to normalise the payload
    try:
        import boto3
        kms     = boto3.client("kms", region_name="ap-south-1")
        adapter = svc.build_adapter(config=config, kms=kms)
        events  = adapter.handle_webhook(payload)
    except Exception:
        log.exception("HRMS webhook: adapter failed connector_id=%s", connector_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail={"error": "ADAPTER_ERROR"})

    # Publish each employee event — salary stripped by adapter + once more here
    tenant_id = config["tenant_id"]
    for evt in events:
        clean = strip_salary_fields(evt)
        try:
            await kafka.employee_event({
                "event_type":    "HRMS_EMPLOYEE_SYNCED",
                "tenant_id":     str(tenant_id),
                "connector_id":  str(connector_id),
                "employee_data": clean,
                "source":        "WEBHOOK",
            })
        except Exception:
            log.exception("HRMS webhook: failed to publish event connector_id=%s", connector_id)

    log.info("HRMS webhook: received connector_id=%s events=%d", connector_id, len(events))
    return {"received": True, "events_queued": len(events)}


async def _load_config_with_secret(connector_id: UUID, conn) -> Optional[dict]:
    row = await conn.fetchrow(
        """
        SELECT c.connector_id, c.tenant_id, c.enc_credentials, c.kek_arn,
               c.field_mapping, c.status, c.webhook_secret,
               d.connector_key
        FROM   hrms_connector_config c
        JOIN   hrms_connector_definition d
               ON d.connector_definition_id = c.connector_definition_id
        WHERE  c.connector_id = $1
          AND  c.status       = 'ACTIVE'
        """,
        connector_id,
    )
    if not row:
        return None
    import json as _json
    fm = row["field_mapping"]
    return {
        "connector_id":   str(row["connector_id"]),
        "tenant_id":      row["tenant_id"],
        "connector_key":  row["connector_key"],
        "status":         row["status"],
        "enc_credentials": row["enc_credentials"],
        "kek_arn":        row["kek_arn"],
        "field_mapping":  _json.loads(fm) if isinstance(fm, str) else (fm or {}),
        "webhook_secret": row["webhook_secret"],
    }
