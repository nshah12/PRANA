"""
Stage 05 — Identity Resolution (manifest-driven)

Runs the resolution ladder using identity_fields priority from the manifest.
The manifest specifies the order in which identity signals should be tried —
e.g. ["pan_number", "employee_id", "employee_name"] means pan_token first,
then employee_id if no PAN was found, then fuzzy name as last resort before embedding.

No LLM — pure algorithmic matching.
"""
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

import asyncpg

from manifest.manifest_client import ManifestData
from resolution.resolution_service import ResolutionService, ResolutionMethod
from resolution.fuzzy_service import FuzzyService
from llm_client import EmbeddingClient, QdrantClient


@dataclass
class Stage05Result:
    employee_uuid: Optional[str]
    method: str
    confidence: float
    needs_exception: bool
    exception_type: Optional[str]   # NO_MATCH | MULTIPLE_CANDIDATES | LOW_CONFIDENCE
    candidates: list                # top candidates for exception queue context


@dataclass
class CrossTenantViolation:
    """Returned when the document's pan_token belongs to a different tenant's employee."""
    violation_type: str             # always "CROSS_TENANT"
    pan_token: str
    uploading_tenant_id: str
    owner_tenant_id: str            # the tenant that legitimately owns this PAN


class Stage05Resolve:

    def __init__(
        self,
        db: asyncpg.Connection,
        embedding_client: EmbeddingClient,
        qdrant_client: QdrantClient | None = None,
    ):
        fuzzy = FuzzyService(db)
        self._svc = ResolutionService(db, embedding_client, fuzzy, qdrant_client)

    async def run(
        self,
        pan_token: Optional[str],
        tenant_id: str,
        extracted_fields: dict,
        manifest: Optional[ManifestData] = None,
    ) -> "Stage05Result | CrossTenantViolation":
        """
        Resolve identity using the manifest's identity_fields priority order.

        manifest.identity_fields = e.g. ["pan_number", "employee_id", "employee_name"]

        The ladder levels are still fixed (EXACT_PAN → EMP_ID → FUZZY_NAME → EMBEDDING)
        but the manifest's identity_fields determines which signals we actually attempt,
        in priority order. If pan_number is not in identity_fields, Level 1 is skipped.
        If manifest is None (e.g. not found), all levels are attempted.
        """
        # Cross-tenant check: if pan_token exists in a DIFFERENT tenant, reject immediately.
        # idx_emp_pan_token makes this O(1). We query across all tenants on purpose.
        if pan_token:
            row = await self._svc._db.fetchrow(
                "SELECT tenant_id FROM employee_master WHERE pan_token = $1 LIMIT 1",
                pan_token,
            )
            if row and str(row["tenant_id"]) != tenant_id:
                return CrossTenantViolation(
                    violation_type="CROSS_TENANT",
                    pan_token=pan_token,
                    uploading_tenant_id=tenant_id,
                    owner_tenant_id=str(row["tenant_id"]),
                )

        # Derive which signals to use from manifest, preserving resolution ladder order
        # If no manifest: attempt all levels
        identity_fields = manifest.identity_fields if manifest else ["pan_number", "employee_id", "employee_name"]
        use_pan    = "pan_number" in identity_fields and pan_token
        use_emp_id = "employee_id" in identity_fields
        use_name   = "employee_name" in identity_fields
        # Embedding (Level 4) always available as final fallback when manifest has name
        use_embed  = use_name

        result = await self._svc.resolve(
            tenant_id=UUID(tenant_id),
            pan_token=pan_token if use_pan else None,
            extracted_fields=extracted_fields,
            skip_emp_id=not use_emp_id,
            skip_fuzzy=not use_name,
            skip_embedding=not use_embed,
        )

        if result.method == ResolutionMethod.UNRESOLVED:
            return Stage05Result(
                employee_uuid=None,
                method=result.method.value,
                confidence=0.0,
                needs_exception=True,
                exception_type="NO_MATCH",
                candidates=result.candidates,
            )

        if len(result.candidates) > 1 and result.confidence < 0.88:
            return Stage05Result(
                employee_uuid=None,
                method=result.method.value,
                confidence=result.confidence,
                needs_exception=True,
                exception_type="MULTIPLE_CANDIDATES",
                candidates=result.candidates,
            )

        return Stage05Result(
            employee_uuid=str(result.employee_uuid),
            method=result.method.value,
            confidence=result.confidence,
            needs_exception=False,
            exception_type=None,
            candidates=result.candidates,
        )
