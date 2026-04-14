import uuid

import pytest

from src.controllers.mode_controller import ModeController
from src.datasources.session_datasource import SessionDatasource
from src.models.session import SessionMode
from src.translators.chat_translator import SessionBindRequest, SessionCreateRequest
from src.utils.errors import ConflictError, NotFoundError, UnprocessableEntityError


@pytest.fixture
def mode_controller(db_session):
    return ModeController(
        datasource=SessionDatasource(db_session),
        session=db_session,
        default_role="estimation_dept_lead",
    )


def test_validate_transition_allows_portfolio_to_rfq_bound(mode_controller):
    mode_controller.validate_transition(
        SessionMode.PORTFOLIO,
        SessionMode.RFQ_BOUND,
    )


def test_validate_transition_rejects_rfq_bound_to_portfolio(mode_controller):
    with pytest.raises(ConflictError) as exc:
        mode_controller.validate_transition(
            SessionMode.RFQ_BOUND,
            SessionMode.PORTFOLIO,
        )

    assert str(exc.value) == "Cannot transition session from 'rfq_bound' to 'portfolio'"


def test_validate_transition_rejects_portfolio_to_portfolio(mode_controller):
    with pytest.raises(ConflictError) as exc:
        mode_controller.validate_transition(
            SessionMode.PORTFOLIO,
            SessionMode.PORTFOLIO,
        )

    assert str(exc.value) == "Cannot transition session from 'portfolio' to 'portfolio'"


def test_resolve_creation_mode_rejects_global_with_rfq_id(mode_controller):
    with pytest.raises(UnprocessableEntityError) as exc:
        mode_controller.resolve_creation_mode("global", "IF-25144")

    assert str(exc.value) == "rfq_id must be null when mode is 'global'"


def test_bind_session_to_rfq_rejects_already_bound_session(mode_controller):
    chatbot_session = mode_controller.create_session(
        SessionCreateRequest(
            user_id="u1",
            mode="rfq",
            rfq_id="IF-25144",
        )
    )

    with pytest.raises(ConflictError) as exc:
        mode_controller.bind_session_to_rfq(
            chatbot_session.id,
            SessionBindRequest(rfq_id="IF-99999"),
        )

    assert (
        str(exc.value)
        == f"Session '{chatbot_session.id}' is already bound to RFQ 'IF-25144'"
    )


def test_bind_session_to_rfq_allows_pending_pivot_to_rfq_bound(mode_controller):
    chatbot_session = mode_controller.create_session(
        SessionCreateRequest(
            user_id="u1",
            mode="global",
        )
    )
    chatbot_session.mode = SessionMode.PENDING_PIVOT
    mode_controller.session.flush()

    updated_session = mode_controller.bind_session_to_rfq(
        chatbot_session.id,
        SessionBindRequest(rfq_id="IF-25144"),
    )

    assert updated_session.mode == SessionMode.RFQ_BOUND
    assert updated_session.rfq_id == "IF-25144"


def test_get_session_raises_not_found_for_missing_id(mode_controller):
    with pytest.raises(NotFoundError) as exc:
        mode_controller.get_session(uuid.uuid4())

    assert "not found" in str(exc.value).lower()
