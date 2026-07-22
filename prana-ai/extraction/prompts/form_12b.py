SYSTEM = """You are a document extraction engine for Indian HR documents.
Extract ONLY the fields listed below from the provided Form 12B (Income Tax Rule 26A).
Return a valid JSON object only — no prose, no markdown, no explanation.
For each field, return a confidence score 0.0–1.0.
If a field is not present, return null with confidence 0.0.
NOTE: Form 12B is submitted by an employee to a new employer to declare income from previous employer."""

def build_user_prompt(redacted_text: str) -> str:
    return f"""DOCUMENT TYPE: Form 12B (Income Tax Rule 26A - India)
DOCUMENT TEXT:
{redacted_text}

EXTRACT THESE FIELDS:
employee_name            — Employee full name
pan_number               — Employee PAN (format: AAAAA9999A) — will be [NIK_REDACTED] if tokenised
financial_year           — Financial year (e.g. 2024-25)
previous_employer_name   — Name of previous employer
previous_employer_tan    — TAN of previous employer (format: AAAAA9999A)
date_of_joining_prev     — Date of joining previous employer
date_of_leaving_prev     — Date of leaving previous employer
tds_deducted             — Total TDS deducted by previous employer (numeric, INR)
period_of_employment     — Employment period at previous employer (months or date range)

RETURN FORMAT (JSON only):
{{
  "employee_name":          {{"value": null, "confidence": 0.0}},
  "pan_number":             {{"value": null, "confidence": 0.0}},
  "financial_year":         {{"value": null, "confidence": 0.0}},
  "previous_employer_name": {{"value": null, "confidence": 0.0}},
  "previous_employer_tan":  {{"value": null, "confidence": 0.0}},
  "date_of_joining_prev":   {{"value": null, "confidence": 0.0}},
  "date_of_leaving_prev":   {{"value": null, "confidence": 0.0}},
  "tds_deducted":           {{"value": null, "confidence": 0.0}},
  "period_of_employment":   {{"value": null, "confidence": 0.0}},
  "overall_confidence": 0.0
}}"""
