"""Database CRUD for conversations and messages."""

from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.conversation import Conversation, Message


class ConversationDatasource:
    """Persistence-only access for conversation and message records."""

    def __init__(self, session: Session):
        self.session = session

    def get_conversation_by_id(self, conversation_id: uuid.UUID) -> Conversation | None:
        return (
            self.session.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )

    def get_conversation_by_session_id(self, session_id: uuid.UUID) -> Conversation | None:
        return (
            self.session.query(Conversation)
            .filter(Conversation.session_id == session_id)
            .order_by(Conversation.created_at.asc())
            .first()
        )

    def create_conversation(self, session_id: uuid.UUID) -> Conversation:
        conversation = Conversation(session_id=session_id)
        self.session.add(conversation)
        self.session.flush()
        self.session.refresh(conversation)
        return conversation

    def get_messages_by_conversation(self, conversation_id: uuid.UUID) -> list[Message]:
        return (
            self.session.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.turn_number.asc())
            .all()
        )

    def get_last_n_messages(
        self,
        conversation_id: uuid.UUID,
        limit: int,
    ) -> list[Message]:
        messages = (
            self.session.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.turn_number.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(messages))

    def get_next_turn_number(self, conversation_id: uuid.UUID) -> int:
        current_max = (
            self.session.query(func.max(Message.turn_number))
            .filter(Message.conversation_id == conversation_id)
            .scalar()
        )
        return (current_max or 0) + 1

    def create_message(
        self,
        *,
        conversation_id: uuid.UUID,
        turn_number: int,
        role: str,
        content: str,
        tool_calls=None,
        source_refs=None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            turn_number=turn_number,
            role=role,
            content=content,
            tool_calls=tool_calls,
            source_refs=source_refs,
        )
        self.session.add(message)
        self.session.flush()
        self.session.refresh(message)
        return message
