import uuid
from types import SimpleNamespace

import pytest

from src.config.stage_profiles import DEFAULT_STAGE_PROFILE, STAGE_PROFILES
from src.connectors.manager_connector import ManagerRfqDetail
from src.controllers.stage_controller import StageController
from src.models.session import SessionMode
from src.utils.errors import NotFoundError, UpstreamServiceError, UpstreamTimeoutError


class FakeManagerConnector:
    def __init__(self, rfq_detail: ManagerRfqDetail | None = None, error: Exception | None = None):
        self._rfq_detail = rfq_detail
        self._error = error
        self.calls = 0

    def get_rfq(self, rfq_id: uuid.UUID) -> ManagerRfqDetail:
        self.calls += 1
        if self._error is not None:
            raise self._error
        if self._rfq_detail is None:
            raise AssertionError("rfq_detail must be provided for success-path tests")
        return self._rfq_detail


def _session(mode: SessionMode, rfq_id: str | None):
    return SimpleNamespace(mode=mode, rfq_id=rfq_id)


def _rfq_detail_with_stage(stage_id: uuid.UUID | None) -> ManagerRfqDetail:
    return ManagerRfqDetail.model_validate(
        {
            "id": str(uuid.uuid4()),
            "rfq_code": "IF-25144",
            "name": "Boiler Upgrade",
            "client": "Acme Industrial",
            "status": "open",
            "progress": 35,
            "deadline": "2026-05-01",
            "current_stage_name": "Review",
            "workflow_name": "Industrial RFQ",
            "industry": "Oil & Gas",
            "country": "SA",
            "priority": "critical",
            "owner": "Sarah",
            "description": "Demo RFQ",
            "workflow_id": str(uuid.uuid4()),
            "current_stage_id": str(stage_id) if stage_id else None,
            "source_package_available": True,
            "source_package_updated_at": "2026-04-10T10:00:00Z",
            "workbook_available": False,
            "workbook_updated_at": None,
            "outcome_reason": None,
            "created_at": "2026-04-01T10:00:00Z",
            "updated_at": "2026-04-10T10:00:00Z",
        }
    )


def test_portfolio_session_uses_default_profile_without_manager_call():
    connector = FakeManagerConnector()
    controller = StageController(manager_connector=connector)

    resolution = controller.resolve_stage(_session(SessionMode.PORTFOLIO, str(uuid.uuid4())))

    assert resolution.profile == DEFAULT_STAGE_PROFILE
    assert resolution.rfq_detail is None
    assert resolution.stage_id is None
    assert connector.calls == 0


def test_non_uuid_rfq_id_uses_default_profile_without_manager_call():
    connector = FakeManagerConnector()
    controller = StageController(manager_connector=connector)

    resolution = controller.resolve_stage(_session(SessionMode.RFQ_BOUND, "IF-25144"))

    assert resolution.profile == DEFAULT_STAGE_PROFILE
    assert resolution.rfq_detail is None
    assert resolution.stage_id is None
    assert connector.calls == 0


def test_known_stage_id_selects_configured_stage_profile_and_returns_rfq_detail():
    known_stage_id = next(iter(STAGE_PROFILES.keys()))
    detail = _rfq_detail_with_stage(known_stage_id)
    connector = FakeManagerConnector(rfq_detail=detail)
    controller = StageController(manager_connector=connector)

    resolution = controller.resolve_stage(
        _session(SessionMode.RFQ_BOUND, str(uuid.uuid4()))
    )

    assert resolution.profile == STAGE_PROFILES[known_stage_id]
    assert resolution.rfq_detail == detail
    assert resolution.stage_id == known_stage_id
    assert connector.calls == 1


def test_unknown_stage_id_uses_default_profile_and_keeps_rfq_detail():
    unknown_stage_id = uuid.uuid4()
    while unknown_stage_id in STAGE_PROFILES:
        unknown_stage_id = uuid.uuid4()

    detail = _rfq_detail_with_stage(unknown_stage_id)
    connector = FakeManagerConnector(rfq_detail=detail)
    controller = StageController(manager_connector=connector)

    resolution = controller.resolve_stage(
        _session(SessionMode.RFQ_BOUND, str(uuid.uuid4()))
    )

    assert resolution.profile == DEFAULT_STAGE_PROFILE
    assert resolution.rfq_detail == detail
    assert resolution.stage_id == unknown_stage_id
    assert connector.calls == 1


@pytest.mark.parametrize(
    "error",
    [
        UpstreamTimeoutError("upstream timed out"),
        UpstreamServiceError("upstream failed"),
        NotFoundError("rfq not found"),
    ],
)
def test_upstream_errors_degrade_to_default_profile(error: Exception):
    connector = FakeManagerConnector(error=error)
    controller = StageController(manager_connector=connector)

    resolution = controller.resolve_stage(
        _session(SessionMode.RFQ_BOUND, str(uuid.uuid4()))
    )

    assert resolution.profile == DEFAULT_STAGE_PROFILE
    assert resolution.rfq_detail is None
    assert resolution.stage_id is None
    assert connector.calls == 1


def test_successful_resolution_calls_manager_get_rfq_exactly_once():
    known_stage_id = next(iter(STAGE_PROFILES.keys()))
    detail = _rfq_detail_with_stage(known_stage_id)
    connector = FakeManagerConnector(rfq_detail=detail)
    controller = StageController(manager_connector=connector)

    controller.resolve_stage(_session(SessionMode.RFQ_BOUND, str(uuid.uuid4())))

    assert connector.calls == 1
