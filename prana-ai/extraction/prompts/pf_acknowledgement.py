SYSTEM = """You are a document extraction engine for Indian HR documents.
Extract ONLY the fields listed below from the provided PF acknowledgement / UAN passbook / EPFO document.
Return a valid JSON object only — no prose, no markdown, no explanation.
For each field, return a confidence score 0.0–1.0.
If a field is not present, return null with confidence 0.0."""

def build_user_prompt(redacted_text: str) -> str:
    return f"""DOCUMENT TYPE: PF Acknowledgement / EPFO Document
DOCUMENT TEXT:
{redacted_text}

EXTRACT THESE FIELDS:
employee_name     — Member / employee full name
uan_number        — Universal Account Number (12-digit)
pf_number         — PF account number
pan_number        — PAN card number — will be [NIK_REDACTED] if already tokenised
employer_name     — Establishment / employer name
establishment_id  — EPFO establishment ID (e.g. MH/BAN/12345/678)
member_id         — Member ID under the establishment
date_of_joining   — Date of joining the establishment (YYYY-MM-DD)
date_of_exit      — Date of exit (YYYY-MM-DD) if stated
acknowledgement_date — Date of the acknowledgement (YYYY-MM-DD)

RETURN FORMAT (JSON only):
{{
  "employee_name":        {{"value": null, "confidence": 0.0}},
  "uan_number":           {{"value": null, "confidence": 0.0}},
  "pf_number":            {{"value": null, "confidence": 0.0}},
  "pan_number":           {{"value": null, "confidence": 0.0}},
  "employer_name":        {{"value": null, "confidence": 0.0}},
  "establishment_id":     {{"value": null, "confidence": 0.0}},
  "member_id":            {{"value": null, "confidence": 0.0}},
  "date_of_joining":      {{"value": null, "confidence": 0.0}},
  "date_of_exit":         {{"value": null, "confidence": 0.0}},
  "acknowledgement_date": {{"value": null, "confidence": 0.0}},
  "overall_confidence": 0.0
}}"""
