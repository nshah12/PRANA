SYSTEM = """You are a document extraction engine for Indian HR documents.
Extract ONLY the fields listed below from the provided joining letter / joining report.
Return a valid JSON object only — no prose, no markdown, no explanation.
For each field, return a confidence score 0.0–1.0.
If a field is not present, return null with confidence 0.0."""

def build_user_prompt(redacted_text: str) -> str:
    return f"""DOCUMENT TYPE: Joining Letter / Joining Report
DOCUMENT TEXT:
{redacted_text}

EXTRACT THESE FIELDS:
employee_name     — Employee full name
employee_id       — Employee code / ID assigned at joining
designation       — Designation joined as
department        — Department
location          — Office location
employer_name     — Company name
date_of_joining   — Actual date of joining (YYYY-MM-DD)
letter_date       — Date the letter was issued (YYYY-MM-DD)
reporting_manager — Reporting manager name (if stated)

RETURN FORMAT (JSON only):
{{
  "employee_name":    {{"value": null, "confidence": 0.0}},
  "employee_id":      {{"value": null, "confidence": 0.0}},
  "designation":      {{"value": null, "confidence": 0.0}},
  "department":       {{"value": null, "confidence": 0.0}},
  "location":         {{"value": null, "confidence": 0.0}},
  "employer_name":    {{"value": null, "confidence": 0.0}},
  "date_of_joining":  {{"value": null, "confidence": 0.0}},
  "letter_date":      {{"value": null, "confidence": 0.0}},
  "reporting_manager":{{"value": null, "confidence": 0.0}},
  "overall_confidence": 0.0
}}"""
