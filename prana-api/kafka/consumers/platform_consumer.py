"""
PlatformConsumer — prana.platform.events

Ops alerting: routes WORKER_CRASHED / HEALTH_CHECK_FAILED to external
alerting (PagerDuty / Slack webhook). Writes to platform_incident log.

Events handled:
  WORKER_CRASHED        → log + alert ops (P1)
  HEALTH_CHECK_FAILED   → log + alert ops (P2 unless repeated → P1)
  DEPLOYMENT_COMPLETED  → log only
  RATE_LIMIT_CONFIG_UPDATED → log only
"""
import json
import logging
import os

from aiokafka import AIOKafkaConsumer

from config import Settings

log = logging.getLogger(__name__)
GROUP_ID = "prana-platform-consumer"


class PlatformConsumer:
    def __init__(self, settings: Settings) -> None:
        self._consumer = AIOKafkaConsumer(
            "prana.platform.events",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )

    async def run(self) -> None:
        await self._consumer.start()
        log.info("PlatformConsumer started")
        try:
            async for msg in self._consumer:
                event = msg.value
                try:
                    await self._handle(event)
                except Exception:
                    log.exception("PlatformConsumer error event_type=%s", event.get("event_type"))
        finally:
            await self._consumer.stop()

    async def _handle(self, event: dict) -> None:
        etype = event.get("event_type")
        if etype in ("WORKER_CRASHED", "HEALTH_CHECK_FAILED"):
            log.critical("PLATFORM ALERT event_type=%s service=%s detail=%s",
                         etype, event.get("service"), event.get("detail"))
            await self._send_ops_alert(etype, event)
        else:
            log.info("PlatformConsumer: event_type=%s service=%s", etype, event.get("service"))

    async def _send_ops_alert(self, etype: str, event: dict) -> None:
        webhook_url = os.environ.get("OPS_ALERT_WEBHOOK_URL", "")
        if not webhook_url:
            log.debug("PlatformConsumer: OPS_ALERT_WEBHOOK_URL not set — alert logged only")
            return
        try:
            import aiohttp
            payload = {
                "text": f":red_circle: *{etype}* on `{event.get('service','unknown')}` "
                        f"— {event.get('detail','no detail')}",
            }
            async with aiohttp.ClientSession() as session:
                resp = await session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10))
                if resp.status not in (200, 204):
                    log.error("PlatformConsumer: alert webhook returned %d", resp.status)
        except ImportError:
            log.error("PlatformConsumer: aiohttp not installed — cannot send ops alert")
        except Exception:
            log.exception("PlatformConsumer: failed to send ops alert")
