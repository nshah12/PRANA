SYSTEM = """You are a document extraction engine for Indian HR documents.
Extract ONLY the fields listed below from the provided Form 16 (TDS certificate).
Return a valid JSON object only — no prose, no markdown, no explanation.
For each field, return a confidence score 0.0–1.0.
If a field is not present, return null with confidence 0.0."""

def build_user_prompt(redacted_text: str) -> str:
    return f"""DOCUMENT TYPE: Form 16 (TDS Certificate - India)
DOCUMENT TEXT:
{redacted_text}

EXTRACT THESE FIELDS:
employee_name       — Employee full name
pan_number          — Employee PAN (format: AAAAA9999A) — will be [NIK_REDACTED] if tokenised
employer_name       — Employer / deductor name
employer_tan        — Employer TAN (format: AAAAA9999A)
employer_address    — Employer address
assessment_year     — Assessment year (e.g. 2024-25)
financial_year      — Financial year (e.g. 2023-24)
gross_salary        — Gross salary as per Part B (numeric, INR)
total_tds           — Total TDS deducted (numeric, INR)
net_taxable_income  — Net taxable income after deductions (numeric, INR)
section_80c         — 80C deduction amount (numeric, INR)
section_80d         — 80D deduction amount (numeric, INR)
hra_exemption       — HRA exemption claimed (numeric, INR)

RETURN FORMAT (JSON only):
{{
  "employee_name":      {{"value": null, "confidence": 0.0}},
  "pan_number":         {{"value": null, "confidence": 0.0}},
  "employer_name":      {{"value": null, "confidence": 0.0}},
  "employer_tan":       {{"value": null, "confidence": 0.0}},
  "employer_address":   {{"value": null, "confidence": 0.0}},
  "assessment_year":    {{"value": null, "confidence": 0.0}},
  "financial_year":     {{"value": null, "confidence": 0.0}},
  "gross_salary":       {{"value": null, "confidence": 0.0}},
  "total_tds":          {{"value": null, "confidence": 0.0}},
  "net_taxable_income": {{"value": null, "confidence": 0.0}},
  "section_80c":        {{"value": null, "confidence": 0.0}},
  "section_80d":        {{"value": null, "confidence": 0.0}},
  "hra_exemption":      {{"value": null, "confidence": 0.0}},
  "overall_confidence": 0.0
}}"""
