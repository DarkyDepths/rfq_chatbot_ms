"""Database CRUD for chatbot sessions."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from src.models.session import ChatbotSession, ChatbotSessionCreate, SessionMode


class SessionDatasource:
    """Persistence-only access for chatbot session records."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, payload: ChatbotSessionCreate) -> ChatbotSession:
        chatbot_session = ChatbotSession(**payload.model_dump())
        self.session.add(chatbot_session)
        self.session.flush()
        self.session.refresh(chatbot_session)
        return chatbot_session

    def get_by_id(self, session_id: uuid.UUID) -> ChatbotSession | None:
        return (
            self.session.query(ChatbotSession)
            .filter(ChatbotSession.id == session_id)
            .first()
        )

    def bind_rfq(
        self,
        chatbot_session: ChatbotSession,
        rfq_id: str,
        mode: SessionMode = SessionMode.RFQ_BOUND,
    ) -> ChatbotSession:
        chatbot_session.rfq_id = rfq_id
        chatbot_session.mode = mode
        self.session.flush()
        self.session.refresh(chatbot_session)
        return chatbot_session
