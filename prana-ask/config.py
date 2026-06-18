import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class Settings:
    host:       str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port:       int = field(default_factory=lambda: int(os.getenv("PORT", "8002")))
    debug:      bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    api_secret: str = field(default_factory=lambda: os.getenv("PRANA_ASK_SECRET", "dev-secret"))

    # LLM — Llama 3.1 8B for conversational RAG
    llm_base_url:    str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"))
    ask_llm_model:   str = field(default_factory=lambda: os.getenv("ASK_LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct"))
    llm_api_key:     str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_timeout:     int = field(default_factory=lambda: int(os.getenv("LLM_TIMEOUT", "60")))

    # Embeddings — bge-m3 for query embedding
    embedding_base_url: str = field(default_factory=lambda: os.getenv("EMBEDDING_BASE_URL", "http://localhost:11434/v1"))
    embedding_model:    str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"))
    embedding_api_key:  str = field(default_factory=lambda: os.getenv("EMBEDDING_API_KEY", ""))

    # Database (career timeline + vault summary queries)
    db_dsn: str = field(default_factory=lambda: os.getenv("DB_DSN", "postgresql://prana:prana@localhost:5433/prana"))

    # Qdrant vector store (per-employee collections: employee_{uuid})
    qdrant_url:  str = field(default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333"))
    qdrant_api_key: str = field(default_factory=lambda: os.getenv("QDRANT_API_KEY", ""))

    # Redis (conversation history)
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/1"))

    # Rate limiting
    ask_rate_limit_per_hour: int = field(default_factory=lambda: int(os.getenv("ASK_RATE_LIMIT_PER_HOUR", "20")))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
