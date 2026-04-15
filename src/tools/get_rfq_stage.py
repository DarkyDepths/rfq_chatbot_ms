"""Manager-backed Phase 4 RFQ stage retrieval tool."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from src.connectors.manager_connector import ManagerConnector
from src.models.envelope import ConfidenceLevel, ToolResultEnvelope
from src.tools.common.envelope import build_tool_result_envelope


class GetRfqStageInput(BaseModel):
    """Typed input for the manager RFQ stage tool."""

    model_config = ConfigDict(extra="forbid")

    rfq_id: uuid.UUID


def get_rfq_stage(
    request: GetRfqStageInput,
    connector: ManagerConnector,
) -> ToolResultEnvelope:
    """Return the current stage list for one RFQ."""

    stage_list = connector.get_rfq_stages(request.rfq_id)
    return build_tool_result_envelope(
        value=stage_list,
        system="rfq_manager_ms",
        artifact="rfq_stages",
        locator=f"/rfq-manager/v1/rfqs/{request.rfq_id}/stages",
        confidence=ConfidenceLevel.DETERMINISTIC,
    )
