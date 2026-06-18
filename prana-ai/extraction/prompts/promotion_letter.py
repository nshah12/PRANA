SYSTEM = """You are a document extraction engine for Indian HR documents.
Extract ONLY the fields listed below from the provided promotion letter.
Return a valid JSON object only — no prose, no markdown, no explanation.
For each field, return a confidence score 0.0–1.0.
If a field is not present, return null with confidence 0.0."""

def build_user_prompt(redacted_text: str) -> str:
    return f"""DOCUMENT TYPE: Promotion Letter
DOCUMENT TEXT:
{redacted_text}

EXTRACT THESE FIELDS:
employee_name        — Employee full name
employee_id          — Employee code / ID
designation_old      — Previous designation / title
designation_new      — New / promoted designation
department           — Department
employer_name        — Company name
effective_date       — Date from which promotion is effective (YYYY-MM-DD)
letter_date          — Date the letter was issued (YYYY-MM-DD)
ctc_new              — Revised CTC post-promotion (numeric, INR annual) if stated

RETURN FORMAT (JSON only):
{{
  "employee_name":    {{"value": null, "confidence": 0.0}},
  "employee_id":      {{"value": null, "confidence": 0.0}},
  "designation_old":  {{"value": null, "confidence": 0.0}},
  "designation_new":  {{"value": null, "confidence": 0.0}},
  "department":       {{"value": null, "confidence": 0.0}},
  "employer_name":    {{"value": null, "confidence": 0.0}},
  "effective_date":   {{"value": null, "confidence": 0.0}},
  "letter_date":      {{"value": null, "confidence": 0.0}},
  "ctc_new":          {{"value": null, "confidence": 0.0}},
  "overall_confidence": 0.0
}}"""
