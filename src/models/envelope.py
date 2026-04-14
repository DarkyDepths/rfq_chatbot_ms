"""Tool result envelope contracts shared across future tool integrations."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConfidenceLevel(str, Enum):
    """Closed confidence states defined by the architecture brief."""

    DETERMINISTIC = "deterministic"
    PATTERN_1_SAMPLE = "pattern_1_sample"
    ABSENT = "absent"


class SourceRef(BaseModel):
    """Provenance pointer for a factual tool result."""

    model_config = ConfigDict(extra="forbid")

    system: str = Field(min_length=1)
    artifact: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    parsed_at: datetime | None = None


class ToolResultEnvelope(BaseModel):
    """Frozen Phase 1 contract for future tool outputs."""

    model_config = ConfigDict(extra="forbid")

    value: Any
    source_ref: SourceRef | None = None
    confidence: ConfidenceLevel
    validated_against: Literal["1_sample", "multi_sample"] | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_source_ref_requirement(self) -> "ToolResultEnvelope":
        if self.confidence != ConfidenceLevel.ABSENT and self.source_ref is None:
            raise ValueError("source_ref is required when confidence is not 'absent'")
        return self
