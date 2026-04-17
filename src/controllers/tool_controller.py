"""Minimal explicit tool selection and execution for Phase 5 retrieval."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from src.config.capability_status import CAPABILITY_STATUS_ENTRIES
from src.config.role_profiles import FALLBACK_ROLE, ROLE_PROFILES, RoleProfile
from src.config.stage_profiles import DEFAULT_STAGE_PROFILE, StageProfile
from src.connectors.intelligence_connector import IntelligenceConnector
from src.connectors.manager_connector import ManagerConnector, ManagerRfqDetail
from src.models.conversation import ToolCallRecord
from src.models.envelope import ConfidenceLevel, ToolResultEnvelope
from src.models.session import ChatbotSession
from src.tools.common.envelope import build_tool_result_envelope
from src.tools.get_rfq_profile import GetRfqProfileInput, get_rfq_profile
from src.tools.get_rfq_snapshot import GetRfqSnapshotInput, get_rfq_snapshot
from src.tools.get_rfq_stage import GetRfqStageInput, get_rfq_stage
from src.utils.errors import UnprocessableEntityError


logger = logging.getLogger(__name__)


class RetrievalPlan(BaseModel):
    """A small typed record describing one planned Phase 5 retrieval."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    selection_reason: str = Field(min_length=1)


@dataclass(frozen=True)
class CapabilityStatusHit:
    """Sentinel describing a closed-list unsupported capability match."""

    matched_keyword: str
    capability_name: str
    named_future_condition: str


class ToolController:
    """Owns explicit Phase 5 tool selection and read-only execution."""

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
        *,
        stage_profile: StageProfile | None = None,
        role_profile: RoleProfile | None = None,
        preloaded_rfq_detail: ManagerRfqDetail | None = None,
    ) -> list[ToolCallRecord]:
        """Return zero or one executed tool calls for the current turn."""

        effective_stage_profile = stage_profile or DEFAULT_STAGE_PROFILE
        effective_role_profile = role_profile or ROLE_PROFILES[FALLBACK_ROLE]

        plan = self._plan_tool_use(
            user_content,
            stage_profile=effective_stage_profile,
            role_profile=effective_role_profile,
        )
        if plan is None:
            return []
        if isinstance(plan, CapabilityStatusHit):
            return [self._build_capability_status_record(plan)]

        rfq_id = self._require_rfq_uuid(chatbot_session)
        result = self._execute_tool(
            plan.tool_name,
            rfq_id,
            preloaded_rfq_detail=preloaded_rfq_detail,
        )
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

    def _plan_tool_use(
        self,
        user_content: str,
        *,
        stage_profile: StageProfile,
        role_profile: RoleProfile,
    ) -> RetrievalPlan | CapabilityStatusHit | None:
        normalized = user_content.strip().lower()
        if not normalized:
            self._log_phase5_field("phase5.tools_keyword_matched", [])
            self._log_phase5_field("phase5.tools_allowed_after_stage", [])
            self._log_phase5_field("phase5.tools_allowed_after_role", [])
            return None

        capability_status_hit = self._match_capability_status(normalized)
        if capability_status_hit is not None:
            self._log_phase5_field("phase5.tools_keyword_matched", [])
            self._log_phase5_field("phase5.tools_allowed_after_stage", [])
            self._log_phase5_field("phase5.tools_allowed_after_role", [])
            self._log_phase5_field(
                "phase5.capability_status_hit",
                capability_status_hit.capability_name,
            )
            return capability_status_hit

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

        self._log_phase5_field(
            "phase5.tools_keyword_matched",
            [plan.tool_name for plan in candidate_plans],
        )

        stage_filtered_plans = [
            plan
            for plan in candidate_plans
            if plan.tool_name in stage_profile["tool_allow_list"]
        ]
        self._log_phase5_field(
            "phase5.tools_allowed_after_stage",
            [plan.tool_name for plan in stage_filtered_plans],
        )
        role_filtered_plans = [
            plan
            for plan in stage_filtered_plans
            if plan.tool_name in role_profile["tool_allow_list"]
        ]
        self._log_phase5_field(
            "phase5.tools_allowed_after_role",
            [plan.tool_name for plan in role_filtered_plans],
        )

        tool_names = {plan.tool_name for plan in role_filtered_plans}
        if len(tool_names) > 1:
            raise UnprocessableEntityError(
                "This retrieval request is ambiguous in Phase 5; ask for one RFQ fact at a time"
            )
        if role_filtered_plans:
            return role_filtered_plans[0]

        return None

    @staticmethod
    def _log_phase5_field(field_name: str, value) -> None:
        logger.info(
            "%s=%s",
            field_name,
            value,
            extra={field_name: value},
        )

    @staticmethod
    def _match_capability_status(normalized_user_content: str) -> CapabilityStatusHit | None:
        for keyword, capability_status in CAPABILITY_STATUS_ENTRIES.items():
            if keyword in normalized_user_content:
                return CapabilityStatusHit(
                    matched_keyword=keyword,
                    capability_name=capability_status["capability_name"],
                    named_future_condition=capability_status["named_future_condition"],
                )
        return None

    @staticmethod
    def _build_capability_status_record(hit: CapabilityStatusHit) -> ToolCallRecord:
        result = ToolResultEnvelope(
            value={
                "capability_name": hit.capability_name,
                "named_future_condition": hit.named_future_condition,
            },
            confidence=ConfidenceLevel.ABSENT,
            source_ref=None,
        )
        return ToolCallRecord(
            tool_name="get_capability_status",
            arguments={
                "matched_keyword": hit.matched_keyword,
                "selection_reason": "User asked for a known unsupported capability",
            },
            result=result,
            source_refs=[],
        )

    def _require_rfq_uuid(self, chatbot_session: ChatbotSession) -> uuid.UUID:
        if not chatbot_session.rfq_id:
            raise UnprocessableEntityError(
                "Phase 5 retrieval requires an RFQ-bound session with a downstream RFQ id"
            )

        try:
            return uuid.UUID(str(chatbot_session.rfq_id))
        except ValueError as exc:
            raise UnprocessableEntityError(
                "Phase 5 retrieval requires session.rfq_id to be a downstream UUID. "
                "Human-readable RFQ codes like 'IF-25144' are not supported here yet."
            ) from exc

    def _execute_tool(
        self,
        tool_name: str,
        rfq_id: uuid.UUID,
        *,
        preloaded_rfq_detail: ManagerRfqDetail | None = None,
    ):
        if tool_name == "get_rfq_profile":
            if preloaded_rfq_detail is not None:
                return build_tool_result_envelope(
                    value=preloaded_rfq_detail,
                    system="rfq_manager_ms",
                    artifact="rfq",
                    locator=f"/rfq-manager/v1/rfqs/{rfq_id}",
                    parsed_at=preloaded_rfq_detail.updated_at,
                    confidence=ConfidenceLevel.DETERMINISTIC,
                )
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
