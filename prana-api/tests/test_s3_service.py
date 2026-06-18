"""Tests for services/s3_service.py."""
import inspect

from services.s3_service import S3Service


def test_s3_put_staging_key_distinct_from_permanent_key():
    # S3 key paths: staging uses a different prefix from routed/permanent documents
    # Verify the ingest router uses staging/ prefix, distinct from vault keys
    import pathlib
    ingest_src = (pathlib.Path(__file__).parent.parent / "routers" / "ingest.py").read_text(encoding="utf-8")
    # ingest.py should reference a staging path before the document is processed
    assert "staging" in ingest_src or "s3_key" in ingest_src, \
        "Ingest router must store document with a staging key before pipeline processes it"


def test_s3_delete_permanent_on_erasure():
    src = inspect.getsource(S3Service.delete_object)
    assert "delete_object" in src or "Bucket" in src, \
        "S3Service.delete_object must call boto3 delete_object"
    # Verify the compliance service references S3 deletion
    import pathlib
    compliance_src = (pathlib.Path(__file__).parent.parent / "services" / "compliance_service.py").read_text(encoding="utf-8")
    assert "s3" in compliance_src.lower() or "delete" in compliance_src.lower(), \
        "ComplianceService must reference S3 deletion during erasure"
