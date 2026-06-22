from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_env: str = "development"          # development | staging | production
    debug: bool = False

    # Database
    db_host: str = "localhost"
    db_port: int = 5433                   # YugabyteDB default (not 5432)
    db_name: str = "prana"
    db_user: str = "yugabyte"
    db_password: str = "yugabyte"
    db_pool_min: int = 5
    db_pool_max: int = 20

    @property
    def db_dsn(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    # AWS KMS (ap-south-1 only — no cross-region KMS calls)
    aws_region: str = "ap-south-1"
    aws_access_key_id: str = ""           # Empty = use IAM role in production
    aws_secret_access_key: str = ""

    # Platform HMAC secret (loaded from KMS at startup, never from env in production)
    platform_hmac_secret: str = "dev_secret"   # DEV ONLY — overridden by KMS in prod

    # JWT — RS256, KMS-signed in production
    jwt_public_key_path: str = "keys/jwt_public.pem"
    jwt_private_key_path: str = "keys/jwt_private.pem"   # Dev only; prod uses KMS signing
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "prana.in"

    # Redis (session blocklist + config cache)
    redis_url: str = "redis://localhost:6379/0"
    redis_config_ttl_seconds: int = 300   # 5-min TTL matches platform_summary_interval

    # Temporal
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "prana-dev"

    # Kafka (MSK in prod; local Kafka for dev)
    kafka_bootstrap_servers: str = "localhost:9092"

    # Internal service URLs
    ai_service_url:    str = "http://localhost:8001"
    ai_service_secret: str = "dev-secret"   # must match prana-ai PRANA_AI_SECRET env var
    ask_service_url:   str = "http://localhost:8002"
    ask_service_secret: str = "dev-secret"  # must match prana-ask PRANA_ASK_SECRET env var

    # S3 / MinIO (endpoint_url="" means real AWS S3; set to MinIO URL for local dev)
    s3_bucket_documents: str = "prana-documents-dev"
    s3_bucket_staging:   str = "prana-staging-dev"
    s3_region:           str = "ap-south-1"
    s3_endpoint_url:     str = ""          # e.g. "http://localhost:9010" for MinIO dev
    s3_access_key_id:    str = ""          # MinIO root user (overrides aws_access_key_id for S3)
    s3_secret_access_key: str = ""         # MinIO root password

    # SMTP / email (dev: leave host empty → logs OTP to console instead of sending)
    smtp_host:     str  = ""                          # e.g. "smtp.sendgrid.net"
    smtp_port:     int  = 587
    smtp_user:     str  = ""
    smtp_password: str  = ""
    smtp_from:     str  = "noreply@prana.in"
    smtp_use_tls:  bool = True

    # SMS gateway — Exotel (primary) or MSG91 (fallback). "dev" logs to console.
    sms_provider:       str = "dev"         # dev | exotel | msg91
    exotel_sid:         str = ""
    exotel_api_key:     str = ""
    exotel_api_token:   str = ""
    exotel_sender_id:   str = "PRANA"
    msg91_auth_key:     str = ""
    msg91_template_id:  str = ""

    # CORS — localhost for dev, GitHub Pages for demo, prana.in for prod
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "https://nshah12.github.io",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
