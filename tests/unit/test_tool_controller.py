import uuid

import pytest

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
from src.utils.errors import UnprocessableEntityError


class FakeManagerConnector(ManagerConnector):
    def __init__(self):
        pass

    def get_rfq(self, rfq_id):
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

    def get_rfq_stages(self, rfq_id):
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
    def get_snapshot(self, rfq_id):
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


def test_tool_controller_executes_manager_profile_retrieval():
    controller = ToolController(
        manager_connector=FakeManagerConnector(),
        intelligence_connector=FakeIntelligenceConnector(),
    )
    session = type("Session", (), {"rfq_id": str(uuid.uuid4())})()

    tool_calls = controller.maybe_execute_retrieval(
        session,
        "Who owns this RFQ and what is the deadline?",
    )

    assert tool_calls[0].tool_name == "get_rfq_profile"
    assert tool_calls[0].result.confidence.value == "deterministic"
    assert tool_calls[0].source_refs[0].system == "rfq_manager_ms"


def test_tool_controller_executes_intelligence_snapshot_retrieval():
    controller = ToolController(
        manager_connector=FakeManagerConnector(),
        intelligence_connector=FakeIntelligenceConnector(),
    )
    session = type("Session", (), {"rfq_id": str(uuid.uuid4())})()

    tool_calls = controller.maybe_execute_retrieval(
        session,
        "Give me the current snapshot summary for this RFQ",
    )

    assert tool_calls[0].tool_name == "get_rfq_snapshot"
    assert tool_calls[0].result.confidence.value == "pattern_1_sample"
    assert tool_calls[0].result.validated_against == "1_sample"


def test_tool_controller_rejects_missing_rfq_binding_for_retrieval():
    controller = ToolController(
        manager_connector=FakeManagerConnector(),
        intelligence_connector=FakeIntelligenceConnector(),
    )
    session = type("Session", (), {"rfq_id": None})()

    with pytest.raises(UnprocessableEntityError) as exc:
        controller.maybe_execute_retrieval(
            session,
            "What is the deadline for this RFQ?",
        )

    assert "requires an RFQ-bound session" in str(exc.value)


def test_tool_controller_handles_unsupported_capability_via_status_response():
    controller = ToolController(
        manager_connector=FakeManagerConnector(),
        intelligence_connector=FakeIntelligenceConnector(),
    )
    session = type("Session", (), {"rfq_id": str(uuid.uuid4())})()

    tool_calls = controller.maybe_execute_retrieval(
        session,
        "Show me the full briefing for this RFQ",
    )

    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "get_capability_status"
    assert tool_calls[0].result.confidence.value == "absent"
    assert tool_calls[0].source_refs == []


def test_tool_controller_rejects_ambiguous_retrieval_attempt():
    controller = ToolController(
        manager_connector=FakeManagerConnector(),
        intelligence_connector=FakeIntelligenceConnector(),
    )
    session = type("Session", (), {"rfq_id": str(uuid.uuid4())})()

    with pytest.raises(UnprocessableEntityError) as exc:
        controller.maybe_execute_retrieval(
            session,
            "Give me the current snapshot and deadline for this RFQ",
        )

    assert "retrieval request is ambiguous" in str(exc.value)
    assert "one RFQ fact at a time" in str(exc.value)
