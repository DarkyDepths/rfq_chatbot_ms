"""Thin request/response translation for session and chat routes."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.models.envelope import SourceRef
from src.models.session import (
    ChatbotSession,
    ChatbotSessionRead,
    SessionBindCommand,
    SessionCreateCommand,
    SessionEntryMode,
)
from src.models.turn import (
    ConversationMessageRead,
    ConversationReadResponse,
    TurnCreateCommand,
    TurnRequest,
    TurnResponse,
)


class SessionCreateRequest(BaseModel):
    """External request contract for creating a session."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: str = Field(min_length=1)
    mode: SessionEntryMode
    rfq_id: str | None = None
    role: str | None = None


class SessionBindRequest(BaseModel):
    """Explicit minimal pivot request for binding a session to one RFQ."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rfq_id: str = Field(min_length=1)


def to_session_create_command(request: SessionCreateRequest) -> SessionCreateCommand:
    """Translate the HTTP create payload into a domain command."""

    return SessionCreateCommand(
        user_id=request.user_id,
        entry_mode=request.mode,
        rfq_id=request.rfq_id,
        role=request.role,
    )


def to_session_bind_command(request: SessionBindRequest) -> SessionBindCommand:
    """Translate the HTTP bind payload into a domain command."""

    return SessionBindCommand(rfq_id=request.rfq_id)


def to_session_response(chatbot_session: ChatbotSession) -> ChatbotSessionRead:
    """Return the Phase 1 read DTO as the API response model."""

    return ChatbotSessionRead.model_validate(chatbot_session)


def to_turn_create_command(request: TurnRequest) -> TurnCreateCommand:
    """Translate the HTTP turn payload into a domain command."""

    return TurnCreateCommand(content=request.content)


def to_turn_response(
    conversation_id,
    assistant_message,
) -> TurnResponse:
    """Translate a persisted assistant message into the turn response contract."""

    return TurnResponse(
        conversation_id=conversation_id,
        turn_number=assistant_message.turn_number,
        role=assistant_message.role,
        content=assistant_message.content,
        source_refs=_to_source_refs(assistant_message.source_refs),
    )


def to_conversation_read_response(conversation, messages) -> ConversationReadResponse:
    """Translate a conversation aggregate into the readback contract."""

    return ConversationReadResponse(
        conversation_id=conversation.id,
        session_id=conversation.session_id,
        messages=[
            ConversationMessageRead(
                id=message.id,
                turn_number=message.turn_number,
                role=message.role,
                content=message.content,
                source_refs=_to_source_refs(message.source_refs),
                timestamp=message.timestamp,
            )
            for message in messages
        ],
    )


def _to_source_refs(source_refs) -> list[SourceRef]:
    if not source_refs:
        return []

    return [SourceRef.model_validate(source_ref) for source_ref in source_refs]
