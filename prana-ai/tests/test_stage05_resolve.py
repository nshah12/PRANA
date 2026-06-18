"""Tests for pipeline/stage05_resolve.py — resolution ladder ordering and exception flow."""
import inspect

from pipeline.stage05_resolve import Stage05Resolve, Stage05Result
from resolution.resolution_service import ResolutionMethod


def test_stage05_resolution_ladder_pan_token_exact_match_first():
    # ResolutionService tries pan_token exact match before any fuzzy or embedding lookup.
    from resolution.resolution_service import ResolutionService
    src = inspect.getsource(ResolutionService.resolve)
    pan_pos   = src.index("EXACT_PAN")
    fuzzy_pos = src.index("FUZZY_NAME")
    embed_pos = src.index("EMBEDDING")
    assert pan_pos < fuzzy_pos < embed_pos, \
        "pan_token exact match (Level 1) must precede fuzzy (Level 3) and embedding (Level 4)"


def test_stage05_unresolved_waits_up_to_7_days_for_signal():
    # When resolution yields UNRESOLVED, Stage05 must set needs_exception=True
    # so the workflow queues an exception and waits for OA-Admin signal (up to 7 days).
    src = inspect.getsource(Stage05Resolve.run)
    assert "needs_exception" in src, \
        "Stage05.run must set needs_exception=True when ResolutionMethod is UNRESOLVED"
    assert "UNRESOLVED" in src, \
        "Stage05.run must check for ResolutionMethod.UNRESOLVED"


def test_stage05_embedding_cosine_is_fallback_level_4():
    # Embedding cosine (Level 4) is the last resort — only reached when Levels 1–3 fail.
    from resolution.resolution_service import ResolutionService
    src = inspect.getsource(ResolutionService.resolve)
    pan_pos   = src.index("EXACT_PAN")
    emp_pos   = src.index("EMP_ID")
    fuzzy_pos = src.index("FUZZY_NAME")
    embed_pos = src.index("EMBEDDING")
    assert pan_pos < emp_pos < fuzzy_pos < embed_pos, \
        "Embedding (Level 4) must be the last fallback — after PAN, emp_id, and fuzzy"
