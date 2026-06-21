"""
ManifestService — resolves doc-type field manifests for the pipeline.

Resolution order (mirrors platform_config → tenant_config override pattern):
  1. Tenant override for this (tenant_id, doc_type) — if exists and active
  2. Platform default for this doc_type (tenant_id IS NULL)
  3. Raise ValueError (unknown doc_type, no manifest configured)

AUTO_DETECT scoring:
  For each active manifest, compute a classification score against the extracted
  partial fields. Score = fraction of classification_signals that fire.
  Returns the highest-scoring manifest if score >= AUTO_DETECT_MIN_SCORE.
"""

import json
import logging
from typing import Optional
from uuid import UUID

log = logging.getLogger(__name__)

AUTO_DETECT_MIN_SCORE = 0.5   # at least half the signals must fire to classify


class ManifestRecord:
    """Resolved manifest — ready for pipeline consumption."""

    def __init__(self, row: dict):
        self.manifest_id: str              = str(row["manifest_id"])
        self.doc_type: str                 = row["doc_type"]
        self.required_fields: list[str]    = _load_json(row["required_fields"])
        self.identity_fields: list[str]    = _load_json(row["identity_fields"])
        self.optional_fields: list[str]    = _load_json(row["optional_fields"])
        self.classification_signals: list  = _load_json(row["classification_signals"])
        self.confidence_threshold: float   = row["confidence_threshold"]
        self.supported_formats: list[str]  = _load_json(row["supported_formats"])
        self.is_tenant_override: bool      = row["tenant_id"] is not None

    def all_fields(self) -> list[str]:
        """Union of required + optional — full extraction target list."""
        seen = set()
        out = []
        for f in self.required_fields + self.optional_fields:
            if f not in seen:
                seen.add(f)
                out.append(f)
        return out

    def score_against(self, partial_fields: dict) -> float:
        """
        Score this manifest against partially extracted fields.
        Used by AUTO_DETECT to rank manifests.
        Returns 0.0–1.0; 0.0 if no classification_signals configured.
        """
        if not self.classification_signals:
            return 0.0
        fired = sum(
            1 for signal in self.classification_signals
            if all(
                partial_fields.get(field) not in (None, "", {})
                for field in signal
            )
        )
        return fired / len(self.classification_signals)

    def format_supported(self, ext: str) -> bool:
        return ext.lower() in self.supported_formats or "auto" in self.supported_formats


class ManifestService:

    def __init__(self, db):
        self._db = db

    async def resolve(self, tenant_id: UUID, doc_type: str) -> ManifestRecord:
        """
        Return the effective manifest for (tenant_id, doc_type).
        Tenant override takes precedence over platform default.
        """
        # Try tenant override first
        row = await self._db.fetchrow(
            """
            SELECT manifest_id, tenant_id, doc_type,
                   required_fields, identity_fields, optional_fields,
                   classification_signals, confidence_threshold, supported_formats
            FROM doc_type_field_manifest
            WHERE tenant_id = $1 AND doc_type = $2 AND is_active = TRUE
            """,
            tenant_id, doc_type,
        )

        if not row:
            # Fall back to platform default
            row = await self._db.fetchrow(
                """
                SELECT manifest_id, tenant_id, doc_type,
                       required_fields, identity_fields, optional_fields,
                       classification_signals, confidence_threshold, supported_formats
                FROM doc_type_field_manifest
                WHERE tenant_id IS NULL AND doc_type = $1 AND is_active = TRUE
                """,
                doc_type,
            )

        if not row:
            raise ValueError(f"No manifest configured for doc_type={doc_type!r}")

        return ManifestRecord(dict(row))

    async def auto_detect(
        self,
        tenant_id: UUID,
        partial_fields: dict,
        ext: str,
    ) -> Optional[ManifestRecord]:
        """
        Score all active manifests against partial_fields extracted from the doc.
        Returns the best-matching manifest if score >= AUTO_DETECT_MIN_SCORE,
        else None (→ unclassified_queue).
        """
        # Load all effective manifests for this tenant
        # (tenant overrides shadow platform defaults for the same doc_type)
        rows = await self._db.fetch(
            """
            SELECT DISTINCT ON (doc_type)
                   manifest_id, tenant_id, doc_type,
                   required_fields, identity_fields, optional_fields,
                   classification_signals, confidence_threshold, supported_formats
            FROM doc_type_field_manifest
            WHERE (tenant_id = $1 OR tenant_id IS NULL) AND is_active = TRUE
            ORDER BY doc_type, tenant_id NULLS LAST
            """,
            tenant_id,
        )

        if not rows:
            log.warning("auto_detect: no active manifests for tenant %s", tenant_id)
            return None

        scored = []
        for row in rows:
            manifest = ManifestRecord(dict(row))
            if not manifest.format_supported(ext):
                continue
            score = manifest.score_against(partial_fields)
            scored.append((score, manifest))

        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_manifest = scored[0]

        if best_score >= AUTO_DETECT_MIN_SCORE:
            log.info(
                "auto_detect: classified as %s (score=%.2f)",
                best_manifest.doc_type, best_score,
            )
            return best_manifest

        log.info(
            "auto_detect: no match above threshold (best=%s score=%.2f)",
            best_manifest.doc_type, best_score,
        )
        return None

    async def list_for_tenant(self, tenant_id: UUID) -> list[dict]:
        """
        Return all effective manifests for a tenant — tenant overrides merged
        with platform defaults. Used by OA-Admin UI to show current config.
        """
        rows = await self._db.fetch(
            """
            SELECT DISTINCT ON (doc_type)
                   manifest_id, tenant_id, doc_type,
                   required_fields, identity_fields, optional_fields,
                   classification_signals, confidence_threshold, supported_formats,
                   is_active, created_at, updated_at
            FROM doc_type_field_manifest
            WHERE (tenant_id = $1 OR tenant_id IS NULL) AND is_active = TRUE
            ORDER BY doc_type, tenant_id NULLS LAST
            """,
            tenant_id,
        )
        return [_serialize_manifest_row(dict(r)) for r in rows]

    async def upsert(
        self,
        tenant_id: UUID,
        doc_type: str,
        payload: dict,
        updated_by: UUID,
    ) -> dict:
        """Create or update a tenant override manifest."""
        existing = await self._db.fetchrow(
            "SELECT manifest_id FROM doc_type_field_manifest WHERE tenant_id=$1 AND doc_type=$2",
            tenant_id, doc_type,
        )

        if existing:
            row = await self._db.fetchrow(
                """
                UPDATE doc_type_field_manifest SET
                  required_fields        = $3,
                  identity_fields        = $4,
                  optional_fields        = $5,
                  classification_signals = $6,
                  confidence_threshold   = $7,
                  supported_formats      = $8,
                  is_active              = $9,
                  updated_by             = $10,
                  updated_at             = NOW()
                WHERE tenant_id = $1 AND doc_type = $2
                RETURNING manifest_id, tenant_id, doc_type, required_fields,
                          identity_fields, optional_fields, classification_signals,
                          confidence_threshold, supported_formats, is_active,
                          created_at, updated_at
                """,
                tenant_id, doc_type,
                json.dumps(payload.get("required_fields", [])),
                json.dumps(payload.get("identity_fields", [])),
                json.dumps(payload.get("optional_fields", [])),
                json.dumps(payload.get("classification_signals", [])),
                payload.get("confidence_threshold", 0.75),
                json.dumps(payload.get("supported_formats", ["pdf", "docx", "jpeg", "jpg", "png", "tiff"])),
                payload.get("is_active", True),
                updated_by,
            )
        else:
            row = await self._db.fetchrow(
                """
                INSERT INTO doc_type_field_manifest
                  (tenant_id, doc_type, required_fields, identity_fields,
                   optional_fields, classification_signals, confidence_threshold,
                   supported_formats, is_active, created_by, updated_by)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$10)
                RETURNING manifest_id, tenant_id, doc_type, required_fields,
                          identity_fields, optional_fields, classification_signals,
                          confidence_threshold, supported_formats, is_active,
                          created_at, updated_at
                """,
                tenant_id, doc_type,
                json.dumps(payload.get("required_fields", [])),
                json.dumps(payload.get("identity_fields", [])),
                json.dumps(payload.get("optional_fields", [])),
                json.dumps(payload.get("classification_signals", [])),
                payload.get("confidence_threshold", 0.75),
                json.dumps(payload.get("supported_formats", ["pdf", "docx", "jpeg", "jpg", "png", "tiff"])),
                payload.get("is_active", True),
                updated_by,
            )

        return _serialize_manifest_row(dict(row))

    async def delete_tenant_override(self, tenant_id: UUID, doc_type: str) -> bool:
        """
        Remove tenant override — pipeline falls back to platform default.
        Returns True if a row was deleted, False if no override existed.
        """
        result = await self._db.execute(
            "DELETE FROM doc_type_field_manifest WHERE tenant_id=$1 AND doc_type=$2",
            tenant_id, doc_type,
        )
        return result == "DELETE 1"

    async def list_all_platform(self) -> list[dict]:
        """PA only — list all platform defaults."""
        rows = await self._db.fetch(
            """
            SELECT manifest_id, tenant_id, doc_type, required_fields, identity_fields,
                   optional_fields, classification_signals, confidence_threshold,
                   supported_formats, is_active, created_at, updated_at
            FROM doc_type_field_manifest
            WHERE tenant_id IS NULL
            ORDER BY doc_type
            """
        )
        return [_serialize_manifest_row(dict(r)) for r in rows]


def _serialize_manifest_row(row: dict) -> dict:
    return {
        "manifest_id":             str(row["manifest_id"]),
        "tenant_id":               str(row["tenant_id"]) if row["tenant_id"] else None,
        "doc_type":                row["doc_type"],
        "required_fields":         _load_json(row["required_fields"]),
        "identity_fields":         _load_json(row["identity_fields"]),
        "optional_fields":         _load_json(row["optional_fields"]),
        "classification_signals":  _load_json(row["classification_signals"]),
        "confidence_threshold":    row["confidence_threshold"],
        "supported_formats":       _load_json(row["supported_formats"]),
        "is_active":               row["is_active"],
        "created_at":              row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at":              row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def _load_json(value) -> list:
    if isinstance(value, str):
        return json.loads(value)
    return value or []
