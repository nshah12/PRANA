"""
Tests for BenchmarkingService: consent, k-anonymity suppression, CHRO band access.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from services.benchmarking_service import BenchmarkingService, K_MIN, _cohort_key, _experience_band


def _make_db(**overrides):
    db = AsyncMock()
    db.transaction = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    for k, v in overrides.items():
        setattr(db, k, AsyncMock(return_value=v))
    return db

def _make_svc(db):
    return BenchmarkingService(db=db)


# ── Consent ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_benchmark_consent_grant():
    db = _make_db()
    svc = _make_svc(db)
    result = await svc.set_benchmark_consent("emp-1", grant=True)
    assert result["peer_benchmark_consent"] is True
    sql = db.execute.call_args_list[0][0][0]
    assert "peer_benchmark" in sql

@pytest.mark.asyncio
async def test_set_benchmark_consent_withdraw_marks_contributions():
    db = _make_db()
    svc = _make_svc(db)
    await svc.set_benchmark_consent("emp-1", grant=False)
    calls = [c[0][0] for c in db.execute.call_args_list]
    assert any("withdrawn_at" in sql for sql in calls)

@pytest.mark.asyncio
async def test_get_benchmark_consent_not_set():
    db = _make_db(fetchrow=None)
    svc = _make_svc(db)
    result = await svc.get_benchmark_consent("emp-new")
    assert result["peer_benchmark_consent"] is False


# ── k-anonymity: employee view ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_employee_benchmark_suppressed_below_k_min():
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "cohort_key":      "senior-engineer|fintech|bengaluru|5-8y",
        "percentile_band": "P60-P75",
        "cohort_size":     30,        # below K_MIN (50)
        "suppressed":      True,
        "label_text":      "More data needed",
        "computed_at":     __import__('datetime').datetime(2026, 1, 1),
    }[k]
    db = _make_db(fetch=[row])
    svc = _make_svc(db)
    result = await svc.get_employee_benchmark("emp-1")
    item = result["items"][0]
    assert item["suppressed"] is True
    assert item["percentile_band"] is None      # never exposed when suppressed
    assert "data needed" in item["label_text"]

@pytest.mark.asyncio
async def test_employee_benchmark_published_above_k_min():
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "cohort_key":      "senior-engineer|fintech|bengaluru|5-8y",
        "percentile_band": "P60-P75",
        "cohort_size":     75,        # above K_MIN
        "suppressed":      False,
        "label_text":      "Your comp is in the top 25%",
        "computed_at":     __import__('datetime').datetime(2026, 1, 1),
    }[k]
    db = _make_db(fetch=[row])
    svc = _make_svc(db)
    result = await svc.get_employee_benchmark("emp-1")
    item = result["items"][0]
    assert item["suppressed"] is False
    assert item["percentile_band"] == "P60-P75"


# ── k-anonymity: market median ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_market_median_suppressed_below_k_min():
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "p25": 1500000, "p50": 2000000, "p75": 2800000, "sample_count": 20,
        "computed_at": __import__('datetime').datetime(2026, 1, 1),
    }[k]
    db = _make_db(fetchrow=row)
    svc = _make_svc(db)
    result = await svc.get_market_median("Senior Engineer", "Engineering")
    assert result["suppressed"] is True
    assert result["reason"] == "BELOW_K_MIN"

@pytest.mark.asyncio
async def test_market_median_published_above_k_min():
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "p25": 1500000, "p50": 2000000, "p75": 2800000, "sample_count": 60,
        "computed_at": __import__('datetime').datetime(2026, 1, 1),
    }[k]
    db = _make_db(fetchrow=row)
    svc = _make_svc(db)
    result = await svc.get_market_median("Senior Engineer", "Engineering")
    assert result["suppressed"] is False
    assert result["p50"] == 2000000

@pytest.mark.asyncio
async def test_market_median_no_data():
    db = _make_db(fetchrow=None)
    svc = _make_svc(db)
    result = await svc.get_market_median("VP Engineering", "Engineering")
    assert result["suppressed"] is True
    assert result["reason"] == "NO_DATA"


# ── CHRO bands ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chro_bands_suppressed_excluded_from_p_values():
    suppressed_row = MagicMock()
    suppressed_row.__getitem__ = lambda self, k: {
        "grade": "L3", "department": "Engineering", "period": "2025-Q4",
        "sample_count": 10, "suppressed": True,
        "p25": 1000000, "p50": 1500000, "p75": 2000000,
        "computed_at": __import__('datetime').datetime(2026, 1, 1),
    }[k]
    db = _make_db(fetch=[suppressed_row], fetchval=1)
    svc = _make_svc(db)
    result = await svc.get_chro_comp_bands("tenant-1")
    item = result["items"][0]
    assert item["suppressed"] is True
    # p values must be None when suppressed — never leak cohort data
    assert item["p25"] is None
    assert item["p50"] is None
    assert item["p75"] is None


# ── Helpers ───────────────────────────────────────────────────────────────────

def test_cohort_key_normalisation():
    key = _cohort_key("Senior Engineer", "Fin Tech", "Bengaluru", "5-8y")
    assert key == "senior-engineer|fin-tech|bengaluru|5-8y"

def test_experience_bands():
    assert _experience_band(1)  == "0-2y"
    assert _experience_band(3)  == "2-5y"
    assert _experience_band(6)  == "5-8y"
    assert _experience_band(10) == "8-12y"
    assert _experience_band(15) == "12y+"


# ── Router auth gates ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_router_consent_requires_auth(client):
    response = await client.post("/v1/benchmarking/consent", json={"grant": True})
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_router_bands_requires_chro_role(client):
    response = await client.get("/v1/benchmarking/org/bands")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_router_my_position_requires_employee_role(client):
    response = await client.get("/v1/benchmarking/my-position")
    assert response.status_code == 401


AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


@pytest.mark.asyncio
async def test_router_my_position_works_with_real_employee_token(client, mock_db):
    """Regression guard: same broken `from auth_utils import decode_jwt` bug as
    routers/alumni.py (see that file's comment) — every request with a real
    Bearer token 500'd; only the no-token 401 path was ever tested. Fixed
    2026-08-10 alongside alumni.py.
    """
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "emp-uuid-001", "user_type": "employee", "role": None,
        "tenant_id": None, "jti": "emp-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)
    mock_db.fetchrow.return_value = None
    response = await client.get("/v1/benchmarking/my-position", headers=AUTH_HEADER)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_router_bands_works_with_real_chro_token(client, mock_db):
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "oa-uuid-chro-001", "user_type": "oa_user", "role": "chro",
        "tenant_id": "tenant-001", "jti": "chro-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)
    mock_db.fetch.return_value = []
    response = await client.get("/v1/benchmarking/org/bands", headers=AUTH_HEADER)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_router_bands_works_with_real_cfo_token(client, mock_db):
    """CFO is also allowed per the module docstring — role gate must include it,
    not just CHRO/OA-Admin."""
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "oa-uuid-cfo-001", "user_type": "oa_user", "role": "cfo",
        "tenant_id": "tenant-001", "jti": "cfo-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)
    mock_db.fetch.return_value = []
    response = await client.get("/v1/benchmarking/org/bands", headers=AUTH_HEADER)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_router_bands_rejects_non_chro_cfo_oa_role(client, mock_db):
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "oa-uuid-002", "user_type": "oa_user", "role": "oa_operator",
        "tenant_id": "tenant-001", "jti": "op-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)
    response = await client.get("/v1/benchmarking/org/bands", headers=AUTH_HEADER)
    assert response.status_code == 403
