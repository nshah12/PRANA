SYSTEM = """You are a document extraction engine for Indian HR documents.
Extract ONLY the fields listed below from the provided salary slip.
Return a valid JSON object only — no prose, no markdown, no explanation.
For each field, return a confidence score 0.0–1.0.
If a field is not present in the document, return null with confidence 0.0.
Do not invent or guess field values."""

def build_user_prompt(redacted_text: str) -> str:
    return f"""DOCUMENT TYPE: Salary Slip
DOCUMENT TEXT:
{redacted_text}

EXTRACT THESE FIELDS:
employee_id       — Employee code / staff ID (e.g. NPCI001, EMP-1234)
employee_name     — Full name as printed on the document
designation       — Job title / role
department        — Department or cost centre
location          — Office city / branch
gross_ctc         — Gross CTC or total cost to company (numeric, INR, no commas)
basic_salary      — Basic salary component (numeric, INR)
hra               — House Rent Allowance (numeric, INR)
pf_employee       — Employee PF deduction (numeric, INR)
tds_amount        — TDS deducted this month (numeric, INR)
net_pay           — Net take-home amount (numeric, INR)
pf_number         — PF account number (format: XX/XXX/XXXXXX/XXX/XXXXXXX)
uan_number        — Universal Account Number (12-digit)
pan_number        — PAN card number (format: AAAAA9999A) — will be [NIK_REDACTED] if already tokenised
pay_period_month  — Month of this payslip (e.g. March)
pay_period_year   — Year of this payslip (e.g. 2024)
employer_name     — Company / employer name as printed

RETURN FORMAT (JSON only, no other text):
{{
  "employee_id":      {{"value": null, "confidence": 0.0}},
  "employee_name":    {{"value": null, "confidence": 0.0}},
  "designation":      {{"value": null, "confidence": 0.0}},
  "department":       {{"value": null, "confidence": 0.0}},
  "location":         {{"value": null, "confidence": 0.0}},
  "gross_ctc":        {{"value": null, "confidence": 0.0}},
  "basic_salary":     {{"value": null, "confidence": 0.0}},
  "hra":              {{"value": null, "confidence": 0.0}},
  "pf_employee":      {{"value": null, "confidence": 0.0}},
  "tds_amount":       {{"value": null, "confidence": 0.0}},
  "net_pay":          {{"value": null, "confidence": 0.0}},
  "pf_number":        {{"value": null, "confidence": 0.0}},
  "uan_number":       {{"value": null, "confidence": 0.0}},
  "pan_number":       {{"value": null, "confidence": 0.0}},
  "pay_period_month": {{"value": null, "confidence": 0.0}},
  "pay_period_year":  {{"value": null, "confidence": 0.0}},
  "employer_name":    {{"value": null, "confidence": 0.0}},
  "overall_confidence": 0.0
}}"""
