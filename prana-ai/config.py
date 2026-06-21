"""
Runtime config for prana-ai.
All LLM/embedding settings come from environment variables (injected by Kubernetes / ECS).
Platform-level overrides are read from DB at startup via prana-api's config tables,
but prana-ai is a GPU worker and reads its own env — not the prana-api process.
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class Settings:
    # ── Service ───────────────────────────────────────────────────────────────
    host:       str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port:       int = field(default_factory=lambda: int(os.getenv("PORT", "8001")))
    debug:      bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    api_secret: str = field(default_factory=lambda: os.getenv("PRANA_AI_SECRET", "dev-secret"))

    # ── LLM — extraction (Qwen 14B) ──────────────────────────────────────────
    llm_base_url:          str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"))
    extraction_llm_model:  str = field(default_factory=lambda: os.getenv("EXTRACTION_LLM_MODEL", "Qwen/Qwen2.5-14B-Instruct"))
    llm_api_key:           str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_timeout:           int = field(default_factory=lambda: int(os.getenv("LLM_TIMEOUT", "120")))

    # ── Embeddings (bge-m3) ───────────────────────────────────────────────────
    embedding_base_url:  str = field(default_factory=lambda: os.getenv("EMBEDDING_BASE_URL", "http://localhost:11434/v1"))
    embedding_model:     str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"))
    embedding_api_key:   str = field(default_factory=lambda: os.getenv("EMBEDDING_API_KEY", ""))

    # ── Database (resolution service needs direct DB access) ──────────────────
    db_dsn:      str = field(default_factory=lambda: os.getenv("DB_DSN", "postgresql://prana:prana@localhost:5433/prana"))

    # ── AWS (Textract fallback, S3) ───────────────────────────────────────────
    aws_region:            str = field(default_factory=lambda: os.getenv("AWS_REGION", "ap-south-1"))
    aws_access_key_id:     str = field(default_factory=lambda: os.getenv("AWS_ACCESS_KEY_ID", ""))
    aws_secret_access_key: str = field(default_factory=lambda: os.getenv("AWS_SECRET_ACCESS_KEY", ""))

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_url:     str = field(default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333"))
    qdrant_api_key: str = field(default_factory=lambda: os.getenv("QDRANT_API_KEY", ""))

    # ── ClamAV ────────────────────────────────────────────────────────────────
    clamd_socket: str = field(default_factory=lambda: os.getenv("CLAMD_SOCKET", "/var/run/clamav/clamd.ctl"))

    # ── prana-api internal — ManifestClient fetches manifests via HTTP ────────
    prana_api_base_url:      str = field(default_factory=lambda: os.getenv("PRANA_API_BASE_URL", "http://localhost:8000"))
    internal_service_token:  str = field(default_factory=lambda: os.getenv("INTERNAL_SERVICE_TOKEN", "dev-internal-token"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
