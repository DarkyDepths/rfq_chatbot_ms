"""Dependency wiring for rfq_chatbot_ms."""

from fastapi import Depends
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.controllers.mode_controller import ModeController
from src.database import get_db
from src.datasources.session_datasource import SessionDatasource


def get_smoke_payload() -> dict[str, str]:
    """Return a static smoke payload for bootstrap verification."""

    return {
        "status": "ok",
        "service": "rfq_chatbot_ms",
        "phase": "phase-0",
    }


def get_session_datasource(db: Session = Depends(get_db)) -> SessionDatasource:
    """Build the session datasource for the current request."""

    return SessionDatasource(db)


def get_mode_controller(
    session_datasource: SessionDatasource = Depends(get_session_datasource),
    db: Session = Depends(get_db),
) -> ModeController:
    """Build the Phase 2 mode controller for the current request."""

    return ModeController(
        datasource=session_datasource,
        session=db,
        default_role=settings.AUTH_BYPASS_ROLE,
    )
