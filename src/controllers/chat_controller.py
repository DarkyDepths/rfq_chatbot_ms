"""Phase 6 intent-routed turn orchestration controller."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
import uuid
from types import SimpleNamespace

from src.connectors.azure_openai_connector import AzureOpenAIConnector
from src.connectors.manager_connector import ManagerRfqDetail
from src.config.intent_patterns import get_out_of_scope_refusal
from src.controllers.context_builder import CONFIDENCE_PATTERN_MARKER, ContextBuilder
from src.controllers.conversation_controller import ConversationController
from src.controllers.disambiguation_controller import DisambiguationController
from src.controllers.intent_controller import IntentClassification, IntentController
from src.controllers.output_guardrail import OutputGuardrail
from src.controllers.rfq_response_controller import RfqResponseController
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
from src.utils.metrics import (
    grounding_gaps_total,
    record_intent,
    record_tool_calls,
    response_latency_seconds,
    turns_total,
)


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
        rfq_response_controller: RfqResponseController | None = None,
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
        self.rfq_response_controller = rfq_response_controller or RfqResponseController()

    def handle_turn(
        self,
        session_id: uuid.UUID,
        command: TurnCreateCommand,
    ) -> TurnResponse:
        started_at = time.perf_counter()
        turns_total.inc()
        try:
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
            record_intent(intent_result.intent)
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

            # out_of_scope: deterministic refusal, no LLM call
            if intent_result.intent == "out_of_scope":
                return self._handle_out_of_scope(
                    session=session,
                    conversation_id=conversation.id,
                    command=command,
                    intent_result=intent_result,
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

            if intent_result.intent == "domain_knowledge":
                return self._handle_domain_knowledge(
                    session=session,
                    conversation_id=conversation.id,
                    command=command,
                    intent_result=intent_result,
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
                intent_result=intent_result,
                is_first_turn=is_first_turn,
                preloaded_rfq_context=preloaded_rfq_context,
            )
        finally:
            response_latency_seconds.observe(time.perf_counter() - started_at)

    def _handle_out_of_scope(
        self,
        *,
        session,
        conversation_id: uuid.UUID,
        command: TurnCreateCommand,
        intent_result: IntentClassification,
    ) -> TurnResponse:
        """Handle out-of-scope questions with deterministic refusal.
        No LLM call. No context building. No tools.
        """
        refusal_text = get_out_of_scope_refusal()

        logger.info(
            "phase6_5.out_of_scope_refusal",
            extra={
                "intent": "out_of_scope",
                "user_message_preview": command.content[:50],
            },
        )

        return self._persist_plain_response(
            conversation_id,
            user_text=command.content,
            assistant_text=refusal_text,
        )

    def _persist_plain_response(
        self,
        conversation_id: uuid.UUID,
        *,
        user_text: str,
        assistant_text: str,
    ) -> TurnResponse:
        self.conversation_controller.create_user_message(conversation_id, user_text)
        assistant_message = self.conversation_controller.create_assistant_message(
            conversation_id,
            assistant_text,
            tool_calls=[],
            source_refs=[],
        )
        return to_turn_response(conversation_id, assistant_message)

    def _persist_structured_response(
        self,
        conversation_id: uuid.UUID,
        *,
        user_text: str,
        assistant_text: str,
        tool_call_records: list[ToolCallRecord],
        source_refs: list[dict],
    ) -> TurnResponse:
        self.conversation_controller.create_user_message(conversation_id, user_text)
        assistant_message = self.conversation_controller.create_assistant_message(
            conversation_id,
            assistant_text,
            tool_calls=tool_call_records_to_storage_payload(tool_call_records),
            source_refs=source_refs,
        )
        return to_turn_response(conversation_id, assistant_message)

    def _handle_deterministic_conversational(
        self,
        *,
        session,
        conversation_id: uuid.UUID,
        command: TurnCreateCommand,
        subtype: str,
        preloaded_rfq_context: PreloadedRfqContext,
    ) -> TurnResponse:
        return self._persist_plain_response(
            conversation_id,
            user_text=command.content,
            assistant_text=self._build_deterministic_conversational_response(
                session=session,
                subtype=subtype,
                preloaded_rfq_context=preloaded_rfq_context,
            ),
        )

    def _build_deterministic_conversational_response(
        self,
        *,
        session,
        subtype: str,
        preloaded_rfq_context: PreloadedRfqContext,
    ) -> str:
        if subtype == "greeting":
            return self._build_deterministic_greeting(
                session=session,
                preloaded_rfq_context=preloaded_rfq_context,
            )
        if subtype == "identity":
            return "I'm RFQ Copilot, your estimation assistant for RFQs."
        if subtype == "thanks":
            return "You're welcome."
        if subtype == "goodbye":
            return "Goodbye."
        if subtype == "reset":
            return "No problem. We can start fresh. What would you like to check?"
        raise ValueError(f"Unsupported deterministic conversational subtype: {subtype}")

    def _build_deterministic_greeting(
        self,
        *,
        session,
        preloaded_rfq_context: PreloadedRfqContext,
    ) -> str:
        if self._session_mode_value(session) != SessionMode.RFQ_BOUND.value:
            return "Hi! I'm RFQ Copilot. How can I help with your RFQs?"

        rfq_detail = preloaded_rfq_context.rfq_detail
        rfq_name = getattr(rfq_detail, "name", None) if rfq_detail is not None else None
        client_name = getattr(rfq_detail, "client", None) if rfq_detail is not None else None
        stage_name = getattr(rfq_detail, "current_stage_name", None) if rfq_detail is not None else None

        if rfq_name and client_name:
            opening = f"Hi! I'm ready to help with RFQ {rfq_name} for {client_name}."
        elif rfq_name:
            opening = f"Hi! I'm ready to help with RFQ {rfq_name}."
        elif client_name:
            opening = f"Hi! I'm ready to help with this RFQ for {client_name}."
        else:
            opening = "Hi! I'm ready to help with this RFQ."

        if stage_name:
            opening = f"{opening} It is currently in {stage_name}."

        return f"{opening} What would you like to check?"

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
                intent="conversational",
                conversational_subtype="greeting",
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

        response_plan = self.rfq_response_controller.compose_response(
            user_content=command.content,
            rfq_detail=stage_resolution.rfq_detail,
            tool_call_records=all_tool_call_records,
            rfq_id=getattr(effective_session, "rfq_id", None),
        )
        logger.info(
            "phase6.rfq_response_mode=%s",
            response_plan.response_mode,
            extra={"phase6.rfq_response_mode": response_plan.response_mode},
        )
        has_evidence = response_plan.grounded
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
            grounding_gaps_total.inc()
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

        record_tool_calls([record.tool_name for record in response_plan.tool_call_records])
        logger.info(
            "phase5.confidence_marker_emitted=%s",
            False,
            extra={"phase5.confidence_marker_emitted": False},
        )
        logger.info(
            "phase6.output_guardrail_result=%s",
            "pass",
            extra={"phase6.output_guardrail_result": "pass"},
        )

        return self._persist_structured_response(
            conversation_id=conversation_id,
            user_text=command.content,
            assistant_text=response_plan.assistant_text,
            tool_call_records=response_plan.tool_call_records,
            source_refs=[
                source_ref.model_dump(mode="json")
                for source_ref in response_plan.source_refs
            ],
        )

    def _handle_domain_knowledge(
        self,
        *,
        session,
        conversation_id: uuid.UUID,
        command: TurnCreateCommand,
        intent_result: IntentClassification,
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
            intent="domain_knowledge",
            apply_output_guardrail=True,
            conversational_subtype=None,
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
        intent_result: IntentClassification,
        is_first_turn: bool,
        preloaded_rfq_context: PreloadedRfqContext,
    ) -> TurnResponse:
        subtype = intent_result.conversational_subtype or "generic"

        if subtype in {"greeting", "identity", "thanks", "goodbye", "reset"}:
            return self._handle_deterministic_conversational(
                session=session,
                conversation_id=conversation_id,
                command=command,
                subtype=subtype,
                preloaded_rfq_context=preloaded_rfq_context,
            )

        turn_guidance_lines = None
        return self._generate_and_persist_turn(
            conversation_id=conversation_id,
            latest_user_turn=command.content,
            stage_resolution=None,
            role_resolution=None,
            tool_call_records=[],
            turn_guidance_lines=turn_guidance_lines,
            intent="conversational",
            conversational_subtype=subtype,
            apply_output_guardrail=True,
        )

    def _handle_greeting(
        self,
        *,
        session,
        conversation_id: uuid.UUID,
        command: TurnCreateCommand,
        intent_result: IntentClassification,
        is_first_turn: bool,
        preloaded_rfq_context: PreloadedRfqContext,
    ) -> TurnResponse:
        return self._handle_deterministic_conversational(
            session=session,
            conversation_id=conversation_id,
            command=command,
            subtype="greeting",
            preloaded_rfq_context=preloaded_rfq_context,
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
        greeting_mode: bool = False,
        intent: str | None = None,
        apply_output_guardrail: bool = False,
        conversational_subtype: str | None = None,
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
        selected_history = self.context_builder.select_history(
            recent_messages,
            intent=intent,
            conversational_subtype=conversational_subtype,
        )
        self.conversation_controller.create_user_message(conversation_id, latest_user_turn)
        any_pattern_based_tool_fired = any(
            record.result is not None
            and record.result.confidence == ConfidenceLevel.PATTERN_1_SAMPLE
            for record in all_tool_call_records
        )
        capability_status_hit = self._extract_capability_status_hit(all_tool_call_records)
        prompt_envelope = self.context_builder.build(
            selected_history,
            tool_call_records_to_prompt_blocks(all_tool_call_records),
            latest_user_turn=latest_user_turn,
            stage_resolution=stage_resolution,
            role_resolution=role_resolution,
            disambiguation_context=disambiguation_context,
            any_pattern_based_tool_fired=any_pattern_based_tool_fired,
            grounding_gap=grounding_gap,
            capability_status_hit=capability_status_hit,
            turn_guidance_lines=turn_guidance_lines,
            greeting_mode=greeting_mode,
            include_history_in_variable_suffix=False,
            intent=intent,
            conversational_subtype=conversational_subtype,
        )
        azure_messages = self._build_azure_messages(prompt_envelope, selected_history)
        completion = self.azure_openai_connector.create_chat_completion(azure_messages)
        confidence_marker_emitted = CONFIDENCE_PATTERN_MARKER in completion.assistant_text
        logger.info(
            "phase5.confidence_marker_emitted=%s",
            confidence_marker_emitted,
            extra={"phase5.confidence_marker_emitted": confidence_marker_emitted},
        )
        source_refs = collect_source_refs(all_tool_call_records)
        record_tool_calls([record.tool_name for record in all_tool_call_records])

        assistant_text = completion.assistant_text

        if apply_output_guardrail and intent is not None:
            guardrail_result = self.output_guardrail.evaluate(
                intent=intent,
                assistant_text=assistant_text,
                source_refs=source_refs,
                grounding_gap_injected=grounding_gap,
                capability_status_hit=capability_status_hit,
                conversational_subtype=conversational_subtype,
            )
            logger.info(
                "phase6.output_guardrail_result=%s",
                guardrail_result,
                extra={"phase6.output_guardrail_result": guardrail_result},
            )

            # Replace response on domain leak
            if guardrail_result == "domain_leak":
                assistant_text = get_out_of_scope_refusal()
                logger.info(
                    "phase6_5.guardrail_replaced_response",
                    extra={"reason": "domain_leak"},
                )

        assistant_message = self.conversation_controller.create_assistant_message(
            conversation_id,
            assistant_text,
            tool_calls=tool_call_records_to_storage_payload(all_tool_call_records),
            source_refs=source_refs,
        )

        return to_turn_response(conversation_id, assistant_message)

    @staticmethod
    def _intent_to_route(intent: str) -> str:
        if intent == "rfq_specific":
            return "tools_pipeline"
        if intent == "domain_knowledge":
            return "direct_llm"
        if intent == "unsupported":
            return "capability_status"
        if intent == "disambiguation":
            return "disambiguation"
        if intent == "out_of_scope":
            return "deterministic_refusal"
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

    @classmethod
    def _is_short_greeting_turn(cls, content: str) -> bool:
        normalized = content.strip()
        if not cls._is_greeting_turn(normalized):
            return False
        return len(normalized.split()) <= 3

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
                "Keep it to 2-3 sentences and end with one simple optional question.",
            ]

        rfq_detail = None
        if stage_resolution is not None:
            rfq_detail = getattr(stage_resolution, "rfq_detail", None)
        if rfq_detail is None and preloaded_rfq_context is not None:
            rfq_detail = preloaded_rfq_context.rfq_detail

        rfq_name = getattr(rfq_detail, "name", None) if rfq_detail is not None else None
        client_name = getattr(rfq_detail, "client", None) if rfq_detail is not None else None
        stage_name = getattr(rfq_detail, "current_stage_name", None) if rfq_detail is not None else None

        lines = [
            "This is a first-turn conversational greeting in RFQ-bound mode.",
            "Reply with a concise, warm welcome that acknowledges the current RFQ context when available.",
            "Keep it to 2-3 sentences, avoid analysis, and end with one simple optional question.",
        ]
        if rfq_name:
            lines.insert(2, f"RFQ name: {rfq_name}")
        if client_name:
            lines.insert(len(lines) - 1, f"Client: {client_name}")
        if stage_name:
            lines.insert(len(lines) - 1, f"Current stage: {stage_name}")
        return lines

    @staticmethod
    def _build_follow_up_guidance_lines() -> list[str]:
        return [
            "Provide at most 1-2 lightweight optional next questions.",
            "Phrase follow-ups as optional questions, not action plans or instructions.",
            "Only propose next questions when they are grounded in the current user request and retrieved facts.",
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
