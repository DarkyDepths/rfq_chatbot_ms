"""Session mode orchestration and transition policy."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from src.datasources.session_datasource import SessionDatasource
from src.models.session import ChatbotSession, ChatbotSessionCreate, SessionMode
from src.translators.chat_translator import SessionBindRequest, SessionCreateRequest
from src.utils.errors import ConflictError, NotFoundError, UnprocessableEntityError


class ModeController:
    """Owns session creation, lookup, and one-way mode pivot rules."""

    def __init__(
        self,
        datasource: SessionDatasource,
        session: Session,
        default_role: str,
    ):
        self.datasource = datasource
        self.session = session
        self.default_role = default_role

    def create_session(self, request: SessionCreateRequest) -> ChatbotSession:
        internal_mode = self.resolve_creation_mode(request.mode, request.rfq_id)
        role = (request.role or self.default_role).strip()
        payload = ChatbotSessionCreate(
            user_id=request.user_id.strip(),
            rfq_id=request.rfq_id.strip() if request.rfq_id else None,
            mode=internal_mode,
            role=role,
        )
        chatbot_session = self.datasource.create(payload)
        self.session.commit()
        self.session.refresh(chatbot_session)
        return chatbot_session

    def get_session(self, session_id: uuid.UUID) -> ChatbotSession:
        chatbot_session = self.datasource.get_by_id(session_id)
        if not chatbot_session:
            raise NotFoundError(f"Session '{session_id}' not found")
        return chatbot_session

    def bind_session_to_rfq(
        self,
        session_id: uuid.UUID,
        request: SessionBindRequest,
    ) -> ChatbotSession:
        chatbot_session = self.get_session(session_id)
        target_mode = SessionMode.RFQ_BOUND
        requested_rfq_id = request.rfq_id.strip()

        if chatbot_session.rfq_id:
            raise ConflictError(
                f"Session '{session_id}' is already bound to RFQ '{chatbot_session.rfq_id}'"
            )

        self.validate_transition(chatbot_session.mode, target_mode)

        chatbot_session = self.datasource.bind_rfq(
            chatbot_session=chatbot_session,
            rfq_id=requested_rfq_id,
            mode=target_mode,
        )
        self.session.commit()
        self.session.refresh(chatbot_session)
        return chatbot_session

    def resolve_creation_mode(self, external_mode: str, rfq_id: str | None) -> SessionMode:
        normalized_rfq_id = rfq_id.strip() if rfq_id else None

        if external_mode == "rfq":
            if not normalized_rfq_id:
                raise UnprocessableEntityError(
                    "rfq_id is required when mode is 'rfq'"
                )
            return SessionMode.RFQ_BOUND

        if normalized_rfq_id:
            raise UnprocessableEntityError(
                "rfq_id must be null when mode is 'global'"
            )

        return SessionMode.PORTFOLIO

    def validate_transition(
        self,
        current_mode: SessionMode,
        target_mode: SessionMode,
    ) -> None:
        allowed_transitions = {
            SessionMode.PORTFOLIO: {SessionMode.RFQ_BOUND},
            SessionMode.PENDING_PIVOT: {SessionMode.RFQ_BOUND},
            SessionMode.RFQ_BOUND: set(),
        }

        if target_mode not in allowed_transitions[current_mode]:
            raise ConflictError(
                f"Cannot transition session from '{current_mode.value}' to '{target_mode.value}'"
            )
