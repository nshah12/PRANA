"""
LLM client — OpenAI-compatible interface for local or HuggingFace hosted inference.

Supported backends (all expose the same /v1/chat/completions endpoint):
  - HuggingFace Inference Endpoints: https://<endpoint>.huggingface.cloud/v1
  - Ollama (local):                   http://localhost:11434/v1
  - vLLM (local GPU server):          http://localhost:8000/v1
  - llama.cpp server (local):         http://localhost:8080/v1

Switch backends by changing `llm_base_url` and `*_llm_model` in platform_config.
Never import or call an inference backend directly from service code — always use this client.
"""

import httpx
from typing import Optional


class LLMClient:
    """OpenAI-compatible chat completion client."""

    def __init__(self, base_url: str, model: str, api_key: Optional[str] = None, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        # HuggingFace Inference Endpoints require Bearer token; local servers typically don't
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> str:
        """
        Send a chat completion request and return the response content string.

        temperature=0.0 for extraction (deterministic JSON).
        temperature=0.3–0.7 for insight/RAG generation (some creativity).
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers,
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class EmbeddingClient:
    """
    OpenAI-compatible embedding client for local or HuggingFace hosted models.

    Default model: BAAI/bge-m3 — multilingual, handles Hindi+English Indian HR docs.
    Config key: embedding_model, embedding_base_url, embedding_api_key
    """

    def __init__(self, base_url: str, model: str, api_key: Optional[str] = None, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def embed(self, text: str) -> list[float]:
        """Embed a single string. Returns a float vector."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/embeddings",
                headers=self._headers,
                json={"model": self.model, "input": text},
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple strings in one request."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/embeddings",
                headers=self._headers,
                json={"model": self.model, "input": texts},
            )
            resp.raise_for_status()
            items = resp.json()["data"]
            return [item["embedding"] for item in sorted(items, key=lambda x: x["index"])]


class QdrantClient:
    """
    Thin HTTP client for Qdrant vector DB.
    Wraps the Qdrant REST API — no qdrant-client SDK dep required.

    Used by:
      - Stage 05 resolution (cosine similarity search, Level 4)
      - CareerInsightService (upsert per-document embedding)
      - prana-ask RAG retrieval
    """

    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._headers = {"api-key": api_key} if api_key else {}

    async def ensure_collection(self, collection: str, vector_size: int = 1024) -> None:
        """Create collection if it doesn't exist (idempotent)."""
        url = f"{self.base_url}/collections/{collection}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, headers=self._headers)
            if resp.status_code == 200:
                return
            await client.put(
                url,
                headers=self._headers,
                json={"vectors": {"size": vector_size, "distance": "Cosine"}},
            )

    async def upsert(
        self,
        collection: str,
        point_id: str,
        vector: list[float],
        payload: dict,
    ) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.put(
                f"{self.base_url}/collections/{collection}/points",
                headers=self._headers,
                json={"points": [{"id": point_id, "vector": vector, "payload": payload}]},
            )
            resp.raise_for_status()

    async def search(
        self,
        collection: str,
        vector: list[float],
        limit: int = 5,
        filter_: Optional[dict] = None,
    ) -> list[dict]:
        """Returns list of {id, score, payload} matches."""
        body: dict = {"vector": vector, "limit": limit, "with_payload": True}
        if filter_:
            body["filter"] = filter_
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/collections/{collection}/points/search",
                headers=self._headers,
                json=body,
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            return resp.json().get("result", [])
