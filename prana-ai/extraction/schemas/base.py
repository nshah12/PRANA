from pydantic import BaseModel, field_validator
from typing import Optional


class FieldValue(BaseModel):
    value: Optional[str] = None
    confidence: float = 0.0

    @field_validator("confidence")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


# Alias — some tests import ExtractedField from this module
ExtractedField = FieldValue


class BaseExtraction(BaseModel):
    overall_confidence: float = 0.0

    @field_validator("overall_confidence")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    def low_confidence_fields(self, threshold: float = 0.75) -> list[str]:
        """Return field names whose confidence is below threshold."""
        return [
            name for name, val in self.__dict__.items()
            if isinstance(val, FieldValue) and val.confidence < threshold
        ]
