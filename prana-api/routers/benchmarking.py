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

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from db import get_db
from dependencies import Employee, require_oa
from services.benchmarking_service import BenchmarkingService

logger = logging.getLogger(__name__)
router = APIRouter()

# Was router-local `from auth_utils import decode_jwt` (same broken module as
# routers/alumni.py — doesn't exist anywhere in this codebase, so every request
# with a real Bearer token 500'd; only no-token 401 paths were ever tested).
# Fixed 2026-08-10 alongside alumni.py using the standard dependencies.py DI
# chain. See that file's comment for the full history.
_CHRO = Depends(require_oa("chro", "cfo", "oa_admin"))


async def _svc(db=Depends(get_db)):
    return BenchmarkingService(db=db)


# ── Employee endpoints ────────────────────────────────────────────────────────

class ConsentBody(BaseModel):
    grant: bool

@router.post("/consent")
async def set_benchmark_consent(
    body:   ConsentBody,
    current: Employee,
    svc:    BenchmarkingService = Depends(_svc),
):
    """Employee opts in or out of contributing their comp data to anonymous benchmarks."""
    return await svc.set_benchmark_consent(
        employee_user_id=current.user_id, grant=body.grant,
    )

@router.get("/consent")
async def get_benchmark_consent(
    current: Employee,
    svc:    BenchmarkingService = Depends(_svc),
):
    return await svc.get_benchmark_consent(employee_user_id=current.user_id)

@router.get("/my-position")
async def get_employee_benchmark(
    current: Employee,
    svc:    BenchmarkingService = Depends(_svc),
):
    """
    Employee sees their own percentile band in their cohort.
    Returns suppressed=True with label 'More data needed' if cohort < 50.
    Never returns raw ₹ salary or other employees' data.
    """
    return await svc.get_employee_benchmark(employee_user_id=current.user_id)


# ── CHRO / CFO endpoints ──────────────────────────────────────────────────────

@router.get("/org/bands")
async def get_chro_comp_bands(
    grade:      str | None = Query(default=None),
    department: str | None = Query(default=None),
    period:     str | None = Query(default=None),
    current=_CHRO,
    svc:    BenchmarkingService = Depends(_svc),
):
    """
    CHRO/CFO: org comp bands by grade/department.
    p25/p50/p75 returned for chart positioning — frontend renders as range markers,
    never as ₹ currency text.
    """
    return await svc.get_chro_comp_bands(
        tenant_id=current.tenant_id,
        grade=grade,
        department=department,
        period=period,
    )

@router.get("/org/opt-in-stats")
async def get_opt_in_stats(
    current=_CHRO,
    svc:    BenchmarkingService = Depends(_svc),
):
    """
    How many active employees have opted in vs. not.
    CHRO uses this to know how many more opt-ins are needed to publish suppressed bands.
    """
    return await svc.get_chro_unopted_count(tenant_id=current.tenant_id)

@router.get("/market/median")
async def get_market_median(
    grade:      str = Query(),
    department: str = Query(),
    period:     str | None = Query(default=None),
    current=_CHRO,
    svc:    BenchmarkingService = Depends(_svc),
):
    """
    Cross-tenant market median for a grade+department cohort.
    Only published when cohort has >= 50 contributors (k-anonymity).
    """
    return await svc.get_market_median(
        grade=grade, department=department, period=period,
    )
