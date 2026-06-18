"""
BenchmarkService — converts raw ₹ values from extracted_fields into percentile rankings.

This is the ONLY place in the codebase that reads raw salary figures.
Output is ALWAYS percentiles / qualitative descriptors — never raw ₹.

The privacy boundary:
  extracted_fields (has ₹) → benchmark_service → career_context (percentiles only)
  career_context then flows to career_insight_service and Ask PRANA.
"""

import logging
from uuid import UUID

log = logging.getLogger(__name__)


class BenchmarkService:
    def __init__(self, db):
        self._db = db

    async def build_career_context(
        self,
        employee_uuid: UUID,
        tenant_id: UUID,
        extracted_fields: dict,
        doc_type: str,
    ) -> dict:
        """
        Convert raw extracted_fields into a privacy-safe career context dict.

        Returns percentiles, growth rates, qualitative labels — never raw ₹.
        This output is safe to pass to LLMs and surface in any UI.
        """
        context = {
            "doc_type": doc_type,
            "employer": _get(extracted_fields, "employer_name"),
            "designation": _get(extracted_fields, "designation"),
            "department": _get(extracted_fields, "department"),
            "location": _get(extracted_fields, "location"),
            "date_of_joining": _get(extracted_fields, "date_of_joining"),
            "last_working_day": _get(extracted_fields, "last_working_day"),
            "pay_period": _pay_period(extracted_fields),
        }

        # Salary benchmarking — converts raw ₹ to percentile
        gross_ctc = _numeric(extracted_fields, "gross_ctc") or _numeric(extracted_fields, "ctc_annual")
        if gross_ctc:
            context["compensation"] = await self._benchmark_salary(
                employee_uuid, tenant_id, gross_ctc,
                designation=context.get("designation"),
            )

        # Increment context — growth rate, not amounts
        ctc_old = _numeric(extracted_fields, "ctc_old")
        ctc_new = _numeric(extracted_fields, "ctc_new")
        if ctc_old and ctc_new and ctc_old > 0:
            pct = round((ctc_new - ctc_old) / ctc_old * 100, 1)
            context["increment"] = {
                "growth_percent": pct,
                "direction": "increase" if pct > 0 else "decrease",
                "reason": _get(extracted_fields, "increment_reason"),
                "effective_date": _get(extracted_fields, "effective_date"),
            }

        return context

    async def _benchmark_salary(
        self, employee_uuid: UUID, tenant_id: UUID, gross_ctc: float, designation: str | None
    ) -> dict:
        """
        Return percentile ranking — never raw ₹.

        Peer comparison uses anonymised aggregates from salary_band table.
        Individual employee records are never exposed in the comparison.
        """
        band_row = await self._db.fetchrow(
            """SELECT p25, p50, p75, p90, band_label
               FROM salary_band
               WHERE tenant_id = $1
                 AND ($2 IS NULL OR designation_pattern ILIKE '%' || $2 || '%')
               ORDER BY updated_at DESC LIMIT 1""",
            tenant_id, designation,
        )

        if not band_row:
            return {"percentile": None, "label": "market data unavailable"}

        p25, p50, p75, p90 = band_row["p25"], band_row["p50"], band_row["p75"], band_row["p90"]
        band_label = band_row["band_label"]

        if gross_ctc < p25:
            percentile, label = 20, "below market"
        elif gross_ctc < p50:
            percentile = 25 + round((gross_ctc - p25) / (p50 - p25) * 25)
            label = "at market"
        elif gross_ctc < p75:
            percentile = 50 + round((gross_ctc - p50) / (p75 - p50) * 25)
            label = "above market"
        elif gross_ctc < p90:
            percentile = 75 + round((gross_ctc - p75) / (p90 - p75) * 15)
            label = "well above market"
        else:
            percentile, label = 92, "top 10%"

        return {
            "percentile": percentile,
            "label": label,
            "band": band_label,
        }


def _get(fields: dict, key: str) -> str | None:
    return (fields.get(key) or {}).get("value")


def _numeric(fields: dict, key: str) -> float | None:
    val = _get(fields, key)
    if val is None:
        return None
    try:
        return float(str(val).replace(",", "").replace("₹", "").strip())
    except ValueError:
        return None


def _pay_period(fields: dict) -> str | None:
    month = _get(fields, "pay_period_month")
    year  = _get(fields, "pay_period_year")
    if month and year:
        return f"{month} {year}"
    return year
