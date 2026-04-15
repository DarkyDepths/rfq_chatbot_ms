"""Phase 4 turn orchestration controller."""

from __future__ import annotations

import uuid

from src.connectors.azure_openai_connector import AzureOpenAIConnector
from src.controllers.context_builder import ContextBuilder
from src.controllers.conversation_controller import ConversationController
from src.controllers.tool_controller import ToolController
from src.datasources.session_datasource import SessionDatasource
from src.models.turn import TurnCreateCommand, TurnResponse
from src.translators.envelope_translator import (
    collect_source_refs,
    tool_call_records_to_prompt_blocks,
    tool_call_records_to_storage_payload,
)
from src.translators.chat_translator import to_turn_response
from src.utils.errors import NotFoundError


class ChatController:
    """Owns the first conversational vertical slice."""

    def __init__(
        self,
        session_datasource: SessionDatasource,
        conversation_controller: ConversationController,
        context_builder: ContextBuilder,
        azure_openai_connector: AzureOpenAIConnector,
        tool_controller: ToolController,
    ):
        self.session_datasource = session_datasource
        self.conversation_controller = conversation_controller
        self.context_builder = context_builder
        self.azure_openai_connector = azure_openai_connector
        self.tool_controller = tool_controller

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
        self.conversation_controller.create_user_message(conversation.id, command.content)
        tool_call_records = self.tool_controller.maybe_execute_retrieval(
            session,
            command.content,
        )

        recent_messages = self.conversation_controller.get_recent_history(
            conversation.id,
            self.context_builder.history_window_size,
        )
        prompt_envelope = self.context_builder.build(
            recent_messages,
            tool_call_records_to_prompt_blocks(tool_call_records),
        )
        azure_messages = self._build_azure_messages(prompt_envelope)
        completion = self.azure_openai_connector.create_chat_completion(azure_messages)
        assistant_message = self.conversation_controller.create_assistant_message(
            conversation.id,
            completion.assistant_text,
            tool_calls=tool_call_records_to_storage_payload(tool_call_records),
            source_refs=collect_source_refs(tool_call_records),
        )

        return to_turn_response(conversation.id, assistant_message)

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
