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
MANIFEST_PROBE_LIMIT = 50     # defensive cap on manifests scored per detection attempt


class ManifestRecord:
    """Resolved manifest — ready for pipeline consumption."""

    def __init__(self, row: dict):
        self.manifest_id: str              = str(row["manifest_id"])
        self.doc_type: str                 = row["doc_type"]
        self.required_fields: list[str]    = _load_json(row["required_fields"])
        self.identity_fields: list[str]    = _load_json(row["identity_fields"])
        self.optional_fields: list[str]    = _load_json(row["optional_fields"])
        self.classification_signals: list  = _load_json(row["classification_signals"])
        self.signal_weights: list[float]   = _load_json(row.get("signal_weights"))
        # Subset of required/identity/optional fields explicitly confirmed
        # non-monetary. Anything NOT here is sensitive by default (fail-closed)
        # — unioned into prana-ai's static _SAFE_METADATA_FIELDS allowlist.
        self.safe_fields: list[str]        = _load_json(row.get("safe_fields"))
        self.confidence_threshold: float   = row["confidence_threshold"]
        self.supported_formats: list[str]  = _load_json(row["supported_formats"])
        self.is_tenant_override: bool      = row["tenant_id"] is not None
        self.usage_count: int              = row.get("usage_count") or 0

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

        Each signal group can carry a relative weight (signal_weights) so a
        highly-discriminative signal (e.g. uan_number + pf_number) counts for
        more than a generic one (e.g. employee_name + employer_name). If
        signal_weights is empty or its length doesn't match classification_signals
        (e.g. legacy rows predating this column), falls back to equal weighting.
        """
        if not self.classification_signals:
            return 0.0

        weights = self.signal_weights
        if not weights or len(weights) != len(self.classification_signals):
            weights = [1.0] * len(self.classification_signals)

        total_weight = sum(weights)
        if total_weight <= 0:
            return 0.0

        fired_weight = sum(
            weight for signal, weight in zip(self.classification_signals, weights)
            if all(
                partial_fields.get(field) not in (None, "", {})
                for field in signal
            )
        )
        return fired_weight / total_weight

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
                   classification_signals, signal_weights, confidence_threshold,
                   supported_formats, usage_count, safe_fields
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
                       classification_signals, signal_weights, confidence_threshold,
                       supported_formats, usage_count, safe_fields
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

        Manifests are considered in usage_count DESC order and capped at
        MANIFEST_PROBE_LIMIT (gap 1c) — defense-in-depth against unbounded
        doc_type growth; DISTINCT ON (doc_type) already bounds the row count
        to the number of distinct doc types today. Ties in score are broken
        by usage_count — prefer the doc_type this tenant classifies most often.
        """
        # Load effective manifests for this tenant (tenant overrides shadow
        # platform defaults for the same doc_type), ordered by how often this
        # tenant actually uses each doc_type, capped defensively.
        rows = await self._db.fetch(
            """
            SELECT manifest_id, tenant_id, doc_type,
                   required_fields, identity_fields, optional_fields,
                   classification_signals, signal_weights, confidence_threshold,
                   supported_formats, usage_count
            FROM (
                SELECT DISTINCT ON (doc_type)
                       manifest_id, tenant_id, doc_type,
                       required_fields, identity_fields, optional_fields,
                       classification_signals, signal_weights, confidence_threshold,
                       supported_formats, usage_count
                FROM doc_type_field_manifest
                WHERE (tenant_id = $1 OR tenant_id IS NULL) AND is_active = TRUE
                ORDER BY doc_type, tenant_id NULLS LAST
            ) deduped
            ORDER BY usage_count DESC
            LIMIT $2
            """,
            tenant_id, MANIFEST_PROBE_LIMIT,
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

        scored.sort(key=lambda x: (x[0], x[1].usage_count), reverse=True)
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

    async def record_usage(self, tenant_id: UUID, doc_type: str) -> None:
        """
        Bump usage_count for the manifest that classified this doc_type.
        Called as a side-effect of /internal/pipeline/routed — a successful
        route confirms the classification was correct, so it's a good signal
        for future AUTO_DETECT tie-breaking. Tenant override is bumped if one
        exists; otherwise the platform default is bumped.
        """
        updated = await self._db.fetchval(
            """
            UPDATE doc_type_field_manifest
            SET usage_count = usage_count + 1
            WHERE tenant_id = $1 AND doc_type = $2 AND is_active = TRUE
            RETURNING manifest_id
            """,
            tenant_id, doc_type,
        )
        if updated:
            return

        await self._db.execute(
            """
            UPDATE doc_type_field_manifest
            SET usage_count = usage_count + 1
            WHERE tenant_id IS NULL AND doc_type = $1 AND is_active = TRUE
            """,
            doc_type,
        )

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
                   classification_signals, signal_weights, confidence_threshold,
                   supported_formats, usage_count,
                   is_active, created_at, updated_at, safe_fields
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
                  signal_weights         = $7,
                  confidence_threshold   = $8,
                  supported_formats      = $9,
                  is_active              = $10,
                  updated_by             = $11,
                  updated_at             = NOW(),
                  safe_fields            = $12
                WHERE tenant_id = $1 AND doc_type = $2
                RETURNING manifest_id, tenant_id, doc_type, required_fields,
                          identity_fields, optional_fields, classification_signals,
                          signal_weights, confidence_threshold, supported_formats,
                          usage_count, is_active, created_at, updated_at, safe_fields
                """,
                tenant_id, doc_type,
                json.dumps(payload.get("required_fields", [])),
                json.dumps(payload.get("identity_fields", [])),
                json.dumps(payload.get("optional_fields", [])),
                json.dumps(payload.get("classification_signals", [])),
                json.dumps(payload.get("signal_weights", [])),
                payload.get("confidence_threshold", 0.75),
                json.dumps(payload.get("supported_formats", ["pdf", "docx", "jpeg", "jpg", "png", "tiff"])),
                payload.get("is_active", True),
                updated_by,
                json.dumps(payload.get("safe_fields", [])),
            )
        else:
            row = await self._db.fetchrow(
                """
                INSERT INTO doc_type_field_manifest
                  (tenant_id, doc_type, required_fields, identity_fields,
                   optional_fields, classification_signals, signal_weights,
                   confidence_threshold, supported_formats, is_active,
                   created_by, updated_by, safe_fields)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$11,$12)
                RETURNING manifest_id, tenant_id, doc_type, required_fields,
                          identity_fields, optional_fields, classification_signals,
                          signal_weights, confidence_threshold, supported_formats,
                          usage_count, is_active, created_at, updated_at, safe_fields
                """,
                tenant_id, doc_type,
                json.dumps(payload.get("required_fields", [])),
                json.dumps(payload.get("identity_fields", [])),
                json.dumps(payload.get("optional_fields", [])),
                json.dumps(payload.get("classification_signals", [])),
                json.dumps(payload.get("signal_weights", [])),
                payload.get("confidence_threshold", 0.75),
                json.dumps(payload.get("supported_formats", ["pdf", "docx", "jpeg", "jpg", "png", "tiff"])),
                payload.get("is_active", True),
                updated_by,
                json.dumps(payload.get("safe_fields", [])),
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
                   optional_fields, classification_signals, signal_weights,
                   confidence_threshold, supported_formats, usage_count,
                   is_active, created_at, updated_at, safe_fields
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
        "signal_weights":          _load_json(row.get("signal_weights")),
        "safe_fields":             _load_json(row.get("safe_fields")),
        "confidence_threshold":    row["confidence_threshold"],
        "supported_formats":       _load_json(row["supported_formats"]),
        "usage_count":             row.get("usage_count") or 0,
        "is_active":               row["is_active"],
        "created_at":              row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at":              row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def _load_json(value) -> list:
    if isinstance(value, str):
        return json.loads(value)
    return value or []
