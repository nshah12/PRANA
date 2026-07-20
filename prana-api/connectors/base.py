"""
BaseHRMSConnector — abstract interface every HRMS adapter must implement.

Privacy contract (hardcoded, not optional):
  - pull() and handle_webhook() strip ALL salary/compensation fields before returning.
  - Adapters return employee identity + career metadata ONLY.
  - Raw ₹ figures are stripped at the adapter layer — never reach the DB or Kafka.

Adapters are stateless — credentials are injected at construction time.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

# Fields that must NEVER appear in adapter output — financial privacy guard
_SALARY_FIELD_BLACKLIST = frozenset({
    "ctc", "salary", "salary_band", "salary_amount", "salary_grade",
    "current_pay", "currentpay", "annualctc", "annual_ctc",
    "compensation", "pay_band", "payband", "gross_salary", "net_salary",
    "lpa", "amount",   # too broad but context-safe here (compensation context)
})


def strip_salary_fields(record: dict) -> dict:
    """Remove any salary/compensation keys from a record dict (case-insensitive)."""
    return {
        k: v
        for k, v in record.items()
        if k.lower().replace("_", "").replace("-", "") not in {
            f.replace("_", "").replace("-", "") for f in _SALARY_FIELD_BLACKLIST
        }
    }


class BaseHRMSConnector(ABC):
    """
    Every HRMS connector adapter must subclass this and implement all three methods.

    Constructor args (both required):
      credentials: dict  — decrypted creds (client_id/secret, api_key, etc.)
      field_mapping: dict — tenant overrides on top of canonical schema
    """

    def __init__(self, credentials: dict, field_mapping: dict) -> None:
        self._creds       = credentials
        self._field_map   = field_mapping

    @abstractmethod
    async def pull(self, cursor: str | None) -> dict:
        """
        Pull employee records since `cursor` (ISO datetime string or None for full pull).

        Returns:
          {
            "records":     [<canonical employee dict>, ...],
            "next_cursor": "<opaque string>" | None,
          }

        Each record must use canonical field names (see canonical_field_schema in DB).
        Salary fields are stripped before returning.
        """

    @abstractmethod
    async def test_connection(self) -> bool:
        """Verify credentials are valid. Returns True on success, False otherwise."""

    @abstractmethod
    def handle_webhook(self, payload: dict) -> list[dict]:
        """
        Parse a webhook payload from the HRMS.

        Returns list of events:
          [{"event_type": "EMPLOYEE_UPDATED"|"EMPLOYEE_CREATED"|"EMPLOYEE_OFFBOARDED",
            "employee_id": str, "changed_at": str, "fields": dict}, ...]
        """

    def _apply_field_mapping(self, raw: dict) -> dict:
        """
        Map HRMS-specific field names to canonical names using field_mapping overrides.
        Falls through to the default mapping defined by the subclass.
        """
        mapped = {}
        for canonical_key, hrms_key in self._canonical_map().items():
            # Tenant override takes precedence
            override = self._field_map.get(canonical_key)
            source_key = override or hrms_key
            value = self._extract_nested(raw, source_key)
            if value is not None:
                mapped[canonical_key] = value
        return mapped

    @abstractmethod
    def _canonical_map(self) -> dict[str, str]:
        """Return the default canonical→hrms_field mapping for this connector."""

    @staticmethod
    def _extract_nested(record: dict, dotted_key: str) -> Any:
        """Extract value from nested dict using dot-notation key (e.g. 'department.name')."""
        parts = dotted_key.split(".")
        val   = record
        for part in parts:
            if not isinstance(val, dict):
                return None
            val = val.get(part)
        return val
