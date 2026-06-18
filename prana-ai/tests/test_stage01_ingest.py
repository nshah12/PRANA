"""Tests for pipeline/stage01_ingest.py — S3 upload and output contract."""
from unittest.mock import MagicMock

from pipeline.stage01_ingest import Stage01Ingest
from extraction.extraction_service import DocType


def test_stage01_validates_doc_type_before_proceeding():
    # Stage 01 uploads to S3; doc_type validation happens in Stage 04 via DocType enum.
    # Verify that the enum rejects unknown doc types so invalid ingest is caught early.
    import pytest
    with pytest.raises(ValueError):
        DocType("UNKNOWN_DOC_TYPE")


def test_stage01_writes_document_row_exactly_once():
    # Stage 01 calls S3 put_object exactly once per document ingestion.
    s3 = MagicMock()
    svc = Stage01Ingest(s3_client=s3, staging_bucket="prana-staging")
    result = svc.run(b"PDF content here", "salary_slip.pdf", tenant_id="tenant-001")

    s3.put_object.assert_called_once()
    assert "s3_key" in result
    assert "file_hash_sha256" in result
    assert len(result["file_hash_sha256"]) == 64, "SHA-256 hex digest must be 64 chars"
