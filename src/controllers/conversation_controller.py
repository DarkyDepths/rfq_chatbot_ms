"""Conversation persistence orchestration for the chat turn pipeline."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from src.datasources.conversation_datasource import ConversationDatasource
from src.models.conversation import Conversation, Message
from src.utils.errors import NotFoundError


class ConversationController:
    """Owns conversation lookup/creation and message persistence."""

    def __init__(self, datasource: ConversationDatasource, session: Session):
        self.datasource = datasource
        self.session = session

    def get_conversation(self, conversation_id: uuid.UUID) -> Conversation:
        conversation = self.datasource.get_conversation_by_id(conversation_id)
        if not conversation:
            raise NotFoundError(f"Conversation '{conversation_id}' not found")
        return conversation

    def get_or_create_conversation_for_session(self, session_id: uuid.UUID) -> Conversation:
        """Return the single Phase 3-4 conversation for this session."""

        conversation = self.datasource.get_conversation_by_session_id(session_id)
        if conversation:
            return conversation

        conversation = self.datasource.create_conversation(session_id)
        self.session.commit()
        self.session.refresh(conversation)
        return conversation

    def get_conversation_with_messages(
        self,
        conversation_id: uuid.UUID,
    ) -> tuple[Conversation, list[Message]]:
        conversation = self.get_conversation(conversation_id)
        return conversation, self.datasource.get_messages_by_conversation(conversation_id)

    def get_messages(self, conversation_id: uuid.UUID) -> list[Message]:
        self.get_conversation(conversation_id)
        return self.datasource.get_messages_by_conversation(conversation_id)

    def get_recent_history(
        self,
        conversation_id: uuid.UUID,
        limit: int,
    ) -> list[Message]:
        self.get_conversation(conversation_id)
        return self.datasource.get_last_n_messages(conversation_id, limit)

    def create_user_message(self, conversation_id: uuid.UUID, content: str) -> Message:
        return self._create_message(conversation_id=conversation_id, role="user", content=content)

    def create_assistant_message(
        self,
        conversation_id: uuid.UUID,
        content: str,
        *,
        tool_calls=None,
        source_refs=None,
    ) -> Message:
        return self._create_message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            tool_calls=tool_calls,
            source_refs=source_refs,
        )

    def _create_message(
        self,
        *,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        tool_calls=None,
        source_refs=None,
    ) -> Message:
        self.get_conversation(conversation_id)
        turn_number = self.datasource.get_next_turn_number(conversation_id)
        message = self.datasource.create_message(
            conversation_id=conversation_id,
            turn_number=turn_number,
            role=role,
            content=content,
            tool_calls=tool_calls,
            source_refs=source_refs,
        )
        self.session.commit()
        self.session.refresh(message)
        return message
