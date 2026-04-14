"""Conversation persistence models for episodic memory."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.database import Base
from src.models.envelope import SourceRef, ToolResultEnvelope


class Conversation(Base):
    """A conversation thread scoped to a single chatbot session."""

    __tablename__ = "chatbot_conversations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("chatbot_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    session = relationship("ChatbotSession", back_populates="conversations")
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.turn_number",
    )


class Message(Base):
    """A persisted conversational turn entry."""

    __tablename__ = "chatbot_messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "turn_number",
            name="uq_chatbot_messages_conversation_turn_number",
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("chatbot_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_number = Column(Integer, nullable=False)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    tool_calls = Column(JSON, nullable=True)
    source_refs = Column(JSON, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    conversation = relationship("Conversation", back_populates="messages")


class ToolCallRecord(BaseModel):
    """Typed JSON helper for future message tool-call storage."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: ToolResultEnvelope | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
