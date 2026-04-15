"""Dependency wiring for rfq_chatbot_ms."""

from fastapi import Depends
from sqlalchemy.orm import Session

from src.config.settings import get_settings
from src.connectors.azure_openai_connector import AzureOpenAIConnector
from src.connectors.intelligence_connector import IntelligenceConnector
from src.connectors.manager_connector import ManagerConnector
from src.controllers.chat_controller import ChatController
from src.controllers.context_builder import ContextBuilder
from src.controllers.conversation_controller import ConversationController
from src.controllers.mode_controller import ModeController
from src.controllers.tool_controller import ToolController
from src.database import get_db
from src.datasources.conversation_datasource import ConversationDatasource
from src.datasources.session_datasource import SessionDatasource


def get_smoke_payload() -> dict[str, str]:
    """Return a static smoke payload for bootstrap verification."""

    return {
        "status": "ok",
        "service": "rfq_chatbot_ms",
        "phase": "phase-4",
    }


def get_session_datasource(db: Session = Depends(get_db)) -> SessionDatasource:
    """Build the session datasource for the current request."""

    return SessionDatasource(db)


def get_conversation_datasource(
    db: Session = Depends(get_db),
) -> ConversationDatasource:
    """Build the conversation datasource for the current request."""

    return ConversationDatasource(db)


def get_mode_controller(
    session_datasource: SessionDatasource = Depends(get_session_datasource),
    db: Session = Depends(get_db),
) -> ModeController:
    """Build the Phase 2 mode controller for the current request."""

    settings = get_settings()

    return ModeController(
        datasource=session_datasource,
        session=db,
        default_role=settings.AUTH_BYPASS_ROLE,
    )


def get_conversation_controller(
    conversation_datasource: ConversationDatasource = Depends(get_conversation_datasource),
    db: Session = Depends(get_db),
) -> ConversationController:
    """Build the conversation controller for the current request."""

    return ConversationController(datasource=conversation_datasource, session=db)


def get_context_builder() -> ContextBuilder:
    """Build the prompt context builder for the current request."""

    return ContextBuilder()


def get_azure_openai_connector() -> AzureOpenAIConnector:
    """Build the Azure OpenAI connector for the current request."""

    return AzureOpenAIConnector()


def get_manager_connector() -> ManagerConnector:
    """Build the Phase 4 manager connector."""

    return ManagerConnector()


def get_intelligence_connector() -> IntelligenceConnector:
    """Build the Phase 4 intelligence connector."""

    return IntelligenceConnector()


def get_tool_controller(
    manager_connector: ManagerConnector = Depends(get_manager_connector),
    intelligence_connector: IntelligenceConnector = Depends(get_intelligence_connector),
) -> ToolController:
    """Build the Phase 4 tool controller."""

    return ToolController(
        manager_connector=manager_connector,
        intelligence_connector=intelligence_connector,
    )


def get_chat_controller(
    session_datasource: SessionDatasource = Depends(get_session_datasource),
    conversation_controller: ConversationController = Depends(get_conversation_controller),
    context_builder: ContextBuilder = Depends(get_context_builder),
    azure_openai_connector: AzureOpenAIConnector = Depends(get_azure_openai_connector),
    tool_controller: ToolController = Depends(get_tool_controller),
) -> ChatController:
    """Build the Phase 4 chat controller for the current request."""

    return ChatController(
        session_datasource=session_datasource,
        conversation_controller=conversation_controller,
        context_builder=context_builder,
        azure_openai_connector=azure_openai_connector,
        tool_controller=tool_controller,
    )
