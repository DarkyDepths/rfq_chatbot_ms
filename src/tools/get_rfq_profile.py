"""Manager-backed Phase 4 RFQ profile retrieval tool."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from src.connectors.manager_connector import ManagerConnector
from src.models.envelope import ConfidenceLevel, ToolResultEnvelope
from src.tools.common.envelope import build_tool_result_envelope


class GetRfqProfileInput(BaseModel):
    """Typed input for the manager RFQ profile tool."""

    model_config = ConfigDict(extra="forbid")

    rfq_id: uuid.UUID


def get_rfq_profile(
    request: GetRfqProfileInput,
    connector: ManagerConnector,
) -> ToolResultEnvelope:
    """Return the current RFQ profile from rfq_manager_ms."""

    profile = connector.get_rfq(request.rfq_id)
    return build_tool_result_envelope(
        value=profile,
        system="rfq_manager_ms",
        artifact="rfq",
        locator=f"/rfq-manager/v1/rfqs/{request.rfq_id}",
        parsed_at=profile.updated_at,
        confidence=ConfidenceLevel.DETERMINISTIC,
    )
