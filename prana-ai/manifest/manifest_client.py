"""
ManifestClient — fetches resolved doc-type field manifests from prana-api.

prana-ai is a separate deployed service; it does NOT import from prana-api.
All manifest data comes via HTTP from prana-api's internal manifest endpoint.

Caches responses in-process for MANIFEST_CACHE_TTL seconds to avoid
per-document API calls at high ingestion throughput.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

log = logging.getLogger(__name__)

MANIFEST_CACHE_TTL = 300   # seconds — manifests change rarely


@dataclass
class ManifestData:
    """Resolved manifest received from prana-api."""
    manifest_id:             str
    doc_type:                str
    required_fields:         list[str]
    identity_fields:         list[str]
    optional_fields:         list[str]
    classification_signals:  list[list[str]]
    confidence_threshold:    float
    supported_formats:       list[str]
    is_tenant_override:      bool = False

    def all_fields(self) -> list[str]:
        seen = set()
        out = []
        for f in self.required_fields + self.optional_fields:
            if f not in seen:
                seen.add(f)
                out.append(f)
        return out

    def format_supported(self, ext: str) -> bool:
        lower_formats = [f.lower() for f in self.supported_formats]
        return ext.lower() in lower_formats or "auto" in lower_formats

    def score_against(self, partial_fields: dict) -> float:
        if not self.classification_signals:
            return 0.0
        fired = sum(
            1 for signal in self.classification_signals
            if all(
                partial_fields.get(f) not in (None, "", {})
                for f in signal
            )
        )
        return fired / len(self.classification_signals)


@dataclass
class _CacheEntry:
    data: object
    expires_at: float


class ManifestClient:
    """
    HTTP client for fetching manifests from prana-api.
    One instance per worker process — shared across pipeline stages.
    """

    def __init__(self, prana_api_base_url: str, internal_token: str):
        self._base = prana_api_base_url.rstrip("/")
        self._token = internal_token
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def resolve(self, tenant_id: str, doc_type: str) -> ManifestData:
        """
        Fetch the effective manifest for (tenant_id, doc_type).
        Cached for MANIFEST_CACHE_TTL seconds.
        """
        cache_key = f"{tenant_id}:{doc_type}"
        cached = self._cache.get(cache_key)
        if cached and cached.expires_at > time.monotonic():
            return cached.data

        async with self._lock:
            # Double-check after acquiring lock
            cached = self._cache.get(cache_key)
            if cached and cached.expires_at > time.monotonic():
                return cached.data

            data = await self._fetch_manifest(tenant_id, doc_type)
            self._cache[cache_key] = _CacheEntry(
                data=data,
                expires_at=time.monotonic() + MANIFEST_CACHE_TTL,
            )
            return data

    async def list_all(self, tenant_id: str) -> list[ManifestData]:
        """Fetch all active manifests for a tenant (for AUTO_DETECT scoring)."""
        cache_key = f"{tenant_id}:__all__"
        cached = self._cache.get(cache_key)
        if cached and cached.expires_at > time.monotonic():
            return cached.data

        async with self._lock:
            cached = self._cache.get(cache_key)
            if cached and cached.expires_at > time.monotonic():
                return cached.data

            data = await self._fetch_all_manifests(tenant_id)
            self._cache[cache_key] = _CacheEntry(
                data=data,
                expires_at=time.monotonic() + MANIFEST_CACHE_TTL,
            )
            return data

    def invalidate(self, tenant_id: str, doc_type: Optional[str] = None) -> None:
        """Invalidate cache entries after a manifest update."""
        if doc_type:
            self._cache.pop(f"{tenant_id}:{doc_type}", None)
        self._cache.pop(f"{tenant_id}:__all__", None)

    async def _fetch_manifest(self, tenant_id: str, doc_type: str) -> ManifestData:
        url = f"{self._base}/internal/manifests/{tenant_id}/{doc_type}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=self._headers())
            if resp.status_code == 404:
                raise ValueError(f"No manifest for doc_type={doc_type!r} tenant={tenant_id}")
            resp.raise_for_status()
            return _parse_manifest(resp.json()["manifest"])

    async def _fetch_all_manifests(self, tenant_id: str) -> list[ManifestData]:
        url = f"{self._base}/internal/manifests/{tenant_id}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=self._headers())
            resp.raise_for_status()
            return [_parse_manifest(m) for m in resp.json()["items"]]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}


def _parse_manifest(data: dict) -> ManifestData:
    return ManifestData(
        manifest_id=data["manifest_id"],
        doc_type=data["doc_type"],
        required_fields=data.get("required_fields", []),
        identity_fields=data.get("identity_fields", []),
        optional_fields=data.get("optional_fields", []),
        classification_signals=data.get("classification_signals", []),
        confidence_threshold=data.get("confidence_threshold", 0.75),
        supported_formats=data.get("supported_formats", ["pdf", "docx", "jpeg", "jpg", "png", "tiff"]),
        is_tenant_override=data.get("is_tenant_override", False),
    )
