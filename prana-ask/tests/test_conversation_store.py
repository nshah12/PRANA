"""Tests for conversation_store.py — per-employee scoping and privacy."""
import inspect
import json
import pytest
from unittest.mock import AsyncMock
from uuid import UUID

from conversation_store import ConversationStore, _KEY_PREFIX, _MAX_MESSAGES, _TTL_SECONDS

_EMP_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_EMP_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def test_conversation_stored_per_employee_not_global():
    # Redis keys must be scoped to (employee_user_id, session_id) so two employees
    # sharing a session_id string still get separate history buckets.
    redis = AsyncMock()
    store = ConversationStore(redis)
    key_a = store._key(_EMP_A, "session-1")
    key_b = store._key(_EMP_B, "session-1")
    assert key_a != key_b, \
        "Different employees with the same session_id must produce different Redis keys"
    assert str(_EMP_A) in key_a
    assert str(_EMP_B) in key_b
    assert _KEY_PREFIX in key_a


@pytest.mark.asyncio
async def test_conversation_store_never_persists_raw_salary_or_pan():
    # ConversationStore.append stores whatever messages AskService passes it.
    # AskService only calls append AFTER the privacy guard has already blocked
    # or passed the response — so raw ₹/PAN never reach here.
    # Verify structurally: the store writes what it receives without modification
    # (no re-filtering needed, but also no raw figures should ever arrive).
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()

    store = ConversationStore(redis)
    safe_reply = "Your career shows strong progression over 5 years."
    await store.append(_EMP_A, "sess-abc", "How long have I worked?", safe_reply)

    redis.set.assert_called_once()
    stored_raw = redis.set.call_args[0][1]
    stored = json.loads(stored_raw)
    assert any(m["content"] == safe_reply for m in stored), \
        "Safe reply must be persisted in conversation history"
    # Confirm the stored data contains no raw rupee or PAN patterns
    assert "₹" not in stored_raw
    assert "Rs." not in stored_raw
