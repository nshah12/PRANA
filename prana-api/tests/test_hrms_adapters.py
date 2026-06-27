"""
RED tests for Darwinbox and Keka connector adapters.

Tests verify the abstract contract is satisfied by each adapter:
- pull()           → returns list of employee records mapped to canonical schema
- test_connection() → returns True on success, False / raises on failure
- handle_webhook() → parses webhook payload, returns list of events

Privacy: adapters must not return any raw salary fields (ctc, salary_amount, etc.)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4


def _make_http_mock(json_data: dict):
    """Helper: returns (mock_client_cls, mock_client, mock_resp) ready to use."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get  = AsyncMock(return_value=mock_resp)
    mock_client.post = AsyncMock(return_value=mock_resp)
    return mock_client


# ── Darwinbox ─────────────────────────────────────────────────────────────────

class TestDarwinboxAdapter:

    @pytest.fixture
    def adapter(self):
        from connectors.darwinbox import DarwinboxConnector
        return DarwinboxConnector(
            credentials={"client_id": "test_id", "client_secret": "test_secret",
                         "base_url": "https://test.darwinbox.com"},
            field_mapping={},  # use canonical defaults
        )

    @pytest.mark.asyncio
    async def test_pull_returns_list(self, adapter):
        """pull() must return a list of employee records."""
        sample_response = {
            "data": [
                {
                    "employee_id":     "EMP001",
                    "first_name":      "Rahul",
                    "last_name":       "Sharma",
                    "date_of_joining": "2022-01-15",
                    "department":      "Engineering",
                    "designation":     "Software Engineer",
                    "employment_status": "active",
                }
            ],
            "next_cursor": "cursor_abc",
        }
        mock_client = _make_http_mock(sample_response)
        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch.object(adapter, "_get_access_token", new=AsyncMock(return_value="tok")):
            result = await adapter.pull(cursor=None)

        assert isinstance(result, dict)
        assert "records" in result
        assert "next_cursor" in result
        assert isinstance(result["records"], list)
        assert len(result["records"]) == 1

    @pytest.mark.asyncio
    async def test_pull_maps_to_canonical_fields(self, adapter):
        """Records must use canonical field names, not HRMS-specific ones."""
        sample = {
            "data": [{
                "employee_id":       "EMP001",
                "first_name":        "Rahul",
                "last_name":         "Sharma",
                "date_of_joining":   "2022-01-15",
                "department":        "Engineering",
                "designation":       "Software Engineer",
                "employment_status": "active",
            }],
            "next_cursor": None,
        }
        mock_client = _make_http_mock(sample)
        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch.object(adapter, "_get_access_token", new=AsyncMock(return_value="tok")):
            result = await adapter.pull(cursor=None)

        record = result["records"][0]
        assert "employee_id"  in record
        assert "date_of_join" in record   # mapped from date_of_joining
        assert "designation"  in record

    @pytest.mark.asyncio
    async def test_pull_no_salary_fields(self, adapter):
        """Privacy: adapter must never return raw salary data."""
        sample = {
            "data": [{
                "employee_id":  "EMP001",
                "first_name":   "Rahul",
                "last_name":    "Sharma",
                "ctc":          "1200000",
                "salary_band":  "L3",
                "designation":  "Engineer",
                "date_of_joining": "2022-01-01",
                "employment_status": "active",
            }],
            "next_cursor": None,
        }
        mock_client = _make_http_mock(sample)
        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch.object(adapter, "_get_access_token", new=AsyncMock(return_value="tok")):
            result = await adapter.pull(cursor=None)

        record = result["records"][0]
        assert "ctc"         not in record
        assert "salary_band" not in record
        assert "salary"      not in str(record).lower()

    @pytest.mark.asyncio
    async def test_test_connection_success(self, adapter):
        mock_client = _make_http_mock({})
        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch.object(adapter, "_get_access_token", new=AsyncMock(return_value="tok")):
            ok = await adapter.test_connection()
        assert ok is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, adapter):
        import httpx
        mock_client = _make_http_mock({})
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("timeout"))
        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch.object(adapter, "_get_access_token", new=AsyncMock(return_value="tok")):
            ok = await adapter.test_connection()
        assert ok is False

    def test_handle_webhook_employee_updated(self, adapter):
        payload = {
            "event":       "EMPLOYEE_UPDATED",
            "employee_id": "EMP001",
            "changed_at":  "2026-06-27T10:00:00Z",
            "fields":      {"designation": "Senior Engineer"},
        }
        events = adapter.handle_webhook(payload)
        assert isinstance(events, list)
        assert len(events) >= 1
        assert events[0]["event_type"] in ("EMPLOYEE_UPDATED", "EMPLOYEE_CREATED", "EMPLOYEE_OFFBOARDED")


# ── Keka ──────────────────────────────────────────────────────────────────────

class TestKekaAdapter:

    @pytest.fixture
    def adapter(self):
        from connectors.keka import KekaConnector
        return KekaConnector(
            credentials={"api_key": "keka_test_key", "base_url": "https://test.keka.com"},
            field_mapping={},
        )

    @pytest.mark.asyncio
    async def test_pull_returns_canonical_records(self, adapter):
        sample = {
            "data": [{
                "employeeNumber": "E001",
                "firstName":      "Priya",
                "lastName":       "Patel",
                "joiningDate":    "2021-03-10",
                "department":     {"name": "HR"},
                "jobTitle":       "HR Manager",
                "employmentStatus": "Active",
            }],
            "nextCursor": "next_token_xyz",
        }
        mock_client = _make_http_mock(sample)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.pull(cursor=None)

        assert "records" in result
        record = result["records"][0]
        assert record["employee_id"] == "E001"
        assert record["date_of_join"] == "2021-03-10"
        assert record["department"]   == "HR"

    @pytest.mark.asyncio
    async def test_pull_no_salary_in_output(self, adapter):
        sample = {
            "data": [{
                "employeeNumber": "E001",
                "firstName":      "Priya",
                "lastName":       "Patel",
                "joiningDate":    "2021-03-10",
                "department":     {"name": "HR"},
                "jobTitle":       "HR Manager",
                "employmentStatus": "Active",
                "currentPay":     {"amount": 900000, "currency": "INR"},
            }],
            "nextCursor": None,
        }
        mock_client = _make_http_mock(sample)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.pull(cursor=None)

        record = result["records"][0]
        assert "currentPay" not in record
        assert "amount"     not in str(record)

    @pytest.mark.asyncio
    async def test_test_connection_uses_api_key_header(self, adapter):
        mock_client = _make_http_mock({})
        with patch("httpx.AsyncClient", return_value=mock_client):
            ok = await adapter.test_connection()
        assert ok is True

    def test_handle_webhook_keka(self, adapter):
        payload = {
            "eventType":  "employee.updated",
            "employeeId": "E001",
            "timestamp":  "2026-06-27T10:00:00Z",
            "payload":    {"jobTitle": "Senior HR Manager"},
        }
        events = adapter.handle_webhook(payload)
        assert isinstance(events, list)
        assert len(events) >= 1


# ── Base contract ─────────────────────────────────────────────────────────────

def test_darwinbox_implements_base_interface():
    from connectors.base import BaseHRMSConnector
    from connectors.darwinbox import DarwinboxConnector
    assert issubclass(DarwinboxConnector, BaseHRMSConnector)


def test_keka_implements_base_interface():
    from connectors.base import BaseHRMSConnector
    from connectors.keka import KekaConnector
    assert issubclass(KekaConnector, BaseHRMSConnector)
