import uuid
from types import SimpleNamespace

import pytest

from src.config.capability_status import CAPABILITY_STATUS_ENTRIES
from src.config.role_profiles import ROLE_PROFILES
from src.config.stage_profiles import DEFAULT_STAGE_PROFILE
from src.connectors.intelligence_connector import (
    IntelligenceSnapshotArtifact,
    IntelligenceSnapshotContent,
    SnapshotAnalyticalStatusSummary,
    SnapshotArtifactMeta,
    SnapshotBriefingPanelSummary,
    SnapshotConsumerHints,
    SnapshotIntakePanelSummary,
    SnapshotOutcomeSummary,
    SnapshotReviewPanel,
    SnapshotRfqSummary,
    SnapshotWorkbookPanel,
)
from src.connectors.manager_connector import (
    ManagerConnector,
    ManagerRfqDetail,
    ManagerRfqStageListResponse,
)
from src.controllers.tool_controller import ToolController
from src.models.session import SessionMode
from src.utils.errors import UnprocessableEntityError


class FakeManagerConnector(ManagerConnector):
    def __init__(self, rfq_detail: ManagerRfqDetail | None = None):
        self.rfq_detail = rfq_detail
        self.get_rfq_calls = 0
        self.get_rfq_stages_calls = 0

    def get_rfq(self, rfq_id):
        self.get_rfq_calls += 1
        if self.rfq_detail is None:
            return _manager_rfq_detail(rfq_id)
        return self.rfq_detail

    def get_rfq_stages(self, rfq_id):
        self.get_rfq_stages_calls += 1
        return ManagerRfqStageListResponse.model_validate(
            {
                "data": [
                    {
                        "id": str(uuid.uuid4()),
                        "name": "Review",
                        "order": 2,
                        "assigned_team": "Estimating",
                        "status": "open",
                        "progress": 35,
                        "blocker_status": None,
                        "blocker_reason_code": None,
                    }
                ]
            }
        )


class FakeIntelligenceConnector:
    def __init__(self):
        self.get_snapshot_calls = 0

    def get_snapshot(self, rfq_id):
        self.get_snapshot_calls += 1
        return IntelligenceSnapshotArtifact(
            id=uuid.uuid4(),
            rfq_id=rfq_id,
            artifact_type="rfq_intelligence_snapshot",
            version=1,
            status="partial",
            is_current=True,
            content=IntelligenceSnapshotContent(
                artifact_meta=SnapshotArtifactMeta(
                    artifact_type="rfq_intelligence_snapshot",
                ),
                rfq_summary=SnapshotRfqSummary(
                    rfq_id=str(rfq_id),
                    rfq_code="IF-25144",
                    project_title="Boiler Upgrade",
                    client_name="Acme Industrial",
                ),
                availability_matrix={"intelligence_briefing": "available"},
                intake_panel_summary=SnapshotIntakePanelSummary(status="available"),
                briefing_panel_summary=SnapshotBriefingPanelSummary(status="available"),
                workbook_panel=SnapshotWorkbookPanel(status="not_ready"),
                review_panel=SnapshotReviewPanel(status="not_ready"),
                analytical_status_summary=SnapshotAnalyticalStatusSummary(
                    status="not_ready"
                ),
                outcome_summary=SnapshotOutcomeSummary(status="not_recorded"),
                consumer_hints=SnapshotConsumerHints(),
                overall_status="partial",
            ),
            schema_version="1.0",
            created_at="2026-04-10T10:00:00Z",
            updated_at="2026-04-10T10:00:00Z",
        )


def _session(rfq_id: str | None, mode: SessionMode = SessionMode.RFQ_BOUND):
    return SimpleNamespace(rfq_id=rfq_id, mode=mode)


def _manager_rfq_detail(rfq_id: uuid.UUID) -> ManagerRfqDetail:
    return ManagerRfqDetail.model_validate(
        {
            "id": str(rfq_id),
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
            "workflow_id": str(uuid.uuid4()),
            "source_package_available": True,
            "workbook_available": False,
            "created_at": "2026-04-01T10:00:00Z",
            "updated_at": "2026-04-10T10:00:00Z",
        }
    )


def _build_controller(
    rfq_detail: ManagerRfqDetail | None = None,
) -> tuple[ToolController, FakeManagerConnector, FakeIntelligenceConnector]:
    manager = FakeManagerConnector(rfq_detail=rfq_detail)
    intelligence = FakeIntelligenceConnector()
    controller = ToolController(
        manager_connector=manager,
        intelligence_connector=intelligence,
    )
    return controller, manager, intelligence


def test_capability_status_hit_returns_absent_record_without_upstream_calls():
    controller, manager, intelligence = _build_controller()
    session = _session(str(uuid.uuid4()))

    tool_calls = controller.maybe_execute_retrieval(session, "what's the briefing?")

    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "get_capability_status"
    assert tool_calls[0].result.confidence.value == "absent"
    assert tool_calls[0].source_refs == []
    assert manager.get_rfq_calls == 0
    assert manager.get_rfq_stages_calls == 0
    assert intelligence.get_snapshot_calls == 0


def test_capability_status_takes_precedence_over_keyword_stage_match():
    controller, manager, intelligence = _build_controller()
    session = _session(str(uuid.uuid4()))

    tool_calls = controller.maybe_execute_retrieval(
        session,
        "what's the briefing stage?",
    )

    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "get_capability_status"
    assert manager.get_rfq_stages_calls == 0
    assert manager.get_rfq_calls == 0
    assert intelligence.get_snapshot_calls == 0


@pytest.mark.parametrize("keyword", sorted(CAPABILITY_STATUS_ENTRIES.keys()))
def test_all_phase4_unsupported_keywords_route_to_capability_status(keyword: str):
    controller, manager, intelligence = _build_controller()
    session = _session(str(uuid.uuid4()))

    tool_calls = controller.maybe_execute_retrieval(session, f"show me {keyword}")

    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "get_capability_status"
    assert tool_calls[0].result.confidence.value == "absent"
    assert manager.get_rfq_calls == 0
    assert manager.get_rfq_stages_calls == 0
    assert intelligence.get_snapshot_calls == 0


def test_keyword_match_with_full_allow_lists_executes_retrieval():
    controller, manager, intelligence = _build_controller()
    session = _session(str(uuid.uuid4()))

    tool_calls = controller.maybe_execute_retrieval(
        session,
        "who owns this RFQ and what is the deadline?",
        stage_profile=DEFAULT_STAGE_PROFILE,
        role_profile=ROLE_PROFILES["estimation_dept_lead"],
    )

    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "get_rfq_profile"
    assert manager.get_rfq_calls == 1
    assert intelligence.get_snapshot_calls == 0


def test_keyword_match_with_stage_subtraction_returns_no_retrieval_and_no_error():
    controller, manager, intelligence = _build_controller()
    session = _session(str(uuid.uuid4()))
    stage_profile = {
        "prompt_frame_fragment": "custom",
        "tool_allow_list": frozenset({"get_rfq_profile", "get_rfq_snapshot"}),
    }

    tool_calls = controller.maybe_execute_retrieval(
        session,
        "what stage are we in?",
        stage_profile=stage_profile,
        role_profile=ROLE_PROFILES["estimation_dept_lead"],
    )

    assert tool_calls == []
    assert manager.get_rfq_stages_calls == 0
    assert manager.get_rfq_calls == 0
    assert intelligence.get_snapshot_calls == 0


def test_keyword_match_with_role_subtraction_returns_no_retrieval_and_no_error():
    controller, manager, intelligence = _build_controller()
    session = _session(str(uuid.uuid4()))
    role_profile = {
        "tone_directive": "custom",
        "depth_directive": "custom",
        "tool_allow_list": frozenset({"get_rfq_profile", "get_rfq_snapshot"}),
    }

    tool_calls = controller.maybe_execute_retrieval(
        session,
        "what stage are we in?",
        stage_profile=DEFAULT_STAGE_PROFILE,
        role_profile=role_profile,
    )

    assert tool_calls == []
    assert manager.get_rfq_stages_calls == 0
    assert manager.get_rfq_calls == 0
    assert intelligence.get_snapshot_calls == 0


def test_keyword_match_surviving_both_gates_executes_selected_tool():
    controller, manager, intelligence = _build_controller()
    session = _session(str(uuid.uuid4()))
    stage_profile = {
        "prompt_frame_fragment": "custom",
        "tool_allow_list": frozenset({"get_rfq_snapshot"}),
    }
    role_profile = {
        "tone_directive": "custom",
        "depth_directive": "custom",
        "tool_allow_list": frozenset({"get_rfq_snapshot"}),
    }

    tool_calls = controller.maybe_execute_retrieval(
        session,
        "give me the current snapshot summary for this RFQ",
        stage_profile=stage_profile,
        role_profile=role_profile,
    )

    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "get_rfq_snapshot"
    assert intelligence.get_snapshot_calls == 1
    assert manager.get_rfq_calls == 0
    assert manager.get_rfq_stages_calls == 0


def test_current_details_about_this_rfq_routes_to_snapshot_tool():
    controller, manager, intelligence = _build_controller()
    session = _session(str(uuid.uuid4()))

    tool_calls = controller.maybe_execute_retrieval(
        session,
        "what is the current details about this rfq",
        stage_profile=DEFAULT_STAGE_PROFILE,
        role_profile=ROLE_PROFILES["estimation_dept_lead"],
    )

    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "get_rfq_snapshot"
    assert intelligence.get_snapshot_calls == 1
    assert manager.get_rfq_calls == 0
    assert manager.get_rfq_stages_calls == 0


def test_current_information_about_this_rfq_routes_to_snapshot_tool():
    controller, manager, intelligence = _build_controller()
    session = _session(str(uuid.uuid4()))

    tool_calls = controller.maybe_execute_retrieval(
        session,
        "what is the current information about this rfq",
        stage_profile=DEFAULT_STAGE_PROFILE,
        role_profile=ROLE_PROFILES["estimation_dept_lead"],
    )

    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "get_rfq_snapshot"
    assert intelligence.get_snapshot_calls == 1
    assert manager.get_rfq_calls == 0
    assert manager.get_rfq_stages_calls == 0


def test_multiple_tool_families_surviving_gates_raises_ambiguous_422():
    controller, _, _ = _build_controller()
    session = _session(str(uuid.uuid4()))

    with pytest.raises(UnprocessableEntityError) as exc:
        controller.maybe_execute_retrieval(
            session,
            "give me the current snapshot and deadline for this RFQ",
            stage_profile=DEFAULT_STAGE_PROFILE,
            role_profile=ROLE_PROFILES["estimation_dept_lead"],
        )

    assert (
        str(exc.value)
        == "This retrieval request is ambiguous; ask for one RFQ fact at a time"
    )


def test_get_rfq_profile_with_preloaded_rfq_detail_reuses_without_manager_call():
    rfq_id = uuid.uuid4()
    preloaded = _manager_rfq_detail(rfq_id)
    controller, manager, intelligence = _build_controller(rfq_detail=_manager_rfq_detail(rfq_id))
    session = _session(str(rfq_id))

    tool_calls = controller.maybe_execute_retrieval(
        session,
        "who owns this RFQ and what is the deadline?",
        preloaded_rfq_detail=preloaded,
    )

    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "get_rfq_profile"
    assert tool_calls[0].result.source_ref.system == "rfq_manager_ms"
    assert tool_calls[0].result.source_ref.artifact == "rfq"
    assert tool_calls[0].result.source_ref.locator == f"/rfq-manager/v1/rfqs/{rfq_id}"
    assert tool_calls[0].result.source_ref.parsed_at == preloaded.updated_at
    assert tool_calls[0].result.value.id == preloaded.id
    assert manager.get_rfq_calls == 0
    assert manager.get_rfq_stages_calls == 0
    assert intelligence.get_snapshot_calls == 0


def test_execute_single_tool_get_rfq_profile_reuses_preloaded_detail():
    rfq_id = uuid.uuid4()
    preloaded = _manager_rfq_detail(rfq_id)
    controller, manager, intelligence = _build_controller()

    result = controller.execute_single_tool(
        "get_rfq_profile",
        rfq_id,
        preloaded_rfq_detail=preloaded,
    )

    assert result.value.id == preloaded.id
    assert result.source_ref.system == "rfq_manager_ms"
    assert result.source_ref.artifact == "rfq"
    assert result.source_ref.locator == f"/rfq-manager/v1/rfqs/{rfq_id}"
    assert manager.get_rfq_calls == 0
    assert manager.get_rfq_stages_calls == 0
    assert intelligence.get_snapshot_calls == 0


def test_execute_single_tool_get_rfq_stage_uses_existing_stage_logic():
    rfq_id = uuid.uuid4()
    controller, manager, intelligence = _build_controller()

    result = controller.execute_single_tool("get_rfq_stage", rfq_id)

    assert result.source_ref.system == "rfq_manager_ms"
    assert result.source_ref.artifact == "rfq_stages"
    assert manager.get_rfq_stages_calls == 1
    assert manager.get_rfq_calls == 0
    assert intelligence.get_snapshot_calls == 0


def test_execute_single_tool_get_rfq_snapshot_uses_existing_snapshot_logic():
    rfq_id = uuid.uuid4()
    controller, manager, intelligence = _build_controller()

    result = controller.execute_single_tool("get_rfq_snapshot", rfq_id)

    assert result.source_ref.system == "rfq_intelligence_ms"
    assert result.source_ref.artifact == "rfq_intelligence_snapshot"
    assert intelligence.get_snapshot_calls == 1
    assert manager.get_rfq_calls == 0
    assert manager.get_rfq_stages_calls == 0


def test_execute_single_tool_unsupported_name_keeps_existing_error():
    controller, manager, intelligence = _build_controller()

    with pytest.raises(UnprocessableEntityError) as exc:
        controller.execute_single_tool("get_unknown_tool", uuid.uuid4())

    assert "Unsupported retrieval tool 'get_unknown_tool'" in str(exc.value)
    assert manager.get_rfq_calls == 0
    assert manager.get_rfq_stages_calls == 0
    assert intelligence.get_snapshot_calls == 0


def test_get_rfq_stage_ignores_preloaded_rfq_detail_and_calls_manager_stage_endpoint():
    rfq_id = uuid.uuid4()
    preloaded = _manager_rfq_detail(rfq_id)
    controller, manager, intelligence = _build_controller()
    session = _session(str(rfq_id))

    tool_calls = controller.maybe_execute_retrieval(
        session,
        "what stage are we in?",
        preloaded_rfq_detail=preloaded,
    )

    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "get_rfq_stage"
    assert manager.get_rfq_stages_calls == 1
    assert manager.get_rfq_calls == 0
    assert intelligence.get_snapshot_calls == 0


def test_maybe_execute_retrieval_keyword_behavior_is_unchanged_after_single_tool_extraction():
    controller, manager, intelligence = _build_controller()
    session = _session(str(uuid.uuid4()))

    tool_calls = controller.maybe_execute_retrieval(
        session,
        "who owns this RFQ and what is the deadline?",
        stage_profile=DEFAULT_STAGE_PROFILE,
        role_profile=ROLE_PROFILES["estimation_dept_lead"],
    )

    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "get_rfq_profile"
    assert tool_calls[0].arguments["selection_reason"] == (
        "User asked about RFQ profile metadata from manager"
    )
    assert manager.get_rfq_calls == 1
    assert manager.get_rfq_stages_calls == 0
    assert intelligence.get_snapshot_calls == 0


def test_portfolio_session_with_retrieval_question_still_raises_existing_binding_422():
    controller, manager, intelligence = _build_controller()
    session = _session(rfq_id=None, mode=SessionMode.PORTFOLIO)

    with pytest.raises(UnprocessableEntityError) as exc:
        controller.maybe_execute_retrieval(
            session,
            "what is the deadline for this RFQ?",
            preloaded_rfq_detail=None,
        )

    assert "requires an RFQ-bound session" in str(exc.value)
    assert manager.get_rfq_calls == 0
    assert manager.get_rfq_stages_calls == 0
    assert intelligence.get_snapshot_calls == 0
