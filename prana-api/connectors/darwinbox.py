"""
Darwinbox HRMS connector adapter.

Auth: OAuth2 client_credentials flow.
Pull: GET /employees?updated_after={cursor}&page_size=200
Webhook: POST events with event + employee_id + changed_at payload.

Privacy: strip_salary_fields() is called before any record leaves this module.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from connectors.base import BaseHRMSConnector, strip_salary_fields

log = logging.getLogger(__name__)

# Default Darwinbox field → canonical field mapping
_DARWINBOX_CANONICAL_MAP = {
    "employee_id":   "employee_id",
    "first_name":    "first_name",
    "last_name":     "last_name",
    "date_of_join":  "date_of_joining",
    "department":    "department",
    "designation":   "designation",
    "location":      "work_location",
    "manager_id":    "reporting_manager_id",
    "status":        "employment_status",
}

_WEBHOOK_EVENT_MAP = {
    "EMPLOYEE_UPDATED":    "EMPLOYEE_UPDATED",
    "EMPLOYEE_CREATED":    "EMPLOYEE_CREATED",
    "EMPLOYEE_OFFBOARDED": "EMPLOYEE_OFFBOARDED",
    "EMPLOYEE_RESIGNED":   "EMPLOYEE_OFFBOARDED",
}


class DarwinboxConnector(BaseHRMSConnector):

    def _canonical_map(self) -> dict[str, str]:
        return _DARWINBOX_CANONICAL_MAP

    async def pull(self, cursor: str | None) -> dict:
        """Pull employee records from Darwinbox, optionally delta since cursor."""
        base_url = self._creds.get("base_url", "").rstrip("/")
        token    = await self._get_access_token()

        params: dict[str, Any] = {"page_size": 200}
        if cursor:
            params["updated_after"] = cursor

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{base_url}/v1/employees",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        raw_records = data.get("data", [])
        records = []
        for raw in raw_records:
            canonical = self._apply_field_mapping(raw)
            canonical = strip_salary_fields(canonical)
            records.append(canonical)

        return {
            "records":     records,
            "next_cursor": data.get("next_cursor"),
        }

    async def test_connection(self) -> bool:
        """Test Darwinbox credentials by fetching a token and hitting /v1/employees?page_size=1."""
        try:
            base_url = self._creds.get("base_url", "").rstrip("/")
            token    = await self._get_access_token()
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{base_url}/v1/employees",
                    params={"page_size": 1},
                    headers={"Authorization": f"Bearer {token}"},
                )
                resp.raise_for_status()
            return True
        except Exception as exc:
            log.warning("Darwinbox connection test failed: %s", exc)
            return False

    def handle_webhook(self, payload: dict) -> list[dict]:
        """Parse Darwinbox webhook payload into canonical events."""
        event_type = _WEBHOOK_EVENT_MAP.get(
            payload.get("event", "").upper(), "EMPLOYEE_UPDATED"
        )
        return [{
            "event_type":  event_type,
            "employee_id": str(payload.get("employee_id", "")),
            "changed_at":  payload.get("changed_at", ""),
            "fields":      strip_salary_fields(payload.get("fields", {})),
        }]

    async def _get_access_token(self) -> str:
        """Obtain OAuth2 access token via client_credentials grant."""
        base_url      = self._creds.get("base_url", "").rstrip("/")
        client_id     = self._creds.get("client_id", "")
        client_secret = self._creds.get("client_secret", "")

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{base_url}/oauth2/token",
                data={
                    "grant_type":    "client_credentials",
                    "client_id":     client_id,
                    "client_secret": client_secret,
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]
