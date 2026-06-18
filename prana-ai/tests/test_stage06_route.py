"""Tests for pipeline/stage06_route.py — TDD stubs. Privacy contract covered by test_stage06_privacy.py."""
import pytest


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_stage06_moves_document_from_staging_to_permanent_s3_key():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_stage06_sets_pipeline_status_to_routed():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_stage06_publishes_doc_routed_to_kafka():
    raise NotImplementedError
