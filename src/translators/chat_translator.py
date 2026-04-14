"""Minimal request/response translation for Phase 2 session routes."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from src.models.session import ChatbotSession, ChatbotSessionRead


class SessionRequestMode(str, Enum):
    """External session entry modes exposed by the Phase 2 API."""

    RFQ = "rfq"
    GLOBAL = "global"


class SessionCreateRequest(BaseModel):
    """External request contract for creating a session."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: str = Field(min_length=1)
    mode: SessionRequestMode
    rfq_id: str | None = None
    role: str | None = None


class SessionBindRequest(BaseModel):
    """Explicit minimal pivot request for binding a session to one RFQ."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rfq_id: str = Field(min_length=1)


def to_session_response(chatbot_session: ChatbotSession) -> ChatbotSessionRead:
    """Return the Phase 1 read DTO as the API response model."""

    return ChatbotSessionRead.model_validate(chatbot_session)
