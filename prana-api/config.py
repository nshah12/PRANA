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
    # prana_app_role — least-privilege role (migration 039_audit_role_revoke.sql):
    # can INSERT/SELECT/UPDATE/DELETE on every app table EXCEPT audit_event, where
    # UPDATE/DELETE is REVOKEd. The app's runtime pool must NEVER connect as the
    # yugabyte/postgres superuser — that would let it bypass the REVOKE and silently
    # tamper with audit history (see KAFKA_REDIS_ARCHITECTURE.md §8).
    db_user: str = "prana_app_role"
    db_password: str = "prana_app_role"
    db_pool_min: int = 5
    db_pool_max: int = 20

    @property
    def db_dsn(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def assert_production_ready(self) -> None:
        """
        Fail-closed secret guard (findings C2/C3).

        In production, refuse to start if any secret is still a known dev/test
        placeholder or a required prod-only secret is missing. No-op outside
        production so local dev and CI keep working on throwaway defaults.
        """
        if not self.is_production:
            return

        # field name -> values that are forbidden in production
        forbidden = {
            "platform_hmac_secret": {"dev_secret", ""},
            "db_password":          {"yugabyte", "prana_app_role", ""},
            # yugabyte/postgres/root are superuser-class accounts that can bypass the
            # audit_event REVOKE (migration 039) — the app must run as prana_app_role
            # or an equivalent least-privilege role, never the DB superuser.
            "db_user":              {"yugabyte", "postgres", "root", ""},
            "ai_service_secret":    {"dev-secret", ""},
            "ask_service_secret":   {"dev-secret", ""},
            "immudb_password":      {"immudb", ""},
        }
        violations = [f for f, bad in forbidden.items() if getattr(self, f) in bad]

        # Required prod-only secrets (no safe default exists)
        if not self.auth_encryption_key:
            violations.append("auth_encryption_key")
        if not self.jwt_kms_key_id:
            violations.append("jwt_kms_key_id")

        if violations:
            raise RuntimeError(
                "Refusing to start in production with placeholder/missing secrets: "
                + ", ".join(sorted(violations))
                + ". Inject real values via AWS Secrets Manager / KMS."
            )

    # AWS KMS (ap-south-1 only — no cross-region KMS calls)
    aws_region: str = "ap-south-1"
    aws_access_key_id: str = ""           # Empty = use IAM role in production
    aws_secret_access_key: str = ""
    kms_endpoint_url: str = ""            # e.g. "http://localhost:4566" for LocalStack dev; empty = real AWS KMS

    # Platform HMAC secret — PAN/NIK tokenization key.
    # Prod: injected from AWS Secrets Manager / KMS via env; MUST NOT be the dev default.
    # assert_production_ready() refuses to boot if this is still "dev_secret" in prod.
    platform_hmac_secret: str = "dev_secret"   # DEV ONLY

    # Auth encryption key — 32-byte AES-256 key (64 hex chars or base64) used to encrypt
    # HRMS signing secrets only (TOTP + mobile moved to platform_auth_kek_arn below,
    # 2026-07-19 — a static app secret decrypting everything platform-wide in one
    # shot was an unacceptable blast radius for those two fields).
    # Empty in dev/test → resolve_auth_dek() derives a non-zero key from platform_hmac_secret.
    auth_encryption_key: str = ""

    # Platform auth CMK — ONE real AWS KMS CMK (not a static secret) encrypting
    # mobile numbers and TOTP secrets (employee/OA/Portal-Admin). Provisioned once
    # via scripts/bootstrap_platform_auth_kek.py. Empty in dev before that script
    # has been run against LocalStack.
    platform_auth_kek_arn: str = ""

    # JWT — RS256. Dev/test: local PEM. Prod: KMS-signed (jwt_kms_key_id = CMK ARN).
    jwt_public_key_path: str = "keys/jwt_public.pem"
    jwt_private_key_path: str = "keys/jwt_private.pem"   # Dev/test only; prod signs via KMS
    jwt_kms_key_id: str = ""                             # KMS CMK ARN for RS256 signing in prod
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "prana.in"

    # Reverse-proxy hops we control (Kong, and optionally ALB). The real client IP is
    # this many entries from the RIGHT of X-Forwarded-For; anything further left is
    # attacker-controllable and must be ignored (finding H3).
    trusted_proxy_count: int = 1

    # Redis (session blocklist + config cache)
    redis_url: str = "redis://localhost:6379/0"
    redis_config_ttl_seconds: int = 300   # 5-min TTL matches platform_summary_interval

    # Temporal
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "prana-dev"

    # Kafka (MSK in prod; local Kafka for dev)
    kafka_bootstrap_servers: str = "localhost:9092"

    # Immudb — tamper-evident audit ledger (cryptographically verifiable, dual-written
    # alongside audit_event by AuditConsumer; see prana-docs/KAFKA_REDIS_ARCHITECTURE.md)
    immudb_host: str = "localhost"
    immudb_port: int = 3322
    immudb_user: str = "immudb"
    immudb_password: str = "immudb"
    immudb_database: str = "prana_audit"

    # Kong Admin API — VPC-internal only, never public
    kong_admin_url: str = "http://localhost:8001"  # dev: Kong not running → provisioning step is skipped gracefully

    # Portal URL — used in welcome emails and provisioning notifications
    portal_url: str = "https://prana.in"

    # Alumni network — CHRO outreach rate limit
    alumni_outreach_max_per_month: int = 3

    # Internal service URLs
    ai_service_url:    str = "http://localhost:8002"
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

    # Email gateway — selectable per environment via env var, same pattern as
    # sms_provider below. "dev" logs to console instead of sending.
    email_provider:    str = "dev"          # dev | ses | smtp
    ses_endpoint_url:  str = ""             # e.g. "http://localhost:4566" for LocalStack dev; empty = real AWS SES

    # SMTP fallback provider (used when email_provider="smtp" — e.g. SendGrid,
    # or any other SMTP-speaking service, so switching off SES needs no code change)
    smtp_host:     str  = ""                          # e.g. "smtp.sendgrid.net"
    smtp_port:     int  = 587
    smtp_user:     str  = ""
    smtp_password: str  = ""
    smtp_from:     str  = "noreply@prana.in"
    smtp_use_tls:  bool = True

    # SMS gateway — selectable per environment via env var. "dev" logs to console.
    sms_provider:       str = "dev"         # dev | aws | exotel | msg91
    sns_endpoint_url:   str = ""            # e.g. "http://localhost:4566" for LocalStack dev; empty = real AWS SNS
    exotel_sid:         str = ""
    exotel_api_key:     str = ""
    exotel_api_token:   str = ""
    exotel_sender_id:   str = "PRANA"
    msg91_auth_key:     str = ""
    msg91_template_id:  str = ""

    # WhatsApp — Communication Hub channel (prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md).
    # Meta Cloud API (WABA) shape — the one real option for most Indian deployments,
    # single-vendor chain for v1 (see §10 "out of scope"). "dev" logs to console.
    whatsapp_provider:              str = "dev"     # dev | waba
    whatsapp_waba_token:            str = ""        # Bearer token (Meta Cloud API access token)
    whatsapp_waba_phone_number_id:  str = ""        # Meta Cloud API phone_number_id (in the send-message URL path)
    whatsapp_waba_api_version:      str = "v20.0"   # Graph API version

    # IVR — new Communication Hub channel, Exotel + Ozonetel (both configurable,
    # ordered via ivr_vendor_chain in platform_config/tenant_config). "dev" logs
    # to console. Exotel IVR shares exotel_sid/api_key/api_token with SMS above
    # (same account) — only the flow reference is IVR-specific. Ozonetel is a
    # separate vendor account entirely — outbound.php's documented params
    # (api_key, phone_no, caller_id, outbound_version) verified against the
    # vendor's own KooKoo API docs 2026-07-24, see services/ivr_service.py.
    ivr_provider:            str = "dev"    # dev | exotel | ozonetel (informational — real
                                             # selection is per-message via ivr_vendor_chain)
    exotel_ivr_flow_id:      str = ""       # Exotel "Applet"/ExoML flow the call connects to
    ozonetel_api_key:        str = ""
    ozonetel_caller_id:      str = ""       # optional — your assigned Ozonetel caller-ID number

    # NCMEC CyberTipline — mandatory CSAM reporting (POCSO Act + IT Act). Empty
    # ncmec_report_url = dev mode: logs instead of calling out (see sms_provider
    # "dev" for the same pattern). Must be set in production — this is a legal
    # reporting obligation, not an optional integration.
    ncmec_report_url: str = ""
    ncmec_api_key:    str = ""

    # CORS — localhost for dev, GitHub Pages for demo, prana.in for prod
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "https://nshah12.github.io",
    ]

    @property
    def effective_cors_origins(self) -> list[str]:
        """
        CORS origins actually applied. In production, drop localhost and the
        github.io demo origin (finding: a third-party-controlled origin must never
        be allowed with credentials). Operators supply real origins via CORS_ORIGINS.
        """
        if self.is_production:
            return [o for o in self.cors_origins
                    if "localhost" not in o and "github.io" not in o]
        return self.cors_origins


@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
