"""Phase 5 turn orchestration controller."""

from __future__ import annotations

import logging
import uuid

from src.connectors.azure_openai_connector import AzureOpenAIConnector
from src.controllers.context_builder import ContextBuilder
from src.controllers.conversation_controller import ConversationController
from src.controllers.role_controller import RoleController
from src.controllers.stage_controller import StageController
from src.controllers.tool_controller import CapabilityStatusHit, ToolController
from src.datasources.session_datasource import SessionDatasource
from src.models.envelope import ConfidenceLevel
from src.models.turn import TurnCreateCommand, TurnResponse
from src.translators.envelope_translator import (
    collect_source_refs,
    tool_call_records_to_prompt_blocks,
    tool_call_records_to_storage_payload,
)
from src.translators.chat_translator import to_turn_response
from src.utils.errors import NotFoundError


logger = logging.getLogger(__name__)


class ChatController:
    """Owns the Phase 5 conversational turn pipeline."""

    def __init__(
        self,
        session_datasource: SessionDatasource,
        conversation_controller: ConversationController,
        context_builder: ContextBuilder,
        azure_openai_connector: AzureOpenAIConnector,
        tool_controller: ToolController,
        stage_controller: StageController,
        role_controller: RoleController,
    ):
        self.session_datasource = session_datasource
        self.conversation_controller = conversation_controller
        self.context_builder = context_builder
        self.azure_openai_connector = azure_openai_connector
        self.tool_controller = tool_controller
        self.stage_controller = stage_controller
        self.role_controller = role_controller

    def handle_turn(
        self,
        session_id: uuid.UUID,
        command: TurnCreateCommand,
    ) -> TurnResponse:
        session = self.session_datasource.get_by_id(session_id)
        if not session:
            raise NotFoundError(f"Session '{session_id}' not found")

        conversation = self.conversation_controller.get_or_create_conversation_for_session(
            session.id
        )

        stage_resolution = self.stage_controller.resolve_stage(session)
        role_resolution = self.role_controller.resolve_role(session)
        logger.info(
            "phase5.role_applied=%s",
            role_resolution.role,
            extra={"phase5.role_applied": role_resolution.role},
        )
        logger.info(
            "phase5.role_fallback_used=%s",
            role_resolution.fallback_used,
            extra={"phase5.role_fallback_used": role_resolution.fallback_used},
        )
        if role_resolution.fallback_used:
            logger.info(
                "phase5.role_original=%s",
                role_resolution.original_role,
                extra={"phase5.role_original": role_resolution.original_role},
            )

        tool_call_records = self.tool_controller.maybe_execute_retrieval(
            session,
            command.content,
            stage_profile=stage_resolution.profile,
            role_profile=role_resolution.profile,
            preloaded_rfq_detail=stage_resolution.rfq_detail,
        )

        recent_messages = self.conversation_controller.get_recent_history(
            conversation.id,
            max(self.context_builder.history_window_size - 1, 0),
        )
        self.conversation_controller.create_user_message(conversation.id, command.content)
        any_pattern_based_tool_fired = any(
            record.result is not None
            and record.result.confidence == ConfidenceLevel.PATTERN_1_SAMPLE
            for record in tool_call_records
        )
        capability_status_hit = self._extract_capability_status_hit(tool_call_records)
        prompt_envelope = self.context_builder.build(
            recent_messages,
            tool_call_records_to_prompt_blocks(tool_call_records),
            latest_user_turn=command.content,
            stage_resolution=stage_resolution,
            role_resolution=role_resolution,
            any_pattern_based_tool_fired=any_pattern_based_tool_fired,
            capability_status_hit=capability_status_hit,
        )
        azure_messages = self._build_azure_messages(prompt_envelope)
        completion = self.azure_openai_connector.create_chat_completion(azure_messages)
        confidence_marker_emitted = (
            "Confidence: pattern-based (validated against 1 sample)"
            in completion.assistant_text
        )
        logger.info(
            "phase5.confidence_marker_emitted=%s",
            confidence_marker_emitted,
            extra={"phase5.confidence_marker_emitted": confidence_marker_emitted},
        )
        assistant_message = self.conversation_controller.create_assistant_message(
            conversation.id,
            completion.assistant_text,
            tool_calls=tool_call_records_to_storage_payload(tool_call_records),
            source_refs=collect_source_refs(tool_call_records),
        )

        return to_turn_response(conversation.id, assistant_message)

    @staticmethod
    def _extract_capability_status_hit(
        tool_call_records,
    ) -> CapabilityStatusHit | None:
        for record in tool_call_records:
            if record.tool_name != "get_capability_status" or record.result is None:
                continue

            value = record.result.value
            if not isinstance(value, dict):
                continue

            capability_name = value.get("capability_name")
            named_future_condition = value.get("named_future_condition")
            if not capability_name or not named_future_condition:
                continue

            return CapabilityStatusHit(
                matched_keyword=str(record.arguments.get("matched_keyword", "")),
                capability_name=capability_name,
                named_future_condition=named_future_condition,
            )

        return None

    @staticmethod
    def _build_azure_messages(prompt_envelope):
        return [
            {
                "role": "system",
                "content": prompt_envelope.stable_prefix,
            },
            {
                "role": "user",
                "content": prompt_envelope.variable_suffix,
            },
        ]
