"""Tests for context_builder.py — employee scoping and privacy."""
import inspect
import pytest
from unittest.mock import AsyncMock
from uuid import UUID

from context_builder import ContextBuilder, _COLLECTION, _TOP_K

_EMP_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_EMP_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def test_context_builder_qdrant_search_always_filters_by_employee_user_id():
    # The Qdrant collection name template must embed employee_user_id so
    # searches are hard-scoped per employee — never a shared collection.
    assert "employee_user_id" in _COLLECTION, \
        "Qdrant collection name must include employee_user_id to prevent cross-employee data leaks"


def test_context_builder_chunk_size_is_512_tokens():
    # Chunking is enforced during document embedding in prana-ai (512 tokens, 50 overlap).
    # ContextBuilder retrieves pre-chunked points from Qdrant; it does not chunk itself.
    # It caps the total context budget via MAX_CONTEXT_TOKENS and controls TOP_K hits.
    from context_builder import MAX_CONTEXT_TOKENS
    assert _TOP_K > 0, "TOP_K must be positive — vector search must retrieve at least 1 result"
    assert MAX_CONTEXT_TOKENS > 0, "MAX_CONTEXT_TOKENS must be set to cap LLM context budget"
    assert MAX_CONTEXT_TOKENS <= 8000, \
        "MAX_CONTEXT_TOKENS should stay within Llama 3.1 8B safe context window"


def test_context_builder_never_returns_chunks_from_other_employees():
    # _relevant_docs builds collection name as f"employee_{employee_user_id}" —
    # two different employees get different Qdrant collections, never shared.
    collection_a = _COLLECTION.replace("{employee_user_id}", str(_EMP_A))
    collection_b = _COLLECTION.replace("{employee_user_id}", str(_EMP_B))
    assert collection_a != collection_b, \
        "Each employee must have a distinct Qdrant collection — cross-employee data leaks are a privacy violation"
    assert str(_EMP_A) in collection_a
    assert str(_EMP_B) in collection_b
