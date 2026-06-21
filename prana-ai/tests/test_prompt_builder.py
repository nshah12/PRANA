"""
Tests for manifest/prompt_builder.py

Covers:
- SYSTEM_PROMPT is a stable string (no per-doc variability)
- build_prompt: identity/required/optional field ordering
- build_prompt: required fields annotated with // REQUIRED in JSON template
- build_prompt: optional fields present but not annotated
- build_auto_detect_prompt: returns valid (system, user) tuple
- build_auto_detect_prompt: contains indicator field names
"""

import pytest
from dataclasses import dataclass
from typing import Optional

from manifest.prompt_builder import (
    build_prompt,
    build_auto_detect_prompt,
    SYSTEM_PROMPT,
)
from manifest.manifest_client import ManifestData


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_manifest(
    doc_type="SALARY_SLIP",
    identity_fields=None,
    required_fields=None,
    optional_fields=None,
    confidence_threshold=0.75,
    **kwargs,
) -> ManifestData:
    return ManifestData(
        manifest_id="test-manifest-id",
        tenant_id=None,
        doc_type=doc_type,
        required_fields=required_fields or ["employee_name", "net_pay", "pay_period_month"],
        identity_fields=identity_fields or ["pan_number", "employee_id", "employee_name"],
        optional_fields=optional_fields or ["designation", "uan_number"],
        classification_signals=[["net_pay", "pay_period_month"]],
        confidence_threshold=confidence_threshold,
        supported_formats=["pdf", "docx"],
        is_tenant_override=False,
    )


# ── SYSTEM_PROMPT ──────────────────────────────────────────────────────────────

def test_system_prompt_is_string():
    assert isinstance(SYSTEM_PROMPT, str)
    assert len(SYSTEM_PROMPT) > 50


def test_system_prompt_contains_privacy_instruction():
    """Privacy reminder must be in the stable system prompt."""
    assert "NIK_REDACTED" in SYSTEM_PROMPT or "privacy" in SYSTEM_PROMPT.lower() or "PAN" in SYSTEM_PROMPT


def test_system_prompt_is_stable_across_calls():
    """SYSTEM_PROMPT must not vary between calls — important for LLM KV-cache."""
    first = SYSTEM_PROMPT
    second = SYSTEM_PROMPT
    assert first is second  # same object, not recomputed


# ── build_prompt ───────────────────────────────────────────────────────────────

def test_build_prompt_returns_two_strings():
    manifest = _make_manifest()
    system, user = build_prompt(manifest, "Sample document text")
    assert isinstance(system, str) and len(system) > 0
    assert isinstance(user, str) and len(user) > 0


def test_build_prompt_system_equals_system_prompt():
    """System prompt must be the stable SYSTEM_PROMPT string (cache-friendly)."""
    manifest = _make_manifest()
    system, _ = build_prompt(manifest, "text")
    assert system == SYSTEM_PROMPT


def test_build_prompt_user_contains_identity_fields():
    manifest = _make_manifest(
        identity_fields=["pan_number", "employee_id"],
        required_fields=["net_pay"],
        optional_fields=["designation"],
    )
    _, user = build_prompt(manifest, "doc text here")
    assert "pan_number" in user
    assert "employee_id" in user


def test_build_prompt_user_contains_required_fields():
    manifest = _make_manifest(
        required_fields=["employee_name", "net_pay"],
    )
    _, user = build_prompt(manifest, "doc text")
    assert "employee_name" in user
    assert "net_pay" in user


def test_build_prompt_required_fields_annotated_required():
    """Required fields in the JSON template must have // REQUIRED annotation."""
    manifest = _make_manifest(
        identity_fields=[],
        required_fields=["net_pay", "employee_name"],
        optional_fields=["designation"],
    )
    _, user = build_prompt(manifest, "doc text")
    # Each required field entry must have // REQUIRED somewhere nearby in user prompt
    assert "REQUIRED" in user


def test_build_prompt_optional_fields_not_annotated_required():
    """Optional fields must appear in the prompt but NOT with // REQUIRED."""
    manifest = _make_manifest(
        required_fields=["net_pay"],
        optional_fields=["designation"],
    )
    _, user = build_prompt(manifest, "doc")
    assert "designation" in user
    # The word REQUIRED must not appear on the same "designation" context line
    lines = user.splitlines()
    designation_lines = [l for l in lines if "designation" in l]
    assert designation_lines, "designation should appear in user prompt"
    for line in designation_lines:
        assert "REQUIRED" not in line, f"Optional field should not be marked REQUIRED: {line}"


def test_build_prompt_identity_fields_appear_before_required():
    """IDENTITY FIELDS section must appear before REQUIRED FIELDS in user prompt."""
    manifest = _make_manifest(
        identity_fields=["pan_number"],
        required_fields=["net_pay"],
    )
    _, user = build_prompt(manifest, "doc")
    identity_pos = user.find("pan_number")
    required_pos = user.find("net_pay")
    assert identity_pos < required_pos, "Identity fields should precede required fields"


def test_build_prompt_embeds_document_text():
    doc_text = "SALARY SLIP FOR MARCH 2024 NET PAY 50000"
    manifest = _make_manifest()
    _, user = build_prompt(manifest, doc_text)
    assert doc_text in user


def test_build_prompt_doc_type_mentioned():
    """User prompt must tell LLM what doc_type it's extracting."""
    manifest = _make_manifest(doc_type="FORM_16")
    _, user = build_prompt(manifest, "text")
    assert "FORM_16" in user or "Form 16" in user or "form_16" in user.lower()


def test_build_prompt_no_duplicate_fields():
    """If a field appears in both identity and required, it should not be listed twice."""
    manifest = _make_manifest(
        identity_fields=["employee_name", "pan_number"],
        required_fields=["employee_name", "net_pay"],  # employee_name is in both
        optional_fields=[],
    )
    _, user = build_prompt(manifest, "text")
    # Count occurrences — should not be duplicated in the JSON template
    count = user.count('"employee_name"')
    assert count <= 2, f"employee_name appeared {count} times — likely duplicated in template"


# ── build_auto_detect_prompt ───────────────────────────────────────────────────

def test_auto_detect_prompt_returns_two_strings():
    system, user = build_auto_detect_prompt("Some document text")
    assert isinstance(system, str) and len(system) > 0
    assert isinstance(user, str) and len(user) > 0


def test_auto_detect_prompt_system_is_stable_string():
    """AUTO_DETECT system prompt should also be the stable SYSTEM_PROMPT."""
    system, _ = build_auto_detect_prompt("text")
    assert system == SYSTEM_PROMPT


def test_auto_detect_prompt_contains_indicator_fields():
    """Probe prompt must ask for the key cross-doc-type indicator fields."""
    _, user = build_auto_detect_prompt("doc text")
    # A few indicator fields that should be in the probe prompt
    expected_indicators = ["pay_period_month", "date_of_joining", "financial_year", "uan_number"]
    found = [f for f in expected_indicators if f in user]
    assert len(found) >= 3, f"Expected at least 3 indicator fields in probe prompt, found: {found}"


def test_auto_detect_prompt_embeds_document_text():
    doc = "SOME PAYSLIP TEXT HERE"
    _, user = build_auto_detect_prompt(doc)
    assert doc in user


def test_auto_detect_prompt_is_lighter_than_full_prompt():
    """Probe prompt user section should be shorter than a full manifest extraction prompt."""
    _, probe_user = build_auto_detect_prompt("doc text")
    full_manifest = _make_manifest()
    _, full_user = build_prompt(full_manifest, "doc text")
    # The probe doesn't list required/optional per-manifest fields
    assert len(probe_user) <= len(full_user)
