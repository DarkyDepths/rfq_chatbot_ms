"""Intelligence-backed Phase 4 RFQ snapshot retrieval tool."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from src.connectors.intelligence_connector import IntelligenceConnector
from src.models.envelope import ConfidenceLevel, ToolResultEnvelope
from src.tools.common.envelope import build_tool_result_envelope


class GetRfqSnapshotInput(BaseModel):
    """Typed input for the intelligence snapshot tool."""

    model_config = ConfigDict(extra="forbid")

    rfq_id: uuid.UUID


def get_rfq_snapshot(
    request: GetRfqSnapshotInput,
    connector: IntelligenceConnector,
) -> ToolResultEnvelope:
    """Return the current intelligence snapshot for one RFQ."""

    snapshot = connector.get_snapshot(request.rfq_id)
    return build_tool_result_envelope(
        value=snapshot,
        system="rfq_intelligence_ms",
        artifact="rfq_intelligence_snapshot",
        locator=f"/intelligence/v1/rfqs/{request.rfq_id}/snapshot",
        parsed_at=snapshot.updated_at or snapshot.created_at,
        confidence=ConfidenceLevel.PATTERN_1_SAMPLE,
        validated_against="1_sample",
    )
