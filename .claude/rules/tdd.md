# PRANA TDD Rules
# Auto-loaded always — TDD is mandatory for all services
# ENFORCEMENT: scripts/enforce_rules.py — TDD-01 (no test file = blocks merge), TDD-02 (empty test file = warn)
# Run /enforce before any PR merge. TDD-01 violations block deployment.

## The cycle. Non-negotiable. Strictly in this order.

```
RED   → Write a failing test. Run it. Watch it fail for the RIGHT reason.
GREEN → Write the MINIMUM code to make it pass. Nothing more.
REFACTOR → Clean up. Tests must still pass.
```

**Never write code first. If you write the implementation before the test, you have already violated TDD.**

## Enforcement in enforce_rules.py

| Rule | Trigger | Severity |
|------|---------|---------|
| TDD-01 | Source file exists without `tests/test_{name}*.py` | ERROR — blocks merge |
| TDD-02 | Test file has no `def test_*()` function | WARN |

TDD-01 is ERROR. A router, service, or workflow with no test file cannot be merged.

## Test file naming convention

| Source file | Required test file |
|-------------|-------------------|
| `routers/vault.py` | `tests/test_vault.py` |
| `services/vault_service.py` | `tests/test_vault_service.py` |
| `workflows/elevation.py` | `tests/test_elevation.py` |
| `pipeline/stage04_extract.py` | `tests/test_stage04_extract.py` |
| `ask_service.py` | `tests/test_ask_service.py` |

`tests/test_{stem}*.py` glob is accepted — `test_ingest_kafka_contract.py` satisfies `ingest.py`.

## Files exempt from TDD-01

These are infrastructure/config, not logic:
`__init__.py`, `config.py`, `main.py`, `db.py`, `versioning.py`, `worker.py`, `llm_client.py`
Directories: `middleware/`, `kafka/`, `scripts/`, `migrations/`, `seeds/`, `prompts/`, `schemas/`

## Test structure — prana-api

Use fixtures from `conftest.py`:
- `client` — ASGI test client (mocked DB, Redis, Kafka, S3, KMS)
- `mock_db` — AsyncMock for asyncpg pool
- `mock_redis` — AsyncMock for Redis
- `mock_kafka` — AsyncMock for Kafka producer

```python
# Correct RED test — fails for the right reason
@pytest.mark.asyncio
async def test_vault_list_documents_requires_auth(client):
    response = await client.get("/v1/vault/documents")
    assert response.status_code == 401  # FAILS: endpoint may not exist yet

# Then implement the endpoint → watch it go GREEN
```

## Stub files (existing pre-TDD code)

All source files that predate TDD enforcement have stub test files with:
```python
@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_something():
    raise NotImplementedError
```

`strict=True` means: if the stub accidentally passes → pytest ERRORS. This forces the developer to:
1. Replace `raise NotImplementedError` with a REAL failing test
2. Implement the feature
3. Watch it go GREEN
4. Remove the `xfail` mark

**When you touch a file covered by a stub, you must replace its stubs with real tests in the same PR.**

## Mandatory tests for every new endpoint

Every new API endpoint MUST have:

1. **Auth test** — unauthenticated request returns 401/403
2. **Role test** — wrong role returns 403
3. **Tenant isolation test** — cannot access another tenant's data
4. **Happy path test** — correct input returns expected shape
5. **Privacy test** (if touches documents/PAN) — response contains no raw salary or PAN field

## Mandatory tests for every new service method

1. **Unit test** — mock all I/O, test pure logic
2. **Privacy test** (if produces output with financial data) — output contains no raw ₹ figures
3. **Config test** (if uses durations/TTLs) — value comes from config, not hardcoded

## What a REAL failing test looks like vs a bad stub

```python
# BAD — trivially fails but tests nothing
def test_vault():
    raise NotImplementedError  # not a real RED test

# GOOD — fails because the feature doesn't exist yet, but tests the real contract
async def test_vault_document_is_watermarked(client, mock_db):
    mock_db.fetchrow.return_value = {"document_id": "doc-1", "tenant_id": "t-1", ...}
    response = await client.get("/v1/vault/documents/doc-1/bytes", headers=auth_headers)
    assert "X-Watermark" in response.headers  # RED: endpoint doesn't watermark yet
```

## Running tests

```bash
# prana-api
cd prana-api && pytest tests/ -v

# prana-ai
cd prana-ai && pytest tests/ -v

# prana-ask
cd prana-ask && pytest tests/ -v

# All — must all pass before merge
pytest prana-api/tests/ prana-ai/tests/ prana-ask/tests/ -v
```

xfail stubs show as `x` (expected failure) — acceptable.
xpass stubs show as `X` (unexpected pass, strict=True) — ERROR, must fix immediately.
Any `FAILED` test → blocks merge.
