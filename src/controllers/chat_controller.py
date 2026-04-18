"""Phase 6 intent-routed turn orchestration controller."""

from __future__ import annotations

import logging
import uuid
from types import SimpleNamespace

from src.connectors.azure_openai_connector import AzureOpenAIConnector
from src.controllers.context_builder import CONFIDENCE_PATTERN_MARKER, ContextBuilder
from src.controllers.conversation_controller import ConversationController
from src.controllers.disambiguation_controller import DisambiguationController
from src.controllers.intent_controller import IntentClassification, IntentController
from src.controllers.output_guardrail import OutputGuardrail
from src.controllers.role_controller import RoleController
from src.controllers.stage_controller import StageController
from src.controllers.tool_controller import CapabilityStatusHit, ToolController
from src.datasources.session_datasource import SessionDatasource
from src.models.conversation import ToolCallRecord
from src.models.envelope import ConfidenceLevel, ToolResultEnvelope
from src.models.session import SessionMode
from src.models.turn import TurnCreateCommand, TurnResponse
from src.translators.envelope_translator import (
    collect_source_refs,
    tool_call_records_to_prompt_blocks,
    tool_call_records_to_storage_payload,
)
from src.translators.chat_translator import to_turn_response
from src.utils.errors import NotFoundError, UpstreamServiceError, UpstreamTimeoutError


logger = logging.getLogger(__name__)


class ChatController:
    """Owns the Phase 6 conversational turn pipeline."""

    def __init__(
        self,
        session_datasource: SessionDatasource,
        conversation_controller: ConversationController,
        context_builder: ContextBuilder,
        azure_openai_connector: AzureOpenAIConnector,
        tool_controller: ToolController,
        stage_controller: StageController,
        role_controller: RoleController,
        intent_controller: IntentController,
        disambiguation_controller: DisambiguationController,
        output_guardrail: OutputGuardrail | None = None,
    ):
        self.session_datasource = session_datasource
        self.conversation_controller = conversation_controller
        self.context_builder = context_builder
        self.azure_openai_connector = azure_openai_connector
        self.tool_controller = tool_controller
        self.stage_controller = stage_controller
        self.role_controller = role_controller
        self.intent_controller = intent_controller
        self.disambiguation_controller = disambiguation_controller
        self.output_guardrail = output_guardrail or OutputGuardrail()

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

        last_assistant_content = self._get_last_assistant_content(conversation.id)
        intent_result = self.intent_controller.classify_intent(
            user_content=command.content,
            session=session,
            last_assistant_content=last_assistant_content,
        )
        route = self._intent_to_route(intent_result.intent)
        logger.info(
            "phase6.intent_classified=%s",
            intent_result.intent,
            extra={"phase6.intent_classified": intent_result.intent},
        )
        logger.info(
            "phase6.route_selected=%s",
            route,
            extra={"phase6.route_selected": route},
        )
        if intent_result.disambiguation_resolved:
            logger.info(
                "phase6.disambiguation_resolved=%s",
                intent_result.resolved_rfq_reference,
                extra={"phase6.disambiguation_resolved": intent_result.resolved_rfq_reference},
            )
        if intent_result.disambiguation_abandoned:
            logger.info(
                "phase6.disambiguation_abandoned=%s",
                True,
                extra={"phase6.disambiguation_abandoned": True},
            )

        if intent_result.intent == "rfq_specific":
            return self._handle_rfq_specific(
                session=session,
                conversation_id=conversation.id,
                command=command,
                intent_result=intent_result,
            )

        if intent_result.intent == "general_knowledge":
            return self._handle_general_knowledge(
                session=session,
                conversation_id=conversation.id,
                command=command,
            )

        if intent_result.intent == "unsupported":
            return self._handle_unsupported(
                session=session,
                conversation_id=conversation.id,
                command=command,
            )

        if intent_result.intent == "disambiguation":
            return self._handle_disambiguation(
                session=session,
                conversation_id=conversation.id,
                command=command,
            )

        return self._handle_conversational(
            conversation_id=conversation.id,
            command=command,
        )

    def _handle_rfq_specific(
        self,
        *,
        session,
        conversation_id: uuid.UUID,
        command: TurnCreateCommand,
        intent_result: IntentClassification,
    ) -> TurnResponse:
        effective_session = self._build_request_scoped_session(
            session,
            intent_result=intent_result,
        )
        stage_resolution = self.stage_controller.resolve_stage(effective_session)
        role_resolution = self.role_controller.resolve_role(session)
        self._log_role_resolution(role_resolution)

        try:
            tool_call_records = self.tool_controller.maybe_execute_retrieval(
                effective_session,
                command.content,
                stage_profile=stage_resolution.profile,
                role_profile=role_resolution.profile,
                preloaded_rfq_detail=stage_resolution.rfq_detail,
            )
        except (UpstreamServiceError, UpstreamTimeoutError) as exc:
            tool_call_records = [self._build_retrieval_failure_record(exc)]

        has_evidence = any(
            record.result is not None
            and record.result.confidence != ConfidenceLevel.ABSENT
            and record.result.source_ref is not None
            for record in tool_call_records
        )
        grounding_gap = not has_evidence
        tool_planner_fired = len(tool_call_records) > 0

        logger.info(
            "phase6.grounding_required=%s",
            True,
            extra={"phase6.grounding_required": True},
        )
        logger.info(
            "phase6.grounding_satisfied=%s",
            has_evidence,
            extra={"phase6.grounding_satisfied": has_evidence},
        )
        if grounding_gap:
            if not tool_planner_fired:
                logger.info(
                    "phase6.grounding_mismatch=%s",
                    True,
                    extra={"phase6.grounding_mismatch": True},
                )
            logger.info(
                "phase6.grounding_gap_absence_injected=%s",
                True,
                extra={"phase6.grounding_gap_absence_injected": True},
            )

        return self._generate_and_persist_turn(
            conversation_id=conversation_id,
            latest_user_turn=command.content,
            stage_resolution=stage_resolution,
            role_resolution=role_resolution,
            tool_call_records=tool_call_records,
            grounding_gap=grounding_gap,
            intent="rfq_specific",
            apply_output_guardrail=True,
        )

    def _handle_general_knowledge(
        self,
        *,
        session,
        conversation_id: uuid.UUID,
        command: TurnCreateCommand,
    ) -> TurnResponse:
        role_resolution = self.role_controller.resolve_role(session)
        self._log_role_resolution(role_resolution)

        return self._generate_and_persist_turn(
            conversation_id=conversation_id,
            latest_user_turn=command.content,
            stage_resolution=None,
            role_resolution=role_resolution,
            tool_call_records=[],
        )

    def _handle_unsupported(
        self,
        *,
        session,
        conversation_id: uuid.UUID,
        command: TurnCreateCommand,
    ) -> TurnResponse:
        role_resolution = self.role_controller.resolve_role(session)
        self._log_role_resolution(role_resolution)

        tool_call_records = self.tool_controller.maybe_execute_retrieval(
            session,
            command.content,
            role_profile=role_resolution.profile,
        )

        return self._generate_and_persist_turn(
            conversation_id=conversation_id,
            latest_user_turn=command.content,
            stage_resolution=None,
            role_resolution=role_resolution,
            tool_call_records=tool_call_records,
            intent="unsupported",
            apply_output_guardrail=True,
        )

    def _handle_disambiguation(
        self,
        *,
        session,
        conversation_id: uuid.UUID,
        command: TurnCreateCommand,
    ) -> TurnResponse:
        role_resolution = self.role_controller.resolve_role(session)
        self._log_role_resolution(role_resolution)
        disambiguation_context = self.disambiguation_controller.build_disambiguation_context(
            user_content=command.content,
            role_resolution=role_resolution,
        )
        logger.info(
            "phase6.disambiguation_triggered=%s",
            True,
            extra={"phase6.disambiguation_triggered": True},
        )

        return self._generate_and_persist_turn(
            conversation_id=conversation_id,
            latest_user_turn=command.content,
            stage_resolution=None,
            role_resolution=role_resolution,
            tool_call_records=[],
            disambiguation_context=disambiguation_context,
            intent="disambiguation",
            apply_output_guardrail=True,
        )

    def _handle_conversational(
        self,
        *,
        conversation_id: uuid.UUID,
        command: TurnCreateCommand,
    ) -> TurnResponse:
        return self._generate_and_persist_turn(
            conversation_id=conversation_id,
            latest_user_turn=command.content,
            stage_resolution=None,
            role_resolution=None,
            tool_call_records=[],
        )

    def _generate_and_persist_turn(
        self,
        *,
        conversation_id: uuid.UUID,
        latest_user_turn: str,
        stage_resolution,
        role_resolution,
        tool_call_records,
        grounding_gap: bool = False,
        disambiguation_context: dict | None = None,
        intent: str | None = None,
        apply_output_guardrail: bool = False,
    ) -> TurnResponse:

        recent_messages = self.conversation_controller.get_recent_history(
            conversation_id,
            max(self.context_builder.history_window_size - 1, 0),
        )
        self.conversation_controller.create_user_message(conversation_id, latest_user_turn)
        any_pattern_based_tool_fired = any(
            record.result is not None
            and record.result.confidence == ConfidenceLevel.PATTERN_1_SAMPLE
            for record in tool_call_records
        )
        capability_status_hit = self._extract_capability_status_hit(tool_call_records)
        prompt_envelope = self.context_builder.build(
            recent_messages,
            tool_call_records_to_prompt_blocks(tool_call_records),
            latest_user_turn=latest_user_turn,
            stage_resolution=stage_resolution,
            role_resolution=role_resolution,
            disambiguation_context=disambiguation_context,
            any_pattern_based_tool_fired=any_pattern_based_tool_fired,
            grounding_gap=grounding_gap,
            capability_status_hit=capability_status_hit,
        )
        azure_messages = self._build_azure_messages(prompt_envelope)
        completion = self.azure_openai_connector.create_chat_completion(azure_messages)
        confidence_marker_emitted = CONFIDENCE_PATTERN_MARKER in completion.assistant_text
        logger.info(
            "phase5.confidence_marker_emitted=%s",
            confidence_marker_emitted,
            extra={"phase5.confidence_marker_emitted": confidence_marker_emitted},
        )
        source_refs = collect_source_refs(tool_call_records)
        if apply_output_guardrail and intent is not None:
            guardrail_result = self.output_guardrail.evaluate(
                intent=intent,
                assistant_text=completion.assistant_text,
                source_refs=source_refs,
                grounding_gap_injected=grounding_gap,
                capability_status_hit=capability_status_hit,
            )
            logger.info(
                "phase6.output_guardrail_result=%s",
                guardrail_result,
                extra={"phase6.output_guardrail_result": guardrail_result},
            )
        assistant_message = self.conversation_controller.create_assistant_message(
            conversation_id,
            completion.assistant_text,
            tool_calls=tool_call_records_to_storage_payload(tool_call_records),
            source_refs=source_refs,
        )

        return to_turn_response(conversation_id, assistant_message)

    @staticmethod
    def _intent_to_route(intent: str) -> str:
        if intent == "rfq_specific":
            return "tools_pipeline"
        if intent == "general_knowledge":
            return "direct_llm"
        if intent == "unsupported":
            return "capability_status"
        if intent == "disambiguation":
            return "disambiguation"
        return "conversational"

    def _get_last_assistant_content(self, conversation_id: uuid.UUID) -> str | None:
        recent = self.conversation_controller.get_recent_history(conversation_id, limit=1)
        if not recent:
            return None
        last_message = recent[-1]
        if last_message.role != "assistant":
            return None
        return last_message.content

    @staticmethod
    def _build_request_scoped_session(session, *, intent_result: IntentClassification):
        if not intent_result.disambiguation_resolved or not intent_result.resolved_rfq_reference:
            return session

        return SimpleNamespace(
            id=session.id,
            mode=SessionMode.RFQ_BOUND,
            rfq_id=intent_result.resolved_rfq_reference,
            role=session.role,
        )

    @staticmethod
    def _log_role_resolution(role_resolution) -> None:
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

    @staticmethod
    def _build_retrieval_failure_record(exc: Exception) -> ToolCallRecord:
        """Wrap an upstream retrieval failure as an ABSENT tool record.

        This converts the exception into a tool call record so that the
        grounding check can detect the failure case (tool_planner_fired=True,
        has_evidence=False) without special-casing the exception path.
        The ABSENT confidence ensures has_evidence evaluates to False,
        triggering grounding-gap absence injection.
        """
        return ToolCallRecord(
            tool_name="retrieval_unavailable",
            arguments={
                "selection_reason": "RFQ retrieval was attempted but upstream failed",
                "error_type": type(exc).__name__,
            },
            result=ToolResultEnvelope(
                value={"error": str(exc)},
                confidence=ConfidenceLevel.ABSENT,
            ),
            source_refs=[],
        )
