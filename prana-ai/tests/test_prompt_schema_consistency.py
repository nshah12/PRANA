"""
Regression guard: every extraction prompt's RETURN FORMAT keys must be a
subset of its paired Pydantic schema's declared fields.

Root cause this catches: extraction_service.py validates the LLM's raw JSON
response through `schema_cls.model_validate(parsed)`. Pydantic's default
`extra='ignore'` behavior means any key the LLM returns that the schema
doesn't declare is silently dropped — no error, no warning. If a prompt asks
the LLM for a field name the schema doesn't have (e.g. increment_letter.py's
prompt once asked for "ctc_old"/"ctc_new" while IncrementLetterExtraction
declared "ctc_before"/"ctc_after"), that data is captured by the LLM and then
thrown away at validation time — the field permanently reads as
null/confidence 0.0 no matter what the source document says, and any
downstream logic reading that field (e.g. benchmark_service.py's increment
growth-percent calculation) silently never fires.
"""
import re

from extraction.extraction_service import _REGISTRY


def _return_format_keys(prompt_module) -> set[str]:
    """Extract the JSON key names from a prompt's RETURN FORMAT template."""
    built = prompt_module.build_user_prompt("dummy redacted document text")
    return_format_start = built.index("RETURN FORMAT")
    template = built[return_format_start:]
    keys = set(re.findall(r'"(\w+)":\s*\{"value"', template))
    return keys


def test_every_prompt_return_format_matches_its_schema_fields():
    mismatches = {}
    for doc_type, (prompt_module, schema_cls) in _REGISTRY.items():
        prompt_keys = _return_format_keys(prompt_module)
        schema_keys = set(schema_cls.model_fields.keys())
        extra_in_prompt = prompt_keys - schema_keys
        if extra_in_prompt:
            mismatches[doc_type.value] = extra_in_prompt

    assert not mismatches, (
        "These doc types' prompts ask the LLM for field names their schema "
        "doesn't declare — Pydantic silently drops that data at validation "
        f"time (extra='ignore'), so it's never captured: {mismatches}"
    )
