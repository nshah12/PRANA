"""
Stage 01 — Batch Ingestion
Receives file bytes, computes SHA-256, uploads to S3 staging bucket.
Returns s3_key for downstream stages. No encryption yet.
"""
import hashlib
import uuid

import boto3


class Stage01Ingest:

    def __init__(self, s3_client, staging_bucket: str):
        self._s3 = s3_client
        self._bucket = staging_bucket

    def run(self, file_bytes: bytes, original_filename: str, tenant_id: str) -> dict:
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else "bin"
        staging_key = f"staging/{tenant_id}/{uuid.uuid4()}.{ext}"

        self._s3.put_object(
            Bucket=self._bucket,
            Key=staging_key,
            Body=file_bytes,
            ContentType=_content_type(ext),
            Metadata={"original_filename": original_filename, "sha256": file_hash},
        )

        return {
            "s3_key": staging_key,
            "s3_bucket": self._bucket,
            "file_size_bytes": len(file_bytes),
            "file_hash_sha256": file_hash,
            "ext": ext,
        }


def _content_type(ext: str) -> str:
    return {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}.get(ext, "application/octet-stream")
