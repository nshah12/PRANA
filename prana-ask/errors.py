"""
PRANA Ask — error taxonomy.

Separate from prana-api/errors.py — prana-ask is an independent deployed service.
Cross-service error code discipline: values == names, grouped by domain.
"""
from enum import StrEnum


class AskError(StrEnum):
    # ── AUTH ──────────────────────────────────────────────────────────────────
    UNAUTHORIZED          = "UNAUTHORIZED"

    # ── REQUEST VALIDATION ────────────────────────────────────────────────────
    MISSING_EMPLOYEE_ID   = "MISSING_EMPLOYEE_ID"
    INVALID_EMPLOYEE_ID   = "INVALID_EMPLOYEE_ID"
    EMPTY_QUERY           = "EMPTY_QUERY"
    QUERY_TOO_LONG        = "QUERY_TOO_LONG"

    # ── PRIVACY GUARD ─────────────────────────────────────────────────────────
    PRIVACY_BLOCK         = "PRIVACY_BLOCK"       # output filtered by privacy guard

    # ── INFRASTRUCTURE ────────────────────────────────────────────────────────
    RAG_UNAVAILABLE       = "RAG_UNAVAILABLE"     # Qdrant / LLM unreachable
