"""Tests for services/immudb_service.py — tamper-evident audit ledger wrapper."""
import json
from unittest.mock import MagicMock, patch

import pytest


def _make_service(mock_client):
    from services.immudb_service import ImmudbService
    svc = ImmudbService.__new__(ImmudbService)
    svc._client = mock_client
    svc._database = "prana_audit"
    return svc


# ── construction / connection ────────────────────────────────────────────────

def test_init_connects_to_configured_host_and_port_and_logs_in():
    with patch("services.immudb_service.ImmudbClient") as MockClient:
        mock_client = MockClient.return_value
        from services.immudb_service import ImmudbService
        ImmudbService(host="immudb", port=3322, user="immudb", password="immudb", database="prana_audit")

        MockClient.assert_called_once_with("immudb:3322")
        mock_client.login.assert_called_once_with("immudb", "immudb", database=b"prana_audit")


def test_init_creates_database_on_first_boot_when_login_fails():
    """First boot: target database doesn't exist yet on a fresh immudb instance."""
    with patch("services.immudb_service.ImmudbClient") as MockClient:
        mock_client = MockClient.return_value
        mock_client.login.side_effect = [Exception("database does not exist"), None, None]
        from services.immudb_service import ImmudbService
        ImmudbService(host="immudb", port=3322, user="immudb", password="immudb", database="prana_audit")

        mock_client.createDatabase.assert_called_once_with(b"prana_audit")
        assert mock_client.login.call_count == 3


# ── verified_set ──────────────────────────────────────────────────────────────

def test_verified_set_writes_json_serialized_value_under_key():
    mock_client = MagicMock()
    mock_client.verifiedSet.return_value = MagicMock(id=42, verified=True)
    svc = _make_service(mock_client)

    result = svc.verified_set("audit:event-1", {"event_type": "DOC_ACCESSED", "tenant_id": "t-1"})

    args, _ = mock_client.verifiedSet.call_args
    key_bytes, value_bytes = args
    assert key_bytes == b"audit:event-1"
    assert json.loads(value_bytes) == {"event_type": "DOC_ACCESSED", "tenant_id": "t-1"}
    assert result == {"id": 42, "verified": True}


def test_verified_set_propagates_real_exceptions_never_degrades_silently():
    """If the Immudb write fails, the exception must propagate — no silent placeholder."""
    mock_client = MagicMock()
    mock_client.verifiedSet.side_effect = RuntimeError("immudb unreachable")
    svc = _make_service(mock_client)

    with pytest.raises(RuntimeError, match="immudb unreachable"):
        svc.verified_set("audit:event-2", {"event_type": "DOC_ROUTED"})


# ── verified_get ──────────────────────────────────────────────────────────────

def test_verified_get_returns_verified_value():
    mock_client = MagicMock()
    mock_client.verifiedGet.return_value = MagicMock(
        id=42, value=json.dumps({"event_type": "DOC_ACCESSED"}).encode(), verified=True,
    )
    svc = _make_service(mock_client)

    result = svc.verified_get("audit:event-1")

    mock_client.verifiedGet.assert_called_once_with(b"audit:event-1")
    assert result == {"value": {"event_type": "DOC_ACCESSED"}, "tx": 42, "verified": True}


def test_verified_get_returns_none_for_missing_key():
    mock_client = MagicMock()
    not_found = Exception("rpc error")
    not_found.details = lambda: "key not found"
    mock_client.verifiedGet.side_effect = not_found
    svc = _make_service(mock_client)

    assert svc.verified_get("audit:nonexistent") is None


def test_verified_get_propagates_non_not_found_errors():
    mock_client = MagicMock()
    mock_client.verifiedGet.side_effect = RuntimeError("immudb unreachable")
    svc = _make_service(mock_client)

    with pytest.raises(RuntimeError, match="immudb unreachable"):
        svc.verified_get("audit:event-1")


# ── close ─────────────────────────────────────────────────────────────────────

def test_close_logs_out_and_shuts_down_channel():
    mock_client = MagicMock()
    svc = _make_service(mock_client)

    svc.close()

    mock_client.logout.assert_called_once()
    mock_client.shutdown.assert_called_once()


def test_close_shuts_down_even_if_logout_fails():
    """Shutdown must still happen if logout errors (e.g. session already expired)."""
    mock_client = MagicMock()
    mock_client.logout.side_effect = RuntimeError("already logged out")
    svc = _make_service(mock_client)

    svc.close()

    mock_client.shutdown.assert_called_once()
