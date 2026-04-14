"""Session contracts and persistence model for rfq_chatbot_ms."""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, DateTime, Enum as SqlEnum, String, Uuid
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.database import Base


class SessionMode(str, Enum):
    """Supported chatbot session modes."""

    RFQ_BOUND = "rfq_bound"
    PORTFOLIO = "portfolio"
    PENDING_PIVOT = "pending_pivot"


class SessionEntryMode(str, Enum):
    """External business entry modes accepted during session creation."""

    RFQ = "rfq"
    GLOBAL = "global"


class ChatbotSession(Base):
    """Conversation scope persisted for future chat turns."""

    __tablename__ = "chatbot_sessions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    rfq_id = Column(String(255), nullable=True, index=True)
    mode = Column(
        SqlEnum(SessionMode, name="session_mode", native_enum=False),
        nullable=False,
        index=True,
    )
    role = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    conversations = relationship(
        "Conversation",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class RoleContext(BaseModel):
    """Minimal future-facing identity context."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1)
    role: str = Field(min_length=1)


class ChatbotSessionCreate(BaseModel):
    """DTO for future session creation flows."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1)
    rfq_id: str | None = None
    mode: SessionMode
    role: str = Field(min_length=1)


class SessionCreateCommand(BaseModel):
    """Domain command for creating a chatbot session."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: str = Field(min_length=1)
    entry_mode: SessionEntryMode
    rfq_id: str | None = None
    role: str | None = None


class SessionBindCommand(BaseModel):
    """Domain command for binding a session to one RFQ."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rfq_id: str = Field(min_length=1)


class ChatbotSessionRead(BaseModel):
    """DTO for reading persisted session state."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    user_id: str
    rfq_id: str | None
    mode: SessionMode
    role: str
    created_at: datetime
    updated_at: datetime
