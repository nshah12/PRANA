SYSTEM = """You are a document extraction engine for Indian HR documents.
Extract ONLY the fields listed below from the provided Bonus Letter (Payment of Bonus Act 1965).
Return a valid JSON object only — no prose, no markdown, no explanation.
For each field, return a confidence score 0.0–1.0.
If a field is not present, return null with confidence 0.0.
IMPORTANT: Do NOT extract the bonus amount in rupees. Extract bonus_percentage only."""

def build_user_prompt(redacted_text: str) -> str:
    return f"""DOCUMENT TYPE: Bonus Letter (Payment of Bonus Act 1965 - India)
DOCUMENT TEXT:
{redacted_text}

EXTRACT THESE FIELDS:
employee_name     — Employee full name
employee_id       — Employee ID / staff number (if present)
employer_name     — Company / employer name
financial_year    — Financial year the bonus relates to (e.g. 2023-24)
bonus_type        — Type of bonus: STATUTORY | EX_GRATIA | PERFORMANCE | FESTIVAL
bonus_percentage  — Bonus as percentage of salary (numeric, do NOT extract rupee amount)
payment_date      — Date of bonus payment or expected payment date (ISO 8601 or as written)
eligible_months   — Number of months of service that qualify (integer)

RETURN FORMAT (JSON only):
{{
  "employee_name":    {{"value": null, "confidence": 0.0}},
  "employee_id":      {{"value": null, "confidence": 0.0}},
  "employer_name":    {{"value": null, "confidence": 0.0}},
  "financial_year":   {{"value": null, "confidence": 0.0}},
  "bonus_type":       {{"value": null, "confidence": 0.0}},
  "bonus_percentage": {{"value": null, "confidence": 0.0}},
  "payment_date":     {{"value": null, "confidence": 0.0}},
  "eligible_months":  {{"value": null, "confidence": 0.0}},
  "overall_confidence": 0.0
}}"""
