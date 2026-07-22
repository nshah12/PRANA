SYSTEM = """You are a document extraction engine for Indian HR documents.
Extract ONLY the fields listed below from the provided Form 26AS (Income Tax Section 203AA / Annual Tax Statement).
Return a valid JSON object only — no prose, no markdown, no explanation.
For each field, return a confidence score 0.0–1.0.
If a field is not present, return null with confidence 0.0.
NOTE: Form 26AS is an annual tax statement from the Income Tax Department showing TDS/TCS credits."""

def build_user_prompt(redacted_text: str) -> str:
    return f"""DOCUMENT TYPE: Form 26AS (Annual Tax Statement - Income Tax Section 203AA - India)
DOCUMENT TEXT:
{redacted_text}

EXTRACT THESE FIELDS:
taxpayer_name      — Taxpayer full name (employee)
pan_number         — Taxpayer PAN (format: AAAAA9999A) — will be [NIK_REDACTED] if tokenised
assessment_year    — Assessment year (e.g. 2024-25)
deductor_name      — Name of the primary TDS deductor (employer)
deductor_tan       — TAN of the primary TDS deductor (format: AAAAA9999A)
tds_amount         — Total TDS amount shown in Part A (numeric, INR)
tcs_amount         — Total TCS amount shown in Part B (numeric, INR) — null if not present
advance_tax        — Total advance tax paid (numeric, INR) — null if not present
self_assessment_tax — Self-assessment tax paid (numeric, INR) — null if not present
refund_amount      — Refund amount if any (numeric, INR) — null if not present

RETURN FORMAT (JSON only):
{{
  "taxpayer_name":       {{"value": null, "confidence": 0.0}},
  "pan_number":          {{"value": null, "confidence": 0.0}},
  "assessment_year":     {{"value": null, "confidence": 0.0}},
  "deductor_name":       {{"value": null, "confidence": 0.0}},
  "deductor_tan":        {{"value": null, "confidence": 0.0}},
  "tds_amount":          {{"value": null, "confidence": 0.0}},
  "tcs_amount":          {{"value": null, "confidence": 0.0}},
  "advance_tax":         {{"value": null, "confidence": 0.0}},
  "self_assessment_tax": {{"value": null, "confidence": 0.0}},
  "refund_amount":       {{"value": null, "confidence": 0.0}},
  "overall_confidence": 0.0
}}"""
