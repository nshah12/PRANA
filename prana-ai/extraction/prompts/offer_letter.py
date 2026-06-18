SYSTEM = """You are a document extraction engine for Indian HR documents.
Extract ONLY the fields listed below from the provided offer letter.
Return a valid JSON object only — no prose, no markdown, no explanation.
For each field, return a confidence score 0.0–1.0.
If a field is not present, return null with confidence 0.0."""

def build_user_prompt(redacted_text: str) -> str:
    return f"""DOCUMENT TYPE: Offer Letter
DOCUMENT TEXT:
{redacted_text}

EXTRACT THESE FIELDS:
employee_name        — Candidate / employee full name
designation          — Offered job title / role
department           — Department
location             — Work location / city
employer_name        — Hiring company name
date_of_offer        — Date the offer letter was issued (YYYY-MM-DD)
date_of_joining      — Expected / agreed joining date (YYYY-MM-DD)
ctc_annual           — Annual CTC offered (numeric, INR)
ctc_monthly          — Monthly CTC offered (numeric, INR) — if stated
probation_months     — Probation period in months (numeric)
notice_period_days   — Notice period in days (numeric)
employee_id          — Employee ID assigned in offer (if present)
reporting_manager    — Name of reporting manager (if stated)

RETURN FORMAT (JSON only):
{{
  "employee_name":     {{"value": null, "confidence": 0.0}},
  "designation":       {{"value": null, "confidence": 0.0}},
  "department":        {{"value": null, "confidence": 0.0}},
  "location":          {{"value": null, "confidence": 0.0}},
  "employer_name":     {{"value": null, "confidence": 0.0}},
  "date_of_offer":     {{"value": null, "confidence": 0.0}},
  "date_of_joining":   {{"value": null, "confidence": 0.0}},
  "ctc_annual":        {{"value": null, "confidence": 0.0}},
  "ctc_monthly":       {{"value": null, "confidence": 0.0}},
  "probation_months":  {{"value": null, "confidence": 0.0}},
  "notice_period_days":{{"value": null, "confidence": 0.0}},
  "employee_id":       {{"value": null, "confidence": 0.0}},
  "reporting_manager": {{"value": null, "confidence": 0.0}},
  "overall_confidence": 0.0
}}"""
