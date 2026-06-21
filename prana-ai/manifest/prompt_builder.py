"""
PromptBuilder — builds LLM extraction prompts dynamically from a ManifestData.

Replaces the hardcoded per-doc-type prompt modules in extraction/prompts/*.py.
The static prompts remain as fallback for offline/test use; the pipeline uses
this builder when a ManifestData is available.

Prompt design principles:
- System prompt is stable across doc types (cached by LLM inference server)
- Only the user prompt varies (field list + doc text)
- Required fields are clearly marked — LLM knows which are non-negotiable
- Identity fields are listed first so the LLM gives them priority attention
- Output format is always the same JSON envelope for easy schema validation
"""

from manifest.manifest_client import ManifestData

SYSTEM_PROMPT = """You are a document extraction engine for Indian employment and financial documents.
Your job: extract ONLY the specified fields from the document text provided.

Rules:
- Return valid JSON only — no prose, no markdown fences, no explanation.
- For each field, return {"value": <extracted_value>, "confidence": <0.0–1.0>}.
- If a field is absent from the document, return {"value": null, "confidence": 0.0}.
- Do NOT invent, infer, or guess values. Extract only what is explicitly printed.
- Monetary values: return as numeric (no currency symbol, no commas). Example: 85000
- Dates: return as ISO 8601 string where possible (YYYY-MM-DD). Example: "2024-03-01"
- PAN numbers will appear as [NIK_REDACTED] — extract that token as-is with confidence 0.99.
- overall_confidence: weighted average of confidence scores for required fields only."""


def build_prompt(manifest: ManifestData, redacted_text: str) -> tuple[str, str]:
    """
    Build (system_prompt, user_prompt) for the given manifest and document text.

    Returns a tuple so the caller can pass them directly to LLMClient.complete().
    """
    return SYSTEM_PROMPT, _build_user_prompt(manifest, redacted_text)


def _build_user_prompt(manifest: ManifestData, redacted_text: str) -> str:
    required_block = _field_list_block(
        manifest.required_fields, label="REQUIRED FIELDS (extract these first — must be present)"
    )
    identity_block = _field_list_block(
        manifest.identity_fields,
        label="IDENTITY FIELDS (used to match this document to an employee — highest priority)",
    )
    optional_block = _field_list_block(
        manifest.optional_fields, label="OPTIONAL FIELDS (extract if present)"
    )

    all_fields = manifest.all_fields()
    return_template = _build_return_template(manifest.required_fields, all_fields)

    return f"""DOCUMENT TYPE: {manifest.doc_type}

{identity_block}

{required_block}

{optional_block}

DOCUMENT TEXT:
{redacted_text}

RETURN FORMAT (JSON only — no other text):
{return_template}"""


def _field_list_block(fields: list[str], label: str) -> str:
    if not fields:
        return ""
    lines = "\n".join(f"  {f}" for f in fields)
    return f"{label}:\n{lines}"


def _build_return_template(required_fields: list[str], all_fields: list[str]) -> str:
    """
    Build the JSON template string shown to the LLM.
    Required fields are annotated with a comment so the LLM knows they matter more.
    overall_confidence is defined as the weighted average of required field confidences.
    """
    lines = ["{"]
    for f in all_fields:
        annotation = "  // REQUIRED" if f in required_fields else ""
        lines.append(f'  "{f}": {{"value": null, "confidence": 0.0}},{annotation}')
    lines.append('  "overall_confidence": 0.0  // weighted avg of required field confidences')
    lines.append("}")
    return "\n".join(lines)


# ── AUTO_DETECT probe prompt ────────────────────────────────────────────────────

AUTO_DETECT_SYSTEM = """You are a document classifier for Indian employment and financial documents.
Extract a minimal set of fields to identify what type of document this is.
Return valid JSON only — no prose, no markdown."""

AUTO_DETECT_FIELDS = [
    "employee_name",
    "employer_name",
    "document_date",
    "pay_period_month",
    "pay_period_year",
    "date_of_joining",
    "last_working_day",
    "financial_year",
    "assessment_year",
    "uan_number",
    "account_number",
    "investment_type",
    "designation",
    "net_pay",
    "gross_salary",
    "tds_deducted",
    "ctc",
    "revised_ctc",
    "new_designation",
    "appraisal_period",
    "rating",
    "pf_period",
    "statement_period",
]

AUTO_DETECT_USER_TEMPLATE = """Identify what type of Indian employment or financial document this is.
Extract only these indicator fields (null if not present):

{field_list}

DOCUMENT TEXT:
{text}

RETURN FORMAT (JSON only):
{{
{field_template}
}}"""


def build_auto_detect_prompt(redacted_text: str) -> tuple[str, str]:
    """Build (system, user) prompt for the AUTO_DETECT probe extraction."""
    field_list = "\n".join(f"  {f}" for f in AUTO_DETECT_FIELDS)
    field_template = "\n".join(
        f'  "{f}": {{"value": null, "confidence": 0.0}},'
        for f in AUTO_DETECT_FIELDS
    )
    user = AUTO_DETECT_USER_TEMPLATE.format(
        field_list=field_list,
        text=redacted_text,
        field_template=field_template.rstrip(","),
    )
    return AUTO_DETECT_SYSTEM, user
