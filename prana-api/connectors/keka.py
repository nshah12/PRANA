"""
Keka HR connector adapter.

Auth: API key in Authorization header (Bearer {api_key}).
Pull: GET /employees?updatedAfter={cursor}&limit=200
Webhook: POST with eventType + employeeId + payload.

Privacy: strip_salary_fields() called before any record leaves this module.
Keka nests fields (e.g. department.name) — _extract_nested handles dot notation.
"""
from __future__ import annotations

import logging

import httpx

from connectors.base import BaseHRMSConnector, strip_salary_fields

log = logging.getLogger(__name__)

_KEKA_CANONICAL_MAP = {
    "employee_id":   "employeeNumber",
    "first_name":    "firstName",
    "last_name":     "lastName",
    "date_of_join":  "joiningDate",
    "department":    "department.name",
    "designation":   "jobTitle",
    "location":      "workLocation.name",
    "manager_id":    "reportsTo.employeeNumber",
    "status":        "employmentStatus",
}

_KEKA_WEBHOOK_EVENT_MAP = {
    "employee.created":    "EMPLOYEE_CREATED",
    "employee.updated":    "EMPLOYEE_UPDATED",
    "employee.terminated": "EMPLOYEE_OFFBOARDED",
    "employee.resigned":   "EMPLOYEE_OFFBOARDED",
}


class KekaConnector(BaseHRMSConnector):

    def _canonical_map(self) -> dict[str, str]:
        return _KEKA_CANONICAL_MAP

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._creds.get('api_key', '')}"}

    async def pull(self, cursor: str | None) -> dict:
        """Pull employee records from Keka, optionally delta since cursor."""
        base_url = self._creds.get("base_url", "").rstrip("/")

        params: dict = {"limit": 200}
        if cursor:
            params["updatedAfter"] = cursor

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{base_url}/v1/employees",
                params=params,
                headers=self._auth_headers(),
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
            "next_cursor": data.get("nextCursor"),
        }

    async def test_connection(self) -> bool:
        """Test Keka API key by calling /v1/employees?limit=1."""
        try:
            base_url = self._creds.get("base_url", "").rstrip("/")
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{base_url}/v1/employees",
                    params={"limit": 1},
                    headers=self._auth_headers(),
                )
                resp.raise_for_status()
            return True
        except Exception as exc:
            log.warning("Keka connection test failed: %s", exc)
            return False

    def handle_webhook(self, payload: dict) -> list[dict]:
        """Parse Keka webhook payload into canonical events."""
        raw_type = payload.get("eventType", "employee.updated").lower()
        event_type = _KEKA_WEBHOOK_EVENT_MAP.get(raw_type, "EMPLOYEE_UPDATED")
        fields = strip_salary_fields(payload.get("payload", {}))
        return [{
            "event_type":  event_type,
            "employee_id": str(payload.get("employeeId", "")),
            "changed_at":  payload.get("timestamp", ""),
            "fields":      fields,
        }]
