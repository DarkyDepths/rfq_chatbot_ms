"""Phase 6 intent-routed turn orchestration controller."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import uuid
from types import SimpleNamespace

from src.connectors.azure_openai_connector import AzureOpenAIConnector
from src.connectors.manager_connector import ManagerRfqDetail
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
from src.tools.get_rfq_profile import GetRfqProfileInput, get_rfq_profile
from src.tools.get_rfq_snapshot import GetRfqSnapshotInput, get_rfq_snapshot
from src.translators.envelope_translator import (
    collect_source_refs,
    tool_call_records_to_prompt_blocks,
    tool_call_records_to_storage_payload,
)
from src.translators.chat_translator import to_turn_response
from src.utils.errors import NotFoundError, UpstreamServiceError, UpstreamTimeoutError


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreloadedRfqContext:
    """First-turn RFQ preload payload reused by later pipeline steps."""

    tool_call_records: list[ToolCallRecord]
    rfq_detail: ManagerRfqDetail | None = None


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

        recent_messages = self.conversation_controller.get_recent_history(conversation.id, limit=1)
        is_first_turn = len(recent_messages) == 0
        last_assistant_content = self._extract_last_assistant_content(recent_messages)
        last_resolved_intent = self._extract_last_resolved_intent(recent_messages)
        preloaded_rfq_context = self._maybe_preload_rfq_context(
            session=session,
            is_first_turn=is_first_turn,
        )

        intent_result = self.intent_controller.classify_intent(
            user_content=command.content,
            session=session,
            last_assistant_content=last_assistant_content,
            last_resolved_intent=last_resolved_intent,
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
                is_first_turn=is_first_turn,
                preloaded_rfq_context=preloaded_rfq_context,
            )

        if intent_result.intent == "general_knowledge":
            return self._handle_general_knowledge(
                session=session,
                conversation_id=conversation.id,
                command=command,
                preloaded_rfq_context=preloaded_rfq_context,
            )

        if intent_result.intent == "unsupported":
            return self._handle_unsupported(
                session=session,
                conversation_id=conversation.id,
                command=command,
                preloaded_rfq_context=preloaded_rfq_context,
            )

        if intent_result.intent == "disambiguation":
            return self._handle_disambiguation(
                session=session,
                conversation_id=conversation.id,
                command=command,
                preloaded_rfq_context=preloaded_rfq_context,
            )

        return self._handle_conversational(
            session=session,
            conversation_id=conversation.id,
            command=command,
            is_first_turn=is_first_turn,
            preloaded_rfq_context=preloaded_rfq_context,
        )

    def _handle_rfq_specific(
        self,
        *,
        session,
        conversation_id: uuid.UUID,
        command: TurnCreateCommand,
        intent_result: IntentClassification,
        is_first_turn: bool,
        preloaded_rfq_context: PreloadedRfqContext,
    ) -> TurnResponse:
        effective_session = self._build_request_scoped_session(
            session,
            intent_result=intent_result,
        )
        stage_resolution = self.stage_controller.resolve_stage(
            effective_session,
            preloaded_rfq_detail=preloaded_rfq_context.rfq_detail,
        )
        role_resolution = self.role_controller.resolve_role(session)
        self._log_role_resolution(role_resolution)

        if is_first_turn and self._is_greeting_turn(command.content):
            turn_guidance_lines = self._build_welcome_guidance_lines(
                session=effective_session,
                stage_resolution=stage_resolution,
            )
            return self._generate_and_persist_turn(
                conversation_id=conversation_id,
                latest_user_turn=command.content,
                stage_resolution=stage_resolution,
                role_resolution=role_resolution,
                tool_call_records=[],
                supplemental_tool_call_records=preloaded_rfq_context.tool_call_records,
                turn_guidance_lines=turn_guidance_lines,
            )

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

        all_tool_call_records = [
            *preloaded_rfq_context.tool_call_records,
            *tool_call_records,
        ]

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
            tool_call_records=all_tool_call_records,
            grounding_gap=grounding_gap,
            turn_guidance_lines=self._build_follow_up_guidance_lines(),
            intent="rfq_specific",
            apply_output_guardrail=True,
        )

    def _handle_general_knowledge(
        self,
        *,
        session,
        conversation_id: uuid.UUID,
        command: TurnCreateCommand,
        preloaded_rfq_context: PreloadedRfqContext,
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
        preloaded_rfq_context: PreloadedRfqContext,
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
        preloaded_rfq_context: PreloadedRfqContext,
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
        session,
        conversation_id: uuid.UUID,
        command: TurnCreateCommand,
        is_first_turn: bool,
        preloaded_rfq_context: PreloadedRfqContext,
    ) -> TurnResponse:
        turn_guidance_lines = None
        if is_first_turn and self._is_greeting_turn(command.content):
            turn_guidance_lines = self._build_welcome_guidance_lines(
                session=session,
                stage_resolution=None,
                preloaded_rfq_context=preloaded_rfq_context,
            )
            supplemental_tool_call_records = preloaded_rfq_context.tool_call_records
        else:
            supplemental_tool_call_records = []

        return self._generate_and_persist_turn(
            conversation_id=conversation_id,
            latest_user_turn=command.content,
            stage_resolution=None,
            role_resolution=None,
            tool_call_records=[],
            supplemental_tool_call_records=supplemental_tool_call_records,
            turn_guidance_lines=turn_guidance_lines,
        )

    def _generate_and_persist_turn(
        self,
        *,
        conversation_id: uuid.UUID,
        latest_user_turn: str,
        stage_resolution,
        role_resolution,
        tool_call_records,
        supplemental_tool_call_records=None,
        grounding_gap: bool = False,
        disambiguation_context: dict | None = None,
        turn_guidance_lines: list[str] | None = None,
        intent: str | None = None,
        apply_output_guardrail: bool = False,
    ) -> TurnResponse:

        supplemental_tool_call_records = supplemental_tool_call_records or []
        all_tool_call_records = [
            *supplemental_tool_call_records,
            *tool_call_records,
        ]

        recent_messages = self.conversation_controller.get_recent_history(
            conversation_id,
            max(self.context_builder.history_window_size - 1, 0),
        )
        self.conversation_controller.create_user_message(conversation_id, latest_user_turn)
        any_pattern_based_tool_fired = any(
            record.result is not None
            and record.result.confidence == ConfidenceLevel.PATTERN_1_SAMPLE
            for record in all_tool_call_records
        )
        capability_status_hit = self._extract_capability_status_hit(all_tool_call_records)
        prompt_envelope = self.context_builder.build(
            recent_messages,
            tool_call_records_to_prompt_blocks(all_tool_call_records),
            latest_user_turn=latest_user_turn,
            stage_resolution=stage_resolution,
            role_resolution=role_resolution,
            disambiguation_context=disambiguation_context,
            any_pattern_based_tool_fired=any_pattern_based_tool_fired,
            grounding_gap=grounding_gap,
            capability_status_hit=capability_status_hit,
            turn_guidance_lines=turn_guidance_lines,
            include_history_in_variable_suffix=False,
        )
        azure_messages = self._build_azure_messages(prompt_envelope, recent_messages)
        completion = self.azure_openai_connector.create_chat_completion(azure_messages)
        confidence_marker_emitted = CONFIDENCE_PATTERN_MARKER in completion.assistant_text
        logger.info(
            "phase5.confidence_marker_emitted=%s",
            confidence_marker_emitted,
            extra={"phase5.confidence_marker_emitted": confidence_marker_emitted},
        )
        source_refs = collect_source_refs(all_tool_call_records)
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
            tool_calls=tool_call_records_to_storage_payload(all_tool_call_records),
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

    @staticmethod
    def _extract_last_assistant_content(recent_messages) -> str | None:
        if not recent_messages:
            return None
        last_message = recent_messages[-1]
        if last_message.role != "assistant":
            return None
        return last_message.content

    @staticmethod
    def _extract_last_resolved_intent(recent_messages) -> str | None:
        if not recent_messages:
            return None

        last_message = recent_messages[-1]
        tool_calls = getattr(last_message, "tool_calls", None)
        if not tool_calls:
            return None

        for tool_call in tool_calls:
            tool_name = tool_call.get("tool_name") if isinstance(tool_call, dict) else None
            if tool_name == "get_capability_status":
                return "unsupported"
            if tool_name in {
                "get_rfq_profile",
                "get_rfq_stage",
                "get_rfq_snapshot",
                "retrieval_unavailable",
            }:
                return "rfq_specific"

        return None

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
    def _build_azure_messages(prompt_envelope, recent_messages):
        messages = [
            {
                "role": "system",
                "content": prompt_envelope.stable_prefix,
            }
        ]
        for message in recent_messages:
            role = str(getattr(message, "role", "")).lower()
            if role not in {"user", "assistant"}:
                continue
            messages.append(
                {
                    "role": role,
                    "content": getattr(message, "content", ""),
                }
            )
        messages.append(
            {
                "role": "user",
                "content": prompt_envelope.variable_suffix,
            }
        )
        return messages

    def _maybe_preload_rfq_context(
        self,
        *,
        session,
        is_first_turn: bool,
    ) -> PreloadedRfqContext:
        if not is_first_turn:
            return PreloadedRfqContext(tool_call_records=[])
        if self._session_mode_value(session) != SessionMode.RFQ_BOUND.value:
            return PreloadedRfqContext(tool_call_records=[])

        rfq_id = self._try_parse_uuid(getattr(session, "rfq_id", None))
        if rfq_id is None:
            return PreloadedRfqContext(tool_call_records=[])

        tool_call_records: list[ToolCallRecord] = []
        preloaded_rfq_detail: ManagerRfqDetail | None = None

        try:
            profile_result = get_rfq_profile(
                GetRfqProfileInput(rfq_id=rfq_id),
                self.tool_controller.manager_connector,
            )
            profile_source_refs = [profile_result.source_ref] if profile_result.source_ref else []
            tool_call_records.append(
                ToolCallRecord(
                    tool_name="get_rfq_profile",
                    arguments={
                        "rfq_id": str(rfq_id),
                        "selection_reason": "First-turn RFQ context preloading (profile)",
                    },
                    result=profile_result,
                    source_refs=profile_source_refs,
                )
            )
            if isinstance(profile_result.value, ManagerRfqDetail):
                preloaded_rfq_detail = profile_result.value
        except (NotFoundError, UpstreamTimeoutError, UpstreamServiceError, AssertionError):
            logger.info(
                "phase7.preload.profile_skipped=%s",
                True,
                extra={"phase7.preload.profile_skipped": True},
            )

        try:
            snapshot_result = get_rfq_snapshot(
                GetRfqSnapshotInput(rfq_id=rfq_id),
                self.tool_controller.intelligence_connector,
            )
            snapshot_source_refs = [snapshot_result.source_ref] if snapshot_result.source_ref else []
            tool_call_records.append(
                ToolCallRecord(
                    tool_name="get_rfq_snapshot",
                    arguments={
                        "rfq_id": str(rfq_id),
                        "selection_reason": "First-turn RFQ context preloading (snapshot)",
                    },
                    result=snapshot_result,
                    source_refs=snapshot_source_refs,
                )
            )
        except (NotFoundError, UpstreamTimeoutError, UpstreamServiceError, AssertionError):
            logger.info(
                "phase7.preload.snapshot_skipped=%s",
                True,
                extra={"phase7.preload.snapshot_skipped": True},
            )

        return PreloadedRfqContext(
            tool_call_records=tool_call_records,
            rfq_detail=preloaded_rfq_detail,
        )

    @staticmethod
    def _session_mode_value(session) -> str:
        mode = getattr(session, "mode", None)
        if isinstance(mode, SessionMode):
            return mode.value
        return str(mode)

    @staticmethod
    def _try_parse_uuid(value: str | None) -> uuid.UUID | None:
        if not value:
            return None
        try:
            return uuid.UUID(str(value))
        except ValueError:
            return None

    @staticmethod
    def _is_greeting_turn(content: str) -> bool:
        normalized = content.strip().lower()
        if not normalized:
            return False
        greeting_prefixes = (
            "hi",
            "hello",
            "hey",
            "good morning",
            "good afternoon",
            "good evening",
            "salam",
        )
        return any(normalized.startswith(prefix) for prefix in greeting_prefixes)

    def _build_welcome_guidance_lines(
        self,
        *,
        session,
        stage_resolution,
        preloaded_rfq_context: PreloadedRfqContext | None = None,
    ) -> list[str]:
        if self._session_mode_value(session) != SessionMode.RFQ_BOUND.value:
            return [
                "This is a first-turn conversational greeting in portfolio mode.",
                "Reply with a concise, warm welcome tailored for portfolio-wide support.",
                "Offer 1-2 concrete next actions the user can ask about across RFQs.",
            ]

        rfq_detail = None
        if stage_resolution is not None:
            rfq_detail = getattr(stage_resolution, "rfq_detail", None)
        if rfq_detail is None and preloaded_rfq_context is not None:
            rfq_detail = preloaded_rfq_context.rfq_detail

        rfq_name = getattr(rfq_detail, "name", None) if rfq_detail is not None else None
        client_name = getattr(rfq_detail, "client", None) if rfq_detail is not None else None
        stage_name = getattr(rfq_detail, "current_stage_name", None) if rfq_detail is not None else None

        return [
            "This is a first-turn conversational greeting in RFQ-bound mode.",
            "Reply with a concise, warm welcome that acknowledges the current RFQ context.",
            f"RFQ name: {rfq_name or 'Unavailable'}",
            f"Client: {client_name or 'Unavailable'}",
            f"Current stage: {stage_name or 'Unavailable'}",
            "Offer 1-2 concrete next actions relevant to the RFQ context.",
        ]

    @staticmethod
    def _build_follow_up_guidance_lines() -> list[str]:
        return [
            "End the response with 1-2 contextual follow-up suggestions.",
            "Keep follow-up suggestions grounded in retrieved RFQ facts and current stage context.",
            "When facts are insufficient, suggest precise clarifying follow-up questions instead.",
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
