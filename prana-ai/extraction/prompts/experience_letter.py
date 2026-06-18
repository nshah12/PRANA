SYSTEM = """You are a document extraction engine for Indian HR documents.
Extract ONLY the fields listed below from the provided experience letter.
Return a valid JSON object only — no prose, no markdown, no explanation.
For each field, return a confidence score 0.0–1.0.
If a field is not present, return null with confidence 0.0."""

def build_user_prompt(redacted_text: str) -> str:
    return f"""DOCUMENT TYPE: Experience Letter
DOCUMENT TEXT:
{redacted_text}

EXTRACT THESE FIELDS:
employee_name        — Employee full name
designation          — Designation / role held
department           — Department (if mentioned)
employer_name        — Issuing company name
date_of_joining      — Date of joining (YYYY-MM-DD)
last_working_day     — Last working day (YYYY-MM-DD)
letter_date          — Date the letter was issued (YYYY-MM-DD)
total_experience     — Total duration stated (e.g. "3 years 4 months")
conduct_remark       — Conduct / performance remark if stated

RETURN FORMAT (JSON only):
{{
  "employee_name":    {{"value": null, "confidence": 0.0}},
  "designation":      {{"value": null, "confidence": 0.0}},
  "department":       {{"value": null, "confidence": 0.0}},
  "employer_name":    {{"value": null, "confidence": 0.0}},
  "date_of_joining":  {{"value": null, "confidence": 0.0}},
  "last_working_day": {{"value": null, "confidence": 0.0}},
  "letter_date":      {{"value": null, "confidence": 0.0}},
  "total_experience": {{"value": null, "confidence": 0.0}},
  "conduct_remark":   {{"value": null, "confidence": 0.0}},
  "overall_confidence": 0.0
}}"""
