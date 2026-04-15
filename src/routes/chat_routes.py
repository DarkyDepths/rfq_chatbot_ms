"""Conversational routes for the current chat baseline."""

from uuid import UUID

from fastapi import APIRouter, Depends

from src.app_context import get_chat_controller, get_conversation_controller
from src.controllers.chat_controller import ChatController
from src.controllers.conversation_controller import ConversationController
from src.models.turn import ConversationReadResponse, TurnRequest, TurnResponse
from src.translators.chat_translator import (
    to_conversation_read_response,
    to_turn_create_command,
)


router = APIRouter(tags=["Chat"])


@router.post("/sessions/{session_id}/turn", response_model=TurnResponse)
def post_turn(
    session_id: UUID,
    body: TurnRequest,
    ctrl: ChatController = Depends(get_chat_controller),
):
    """Handle one user turn on an existing session."""

    return ctrl.handle_turn(session_id, to_turn_create_command(body))


@router.get("/conversations/{conversation_id}", response_model=ConversationReadResponse)
def get_conversation(
    conversation_id: UUID,
    ctrl: ConversationController = Depends(get_conversation_controller),
):
    """Read back persisted conversation history."""

    conversation = ctrl.get_conversation(conversation_id)
    messages = ctrl.get_messages(conversation_id)
    return to_conversation_read_response(conversation, messages)
