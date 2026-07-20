"""
Comp Benchmarking router.

Employee endpoints  /v1/benchmarking/...      — employee JWT
CHRO endpoints      /v1/chro/benchmarking/... — OA JWT (CHRO / CFO role)

Privacy rules enforced here:
- Employee sees only their own percentile band + label, never raw ₹ or peers' data.
- CHRO sees org band positions (p25/p50/p75) for chart rendering only — not as ₹ text.
- Any cohort with < K_MIN contributors is suppressed at the service layer.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from db import get_db
from services.benchmarking_service import BenchmarkingService

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_employee_jwt(authorization: Annotated[str | None, Header()] = None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="MISSING_TOKEN")
    from auth_utils import decode_jwt
    claims = decode_jwt(authorization.removeprefix("Bearer "))
    if claims.get("role") != "employee":
        raise HTTPException(status_code=403, detail="EMPLOYEE_ONLY")
    return claims

def _require_chro_jwt(authorization: Annotated[str | None, Header()] = None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="MISSING_TOKEN")
    from auth_utils import decode_jwt
    claims = decode_jwt(authorization.removeprefix("Bearer "))
    if claims.get("role") not in ("CHRO", "CFO", "OA-Admin"):
        raise HTTPException(status_code=403, detail="CHRO_ROLE_REQUIRED")
    return claims

async def _svc(db=Depends(get_db)):
    return BenchmarkingService(db=db)


# ── Employee endpoints ────────────────────────────────────────────────────────

class ConsentBody(BaseModel):
    grant: bool

@router.post("/consent")
async def set_benchmark_consent(
    body:   ConsentBody,
    claims: dict = Depends(_require_employee_jwt),
    svc:    BenchmarkingService = Depends(_svc),
):
    """Employee opts in or out of contributing their comp data to anonymous benchmarks."""
    return await svc.set_benchmark_consent(
        employee_user_id=claims["sub"], grant=body.grant,
    )

@router.get("/consent")
async def get_benchmark_consent(
    claims: dict = Depends(_require_employee_jwt),
    svc:    BenchmarkingService = Depends(_svc),
):
    return await svc.get_benchmark_consent(employee_user_id=claims["sub"])

@router.get("/my-position")
async def get_employee_benchmark(
    claims: dict = Depends(_require_employee_jwt),
    svc:    BenchmarkingService = Depends(_svc),
):
    """
    Employee sees their own percentile band in their cohort.
    Returns suppressed=True with label 'More data needed' if cohort < 50.
    Never returns raw ₹ salary or other employees' data.
    """
    return await svc.get_employee_benchmark(employee_user_id=claims["sub"])


# ── CHRO / CFO endpoints ──────────────────────────────────────────────────────

@router.get("/org/bands")
async def get_chro_comp_bands(
    grade:      str | None = Query(default=None),
    department: str | None = Query(default=None),
    period:     str | None = Query(default=None),
    claims: dict = Depends(_require_chro_jwt),
    svc:    BenchmarkingService = Depends(_svc),
):
    """
    CHRO/CFO: org comp bands by grade/department.
    p25/p50/p75 returned for chart positioning — frontend renders as range markers,
    never as ₹ currency text.
    """
    return await svc.get_chro_comp_bands(
        tenant_id=claims["tenant_id"],
        grade=grade,
        department=department,
        period=period,
    )

@router.get("/org/opt-in-stats")
async def get_opt_in_stats(
    claims: dict = Depends(_require_chro_jwt),
    svc:    BenchmarkingService = Depends(_svc),
):
    """
    How many active employees have opted in vs. not.
    CHRO uses this to know how many more opt-ins are needed to publish suppressed bands.
    """
    return await svc.get_chro_unopted_count(tenant_id=claims["tenant_id"])

@router.get("/market/median")
async def get_market_median(
    grade:      str = Query(),
    department: str = Query(),
    period:     str | None = Query(default=None),
    claims: dict = Depends(_require_chro_jwt),
    svc:    BenchmarkingService = Depends(_svc),
):
    """
    Cross-tenant market median for a grade+department cohort.
    Only published when cohort has >= 50 contributors (k-anonymity).
    """
    return await svc.get_market_median(
        grade=grade, department=department, period=period,
    )
