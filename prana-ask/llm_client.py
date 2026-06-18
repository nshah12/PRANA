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
from typing import Optional, Any


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
        messages: list[dict] | None = None,
    ) -> str:
        """
        Send a chat completion request and return the response content string.

        temperature=0.0 for extraction (deterministic JSON).
        temperature=0.3–0.7 for insight/RAG generation (some creativity).
        messages: if provided, used as the full turn history (replaces single user turn).
        """
        if messages is not None:
            chat_messages = [{"role": "system", "content": system}] + messages
        else:
            chat_messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers,
                json={
                    "model": self.model,
                    "messages": chat_messages,
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
    Thin async Qdrant REST client for vector similarity search.

    Per-employee collection naming: employee_{employee_user_id}
    Each point payload must contain: insight_text (str), doc_type (str), event_date (str)

    We use Qdrant's REST API directly to avoid adding the qdrant-client SDK dependency
    (which pulls in grpc and other heavy deps). The REST API is stable.
    """

    def __init__(self, url: str, api_key: Optional[str] = None, timeout: int = 10):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._headers: dict[str, str] = {}
        if api_key:
            self._headers["api-key"] = api_key

    async def collection_exists(self, collection: str) -> bool:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(
                    f"{self.url}/collections/{collection}",
                    headers=self._headers,
                )
                return resp.status_code == 200
            except httpx.RequestError:
                return False

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        top_k: int = 5,
        score_threshold: float = 0.30,
    ) -> list[dict[str, Any]]:
        """
        Search for similar vectors in a collection.

        Returns a list of payload dicts for the top_k matches above score_threshold.
        Returns [] if the collection does not exist or Qdrant is unavailable.
        """
        if not await self.collection_exists(collection):
            return []

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.url}/collections/{collection}/points/search",
                headers={**self._headers, "Content-Type": "application/json"},
                json={
                    "vector": query_vector,
                    "limit": top_k,
                    "score_threshold": score_threshold,
                    "with_payload": True,
                    "with_vector": False,
                },
            )
            resp.raise_for_status()
            results = resp.json().get("result", [])
            return [r["payload"] for r in results]

    async def upsert(
        self,
        collection: str,
        point_id: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        """Upsert a single point. Creates the collection if it doesn't exist."""
        await self._ensure_collection(collection, len(vector))
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.put(
                f"{self.url}/collections/{collection}/points",
                headers={**self._headers, "Content-Type": "application/json"},
                json={"points": [{"id": point_id, "vector": vector, "payload": payload}]},
            )
            resp.raise_for_status()

    async def _ensure_collection(self, collection: str, vector_size: int) -> None:
        if await self.collection_exists(collection):
            return
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.put(
                f"{self.url}/collections/{collection}",
                headers={**self._headers, "Content-Type": "application/json"},
                json={"vectors": {"size": vector_size, "distance": "Cosine"}},
            )
            resp.raise_for_status()
