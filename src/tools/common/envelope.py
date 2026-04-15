"""Helpers for building Phase 4 tool result envelopes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from src.models.envelope import ConfidenceLevel, SourceRef, ToolResultEnvelope


def build_tool_result_envelope(
    *,
    value: Any,
    system: str,
    artifact: str,
    locator: str,
    parsed_at: datetime | None = None,
    confidence: ConfidenceLevel = ConfidenceLevel.DETERMINISTIC,
    validated_against: Literal["1_sample", "multi_sample"] | None = None,
) -> ToolResultEnvelope:
    """Construct a ToolResultEnvelope with consistent provenance fields."""

    return ToolResultEnvelope(
        value=value,
        source_ref=SourceRef(
            system=system,
            artifact=artifact,
            locator=locator,
            parsed_at=parsed_at,
        ),
        confidence=confidence,
        validated_against=validated_against,
    )
