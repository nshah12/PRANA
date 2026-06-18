"""
ExtractionService — Stage 04 of the DocumentPipelineWorkflow.

Receives redacted document text (NIK already replaced with [NIK_REDACTED]).
Selects the correct prompt + schema for the doc_type.
Calls the local LLM via LLMClient.
Validates the response against the Pydantic schema.
Returns structured extracted fields + overall_confidence.
"""

import json
import logging
from enum import Enum

from llm_client import LLMClient
from extraction.schemas import (
    BaseExtraction, SalarySlipExtraction, Form16Extraction, OfferLetterExtraction,
    AppointmentLetterExtraction, IncrementLetterExtraction, PromotionLetterExtraction,
    ExperienceLetterExtraction, RelievingLetterExtraction, JoiningLetterExtraction,
    PFAcknowledgementExtraction,
)
from extraction.prompts import (
    salary_slip, form_16, offer_letter, increment_letter,
    promotion_letter, relieving_letter, experience_letter,
    appointment_letter, joining_letter, pf_acknowledgement,
)

log = logging.getLogger(__name__)


class DocType(str, Enum):
    SALARY_SLIP         = "SALARY_SLIP"
    FORM_16             = "FORM_16"
    OFFER_LETTER        = "OFFER_LETTER"
    APPOINTMENT_LETTER  = "APPOINTMENT_LETTER"
    INCREMENT_LETTER    = "INCREMENT_LETTER"
    PROMOTION_LETTER    = "PROMOTION_LETTER"
    EXPERIENCE_LETTER   = "EXPERIENCE_LETTER"
    RELIEVING_LETTER    = "RELIEVING_LETTER"
    JOINING_LETTER      = "JOINING_LETTER"
    PF_ACKNOWLEDGEMENT  = "PF_ACKNOWLEDGEMENT"


# Maps each doc_type to its (prompt_module, schema_class)
_REGISTRY: dict[DocType, tuple] = {
    DocType.SALARY_SLIP:        (salary_slip,        SalarySlipExtraction),
    DocType.FORM_16:            (form_16,             Form16Extraction),
    DocType.OFFER_LETTER:       (offer_letter,        OfferLetterExtraction),
    # schemas for remaining types to be added; use BaseExtraction as placeholder
    DocType.APPOINTMENT_LETTER: (appointment_letter,  AppointmentLetterExtraction),
    DocType.INCREMENT_LETTER:   (increment_letter,    IncrementLetterExtraction),
    DocType.PROMOTION_LETTER:   (promotion_letter,    PromotionLetterExtraction),
    DocType.EXPERIENCE_LETTER:  (experience_letter,   ExperienceLetterExtraction),
    DocType.RELIEVING_LETTER:   (relieving_letter,    RelievingLetterExtraction),
    DocType.JOINING_LETTER:     (joining_letter,      JoiningLetterExtraction),
    DocType.PF_ACKNOWLEDGEMENT: (pf_acknowledgement,  PFAcknowledgementExtraction),
}

# Confidence thresholds — read from config in production, hard-defaults here
CONFIDENCE_ROUTE    = 0.90
CONFIDENCE_FLAGGED  = 0.75  # below this → flag for OA review but still route
CONFIDENCE_REJECT   = 0.60  # below this → LOW_CONFIDENCE exception


class ExtractionResult:
    def __init__(self, fields: dict, overall_confidence: float, low_confidence_fields: list[str]):
        self.fields = fields
        self.overall_confidence = overall_confidence
        self.low_confidence_fields = low_confidence_fields

    @property
    def status(self) -> str:
        if self.overall_confidence >= CONFIDENCE_ROUTE:
            return "ROUTED"
        if self.overall_confidence >= CONFIDENCE_FLAGGED:
            return "ROUTED_FLAGGED"
        return "LOW_CONFIDENCE"


class ExtractionService:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    async def extract(self, doc_type: DocType, redacted_text: str) -> ExtractionResult:
        """
        Extract fields from redacted document text.

        redacted_text: document text with NIK replaced by [NIK_REDACTED].
        Returns ExtractionResult with fields dict, confidence, and status.
        """
        if doc_type not in _REGISTRY:
            raise ValueError(f"Unknown doc_type: {doc_type}")

        prompt_module, schema_cls = _REGISTRY[doc_type]
        system = prompt_module.SYSTEM
        user   = prompt_module.build_user_prompt(redacted_text)

        raw = await self._llm.complete(system=system, user=user, temperature=0.0)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # LLM returned non-JSON — extract JSON block if wrapped in markdown
            parsed = _extract_json_block(raw)

        validated: BaseExtraction = schema_cls.model_validate(parsed)
        low_conf = validated.low_confidence_fields(threshold=CONFIDENCE_FLAGGED)

        log.info(
            "extraction complete",
            extra={
                "doc_type": doc_type,
                "overall_confidence": validated.overall_confidence,
                "low_confidence_fields": low_conf,
            }
        )

        return ExtractionResult(
            fields=validated.model_dump(),
            overall_confidence=validated.overall_confidence,
            low_confidence_fields=low_conf,
        )


def _extract_json_block(text: str) -> dict:
    """Pull JSON out of a markdown code block if the LLM wrapped its response."""
    import re
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # last resort — find first { ... } block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"LLM response contained no valid JSON: {text[:200]}")
