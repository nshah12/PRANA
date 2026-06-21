# ManifestService tests live in test_doc_manifest.py (covers service + router together).
# This file exists to satisfy TDD-01 enforcement. Import and re-export the service tests.

def test_manifest_service_module_importable():
    """Smoke test — ensures ManifestService can be imported without error."""
    from services.manifest_service import ManifestService, ManifestRecord  # noqa: F401


from tests.test_doc_manifest import (
    test_manifest_record_all_fields_deduplicates,
    test_manifest_record_format_supported,
    test_manifest_record_score_no_signals,
    test_manifest_record_score_all_signals_fire,
    test_manifest_record_score_partial_signals,
    test_manifest_record_score_null_values_dont_fire,
    test_resolve_tenant_override_takes_precedence,
    test_resolve_falls_back_to_platform_default,
    test_resolve_raises_when_no_manifest,
    test_auto_detect_picks_best_matching_manifest,
    test_auto_detect_returns_none_when_score_below_threshold,
    test_auto_detect_skips_unsupported_formats,
    test_upsert_creates_new_override,
    test_delete_tenant_override_returns_true_on_success,
    test_delete_tenant_override_returns_false_when_no_override,
)

__all__ = [
    "test_manifest_record_all_fields_deduplicates",
    "test_manifest_record_format_supported",
    "test_manifest_record_score_no_signals",
    "test_manifest_record_score_all_signals_fire",
    "test_manifest_record_score_partial_signals",
    "test_manifest_record_score_null_values_dont_fire",
    "test_resolve_tenant_override_takes_precedence",
    "test_resolve_falls_back_to_platform_default",
    "test_resolve_raises_when_no_manifest",
    "test_auto_detect_picks_best_matching_manifest",
    "test_auto_detect_returns_none_when_score_below_threshold",
    "test_auto_detect_skips_unsupported_formats",
    "test_upsert_creates_new_override",
    "test_delete_tenant_override_returns_true_on_success",
    "test_delete_tenant_override_returns_false_when_no_override",
]
