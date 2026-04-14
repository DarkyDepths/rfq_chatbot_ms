"""Minimal request/response translation for Phase 2 session routes."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.models.session import (
    ChatbotSession,
    ChatbotSessionRead,
    SessionBindCommand,
    SessionCreateCommand,
    SessionEntryMode,
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
