"""Minimal explicit tool selection and execution for Phase 4 retrieval."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from src.connectors.intelligence_connector import IntelligenceConnector
from src.connectors.manager_connector import ManagerConnector
from src.models.conversation import ToolCallRecord
from src.models.session import ChatbotSession
from src.tools.get_rfq_profile import GetRfqProfileInput, get_rfq_profile
from src.tools.get_rfq_snapshot import GetRfqSnapshotInput, get_rfq_snapshot
from src.tools.get_rfq_stage import GetRfqStageInput, get_rfq_stage
from src.utils.errors import UnprocessableEntityError


class RetrievalPlan(BaseModel):
    """A small typed record describing one planned Phase 4 retrieval."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    selection_reason: str = Field(min_length=1)


class ToolController:
    """Owns explicit Phase 4 tool selection and read-only execution."""

    stage_keywords = (
        "stage",
        "current stage",
        "blocked",
        "blocker",
        "progress",
        "assigned team",
    )
    snapshot_keywords = (
        "snapshot",
        "currently known",
        "known about this rfq",
        "current snapshot",
        "snapshot summary",
        "missing info",
        "missing information",
    )
    profile_keywords = (
        "deadline",
        "owner",
        "client",
        "country",
        "industry",
        "priority",
        "workflow",
        "rfq code",
        "rfq status",
        "status of this rfq",
    )
    unsupported_keywords = (
        "briefing",
        "workbook review",
        "workbook profile",
        "analytics",
        "stats",
        "list rfqs",
        "portfolio",
        "grand total",
        "final price",
        "estimation amount",
    )

    def __init__(
        self,
        manager_connector: ManagerConnector,
        intelligence_connector: IntelligenceConnector,
    ):
        self.manager_connector = manager_connector
        self.intelligence_connector = intelligence_connector

    def maybe_execute_retrieval(
        self,
        chatbot_session: ChatbotSession,
        user_content: str,
    ) -> list[ToolCallRecord]:
        """Return zero or one executed tool calls for the current turn."""

        plan = self._plan_tool_use(user_content)
        if plan is None:
            return []

        rfq_id = self._require_rfq_uuid(chatbot_session)
        result = self._execute_tool(plan.tool_name, rfq_id)
        source_refs = [result.source_ref] if result.source_ref else []
        return [
            ToolCallRecord(
                tool_name=plan.tool_name,
                arguments={
                    "rfq_id": str(rfq_id),
                    "selection_reason": plan.selection_reason,
                },
                result=result,
                source_refs=source_refs,
            )
        ]

    def _plan_tool_use(self, user_content: str) -> RetrievalPlan | None:
        normalized = user_content.strip().lower()
        if not normalized:
            return None

        if any(keyword in normalized for keyword in self.unsupported_keywords):
            raise UnprocessableEntityError(
                "This retrieval request is not supported in Phase 4 yet"
            )

        candidate_plans = []
        if any(keyword in normalized for keyword in self.stage_keywords):
            candidate_plans.append(
                RetrievalPlan(
                    tool_name="get_rfq_stage",
                    selection_reason="User asked about RFQ stage, progress, or blockers",
                )
            )

        if any(keyword in normalized for keyword in self.snapshot_keywords):
            candidate_plans.append(
                RetrievalPlan(
                    tool_name="get_rfq_snapshot",
                    selection_reason=(
                        "User asked for the current RFQ snapshot or currently known facts"
                    ),
                )
            )

        if any(keyword in normalized for keyword in self.profile_keywords):
            candidate_plans.append(
                RetrievalPlan(
                    tool_name="get_rfq_profile",
                    selection_reason="User asked about RFQ profile metadata from manager",
                )
            )

        tool_names = {plan.tool_name for plan in candidate_plans}
        if len(tool_names) > 1:
            raise UnprocessableEntityError(
                "This retrieval request is ambiguous in Phase 4; ask for one RFQ fact at a time"
            )
        if candidate_plans:
            return candidate_plans[0]

        return None

    def _require_rfq_uuid(self, chatbot_session: ChatbotSession) -> uuid.UUID:
        if not chatbot_session.rfq_id:
            raise UnprocessableEntityError(
                "Phase 4 retrieval requires an RFQ-bound session with a downstream RFQ id"
            )

        try:
            return uuid.UUID(str(chatbot_session.rfq_id))
        except ValueError as exc:
            raise UnprocessableEntityError(
                "Phase 4 retrieval requires session.rfq_id to be a downstream UUID. "
                "Human-readable RFQ codes like 'IF-25144' are not supported here yet."
            ) from exc

    def _execute_tool(self, tool_name: str, rfq_id: uuid.UUID):
        if tool_name == "get_rfq_profile":
            return get_rfq_profile(
                GetRfqProfileInput(rfq_id=rfq_id),
                self.manager_connector,
            )
        if tool_name == "get_rfq_stage":
            return get_rfq_stage(
                GetRfqStageInput(rfq_id=rfq_id),
                self.manager_connector,
            )
        if tool_name == "get_rfq_snapshot":
            return get_rfq_snapshot(
                GetRfqSnapshotInput(rfq_id=rfq_id),
                self.intelligence_connector,
            )

        raise UnprocessableEntityError(f"Unsupported retrieval tool '{tool_name}'")
