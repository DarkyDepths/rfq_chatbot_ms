"""Session routes for Phase 2 mode creation, retrieval, and binding."""

from uuid import UUID

from fastapi import APIRouter, Depends

from src.app_context import get_mode_controller
from src.controllers.mode_controller import ModeController
from src.models.session import ChatbotSessionRead
from src.translators.chat_translator import (
    SessionBindRequest,
    SessionCreateRequest,
    to_session_response,
)


router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.post("", status_code=201, response_model=ChatbotSessionRead)
def create_session(
    body: SessionCreateRequest,
    ctrl: ModeController = Depends(get_mode_controller),
):
    """Create either an RFQ-bound or global session."""

    return to_session_response(ctrl.create_session(body))


@router.get("/{session_id}", response_model=ChatbotSessionRead)
def get_session(
    session_id: UUID,
    ctrl: ModeController = Depends(get_mode_controller),
):
    """Fetch one session by id."""

    return to_session_response(ctrl.get_session(session_id))


@router.post("/{session_id}/bind-rfq", response_model=ChatbotSessionRead)
def bind_session_to_rfq(
    session_id: UUID,
    body: SessionBindRequest,
    ctrl: ModeController = Depends(get_mode_controller),
):
    """Perform the one-way portfolio-to-RFQ binding for this phase."""

    return to_session_response(ctrl.bind_session_to_rfq(session_id, body))
