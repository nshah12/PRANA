SYSTEM = """You are a document extraction engine for Indian HR documents.
Extract ONLY the fields listed below from the provided appointment letter.
Return a valid JSON object only — no prose, no markdown, no explanation.
For each field, return a confidence score 0.0–1.0.
If a field is not present, return null with confidence 0.0.

Note: Appointment letters and offer letters are different.
Appointment = formal confirmation after acceptance (may include employee ID).
Offer = pre-acceptance offer extended to candidate."""

def build_user_prompt(redacted_text: str) -> str:
    return f"""DOCUMENT TYPE: Appointment Letter
DOCUMENT TEXT:
{redacted_text}

EXTRACT THESE FIELDS:
employee_name        — Employee full name
employee_id          — Employee ID / staff number assigned
designation          — Designation / role
department           — Department
location             — Work location / city
employer_name        — Company name
date_of_appointment  — Date the appointment letter was issued (YYYY-MM-DD)
date_of_joining      — Joining date (YYYY-MM-DD)
ctc_annual           — Annual CTC (numeric, INR)
probation_months     — Probation period in months (numeric)
notice_period_days   — Notice period in days (numeric)
grade_band           — Grade or band level (e.g. L4, Band C) if stated

RETURN FORMAT (JSON only):
{{
  "employee_name":       {{"value": null, "confidence": 0.0}},
  "employee_id":         {{"value": null, "confidence": 0.0}},
  "designation":         {{"value": null, "confidence": 0.0}},
  "department":          {{"value": null, "confidence": 0.0}},
  "location":            {{"value": null, "confidence": 0.0}},
  "employer_name":       {{"value": null, "confidence": 0.0}},
  "date_of_appointment": {{"value": null, "confidence": 0.0}},
  "date_of_joining":     {{"value": null, "confidence": 0.0}},
  "ctc_annual":          {{"value": null, "confidence": 0.0}},
  "probation_months":    {{"value": null, "confidence": 0.0}},
  "notice_period_days":  {{"value": null, "confidence": 0.0}},
  "grade_band":          {{"value": null, "confidence": 0.0}},
  "overall_confidence": 0.0
}}"""
