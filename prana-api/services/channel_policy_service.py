"""
ChannelPolicyService — resolves which channel(s) a NotificationTemplate goes
out on. Tenant override → platform-default fallback, same resolution order
as ConfigService, expressed against notification_channel_policy instead of
platform_config/tenant_config because a plain scalar column can't hold an
ordered channel list. See prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §3.

This is the ONE place channel decisions are made — CommunicationHubConsumer
calls it, nothing else names a channel.
"""
from typing import Optional

import asyncpg


class ChannelPolicyService:
    def __init__(self, db: asyncpg.Connection) -> None:
        self._db = db

    async def resolve(self, template_id: str, tenant_id: Optional[str]) -> list[str]:
        if tenant_id:
            row = await self._db.fetchrow(
                "SELECT channels FROM notification_channel_policy "
                "WHERE template_id = $1 AND tenant_id = $2",
                template_id, tenant_id,
            )
            if row:
                return list(row["channels"])

        row = await self._db.fetchrow(
            "SELECT channels FROM notification_channel_policy "
            "WHERE template_id = $1 AND tenant_id IS NULL",
            template_id,
        )
        return list(row["channels"]) if row else []
