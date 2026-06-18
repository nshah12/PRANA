"""
Per-session conversation history backed by Redis.

Key:  ask:hist:{employee_user_id}:{session_id}
TTL:  30 minutes from last write (sliding)
Cap:  last 20 messages (10 turns) — oldest pair dropped when exceeded

Privacy: messages stored are already post-processed (raw ₹ / PAN never reach here).
"""

import json
import logging
from uuid import UUID

log = logging.getLogger(__name__)

_KEY_PREFIX = "ask:hist"
_TTL_SECONDS = 1800   # 30 min sliding window
_MAX_MESSAGES = 20    # 10 user+assistant pairs


class ConversationStore:
    def __init__(self, redis):
        self._r = redis

    def _key(self, employee_user_id: UUID, session_id: str) -> str:
        return f"{_KEY_PREFIX}:{employee_user_id}:{session_id}"

    async def get_history(self, employee_user_id: UUID, session_id: str) -> list[dict]:
        try:
            raw = await self._r.get(self._key(employee_user_id, session_id))
            if not raw:
                return []
            return json.loads(raw)
        except Exception as e:
            log.warning("conversation_store get failed: %s", e)
            return []

    async def append(
        self,
        employee_user_id: UUID,
        session_id: str,
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        key = self._key(employee_user_id, session_id)
        try:
            history = await self.get_history(employee_user_id, session_id)
            history.append({"role": "user", "content": user_msg})
            history.append({"role": "assistant", "content": assistant_msg})
            # Keep only the last _MAX_MESSAGES entries (trim from front)
            if len(history) > _MAX_MESSAGES:
                history = history[-_MAX_MESSAGES:]
            await self._r.set(key, json.dumps(history), ex=_TTL_SECONDS)
        except Exception as e:
            log.warning("conversation_store append failed: %s", e)
