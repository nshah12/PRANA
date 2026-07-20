SYSTEM = """You are a document extraction engine for Indian HR documents.
Extract ONLY the fields listed below from the provided Gratuity Letter (Payment of Gratuity Act 1972).
Return a valid JSON object only — no prose, no markdown, no explanation.
For each field, return a confidence score 0.0–1.0.
If a field is not present, return null with confidence 0.0.
IMPORTANT: Do NOT extract the gratuity amount in rupees. Extract eligibility and tenure only."""

def build_user_prompt(redacted_text: str) -> str:
    return f"""DOCUMENT TYPE: Gratuity Letter (Payment of Gratuity Act 1972 - India)
DOCUMENT TEXT:
{redacted_text}

EXTRACT THESE FIELDS:
employee_name       — Employee full name
employee_id         — Employee ID / staff number (if present)
employer_name       — Company / employer name
date_of_joining     — Date of joining the organisation (ISO 8601 or as written)
date_of_exit        — Date of resignation / retirement / termination (ISO 8601 or as written)
years_of_service    — Total years of service (numeric, decimal allowed e.g. 5.5)
reason_for_exit     — RESIGNATION | RETIREMENT | TERMINATION | DEATH | DISABLEMENT
gratuity_eligible   — Whether employee is eligible for gratuity: true | false
acknowledgement_no  — Acknowledgement or reference number on the letter (if present)

RETURN FORMAT (JSON only):
{{
  "employee_name":      {{"value": null, "confidence": 0.0}},
  "employee_id":        {{"value": null, "confidence": 0.0}},
  "employer_name":      {{"value": null, "confidence": 0.0}},
  "date_of_joining":    {{"value": null, "confidence": 0.0}},
  "date_of_exit":       {{"value": null, "confidence": 0.0}},
  "years_of_service":   {{"value": null, "confidence": 0.0}},
  "reason_for_exit":    {{"value": null, "confidence": 0.0}},
  "gratuity_eligible":  {{"value": null, "confidence": 0.0}},
  "acknowledgement_no": {{"value": null, "confidence": 0.0}},
  "overall_confidence": 0.0
}}"""
