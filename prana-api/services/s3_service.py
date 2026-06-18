"""
S3 / MinIO client factory.

In production:  s3_endpoint_url is empty → uses real AWS S3 with IAM role.
In local dev:   s3_endpoint_url = "http://localhost:9010" → routes to MinIO.

Usage:
    from services.s3_service import S3Service
    svc = S3Service(settings)
    svc.put_object(bucket, key, body, content_type)
    url = svc.presign_get(bucket, key, expires=3600)
"""
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


class S3Service:
    def __init__(self, settings):
        kwargs = dict(
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4"),
        )
        if settings.s3_endpoint_url:
            # MinIO or any S3-compatible store
            kwargs["endpoint_url"] = settings.s3_endpoint_url
            kwargs["aws_access_key_id"]     = settings.s3_access_key_id
            kwargs["aws_secret_access_key"] = settings.s3_secret_access_key
        elif settings.aws_access_key_id:
            # Explicit AWS creds (CI / non-IAM envs)
            kwargs["aws_access_key_id"]     = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        # else: IAM role via instance metadata (production)

        self._client  = boto3.client("s3", **kwargs)
        self._is_minio = bool(settings.s3_endpoint_url)

    # ── Core operations ───────────────────────────────────────────────────────

    def put_object(self, bucket: str, key: str, body: bytes,
                   content_type: str = "application/pdf",
                   metadata: dict | None = None) -> None:
        extra: dict = {"ContentType": content_type}
        if metadata:
            extra["Metadata"] = metadata
        self._client.put_object(Bucket=bucket, Key=key, Body=body, **extra)

    def get_object(self, bucket: str, key: str) -> bytes:
        resp = self._client.get_object(Bucket=bucket, Key=key)
        return resp["Body"].read()

    def delete_object(self, bucket: str, key: str) -> None:
        self._client.delete_object(Bucket=bucket, Key=key)

    def object_exists(self, bucket: str, key: str) -> bool:
        try:
            self._client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError:
            return False

    def presign_get(self, bucket: str, key: str, expires: int = 3600) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires,
        )

    def presign_put(self, bucket: str, key: str, expires: int = 300,
                    content_type: str = "application/pdf") -> str:
        return self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires,
        )

    # ── Bucket bootstrap (dev/CI only) ────────────────────────────────────────

    def ensure_bucket(self, bucket: str) -> None:
        """Create bucket if it doesn't exist. Safe to call on startup in dev."""
        try:
            self._client.head_bucket(Bucket=bucket)
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
                if self._is_minio:
                    self._client.create_bucket(Bucket=bucket)
                else:
                    self._client.create_bucket(
                        Bucket=bucket,
                        CreateBucketConfiguration={"LocationConstraint": self._client.meta.region_name},
                    )
            else:
                raise

    @property
    def raw_client(self):
        """Escape hatch for code that still uses boto3 directly."""
        return self._client
