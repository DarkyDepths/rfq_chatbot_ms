import uuid

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
    ManagerRfqDetail,
    ManagerRfqStageListResponse,
)
from src.controllers.rfq_response_controller import RfqResponseController
from src.models.conversation import ToolCallRecord
from src.models.envelope import ConfidenceLevel
from src.tools.common.envelope import build_tool_result_envelope


class RecordingToolController:
    def __init__(self, *, rfq_id: uuid.UUID):
        self.rfq_id = rfq_id
        self.calls: list[str] = []

    def execute_single_tool(self, tool_name, rfq_id, *, preloaded_rfq_detail=None):
        self.calls.append(tool_name)
        if tool_name == "get_rfq_profile":
            value = preloaded_rfq_detail or _profile(rfq_id=rfq_id)
            return build_tool_result_envelope(
                value=value,
                system="rfq_manager_ms",
                artifact="rfq",
                locator=f"/rfq-manager/v1/rfqs/{rfq_id}",
                parsed_at=value.updated_at,
                confidence=ConfidenceLevel.DETERMINISTIC,
            )
        if tool_name == "get_rfq_stage":
            value = _stage_list()
            return build_tool_result_envelope(
                value=value,
                system="rfq_manager_ms",
                artifact="rfq_stages",
                locator=f"/rfq-manager/v1/rfqs/{rfq_id}/stages",
                confidence=ConfidenceLevel.DETERMINISTIC,
            )
        if tool_name == "get_rfq_snapshot":
            value = _snapshot(rfq_id)
            return build_tool_result_envelope(
                value=value,
                system="rfq_intelligence_ms",
                artifact="rfq_intelligence_snapshot",
                locator=f"/intelligence/v1/rfqs/{rfq_id}/snapshot",
                confidence=ConfidenceLevel.DETERMINISTIC,
            )
        raise AssertionError(f"unexpected tool: {tool_name}")


def _profile(*, rfq_id: uuid.UUID | None = None, progress: int = 35) -> ManagerRfqDetail:
    rfq_id = rfq_id or uuid.uuid4()
    return ManagerRfqDetail.model_validate(
        {
            "id": str(rfq_id),
            "rfq_code": "IF-25144",
            "name": "Boiler Upgrade",
            "client": "Acme Industrial",
            "status": "open",
            "progress": progress,
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


def _stage_list(*, progress: int = 82, blocker_status: str | None = None):
    return ManagerRfqStageListResponse.model_validate(
        {
            "data": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "Review",
                    "order": 2,
                    "assigned_team": "Estimating",
                    "status": "open",
                    "progress": progress,
                    "blocker_status": blocker_status,
                    "blocker_reason_code": "awaiting_vendor" if blocker_status else None,
                }
            ]
        }
    )


def _snapshot(rfq_id: uuid.UUID) -> IntelligenceSnapshotArtifact:
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
            intake_panel_summary=SnapshotIntakePanelSummary(
                status="available",
                key_gaps=["vendor clarifications"],
            ),
            briefing_panel_summary=SnapshotBriefingPanelSummary(
                status="available",
                executive_summary="Known summary",
                missing_info=["commercial exclusions"],
            ),
            workbook_panel=SnapshotWorkbookPanel(status="not_ready"),
            review_panel=SnapshotReviewPanel(status="not_ready", active_findings_count=2),
            analytical_status_summary=SnapshotAnalyticalStatusSummary(status="not_ready"),
            outcome_summary=SnapshotOutcomeSummary(
                status="not_recorded",
                reason="pending review",
            ),
            consumer_hints=SnapshotConsumerHints(),
            requires_human_review=True,
            overall_status="partial",
        ),
        schema_version="1.0",
        created_at="2026-04-10T10:00:00Z",
        updated_at="2026-04-10T10:00:00Z",
    )


def _record(tool_name: str, value, *, system: str, artifact: str, locator: str) -> ToolCallRecord:
    result = build_tool_result_envelope(
        value=value,
        system=system,
        artifact=artifact,
        locator=locator,
        parsed_at=getattr(value, "updated_at", None),
        confidence=ConfidenceLevel.DETERMINISTIC,
    )
    return ToolCallRecord(
        tool_name=tool_name,
        arguments={"selection_reason": "test"},
        result=result,
        source_refs=[result.source_ref] if result.source_ref else [],
    )


def test_stage_answer_uses_profile_progress_as_canonical_value():
    controller = RfqResponseController()
    rfq_id = uuid.uuid4()
    profile = _profile(rfq_id=rfq_id, progress=35)
    stage_record = _record(
        "get_rfq_stage",
        _stage_list(progress=82),
        system="rfq_manager_ms",
        artifact="rfq_stages",
        locator=f"/rfq-manager/v1/rfqs/{rfq_id}/stages",
    )

    plan = controller.compose_response(
        user_content="what is the current stage?",
        rfq_detail=profile,
        tool_call_records=[stage_record],
        rfq_id=rfq_id,
    )

    assert plan.grounded is True
    assert plan.response_mode == "FACT_FIELD"
    assert plan.original_response_mode == "FACT_FIELD"
    assert plan.effective_response_mode == "FACT_FIELD"
    assert plan.evidence_sufficient is True
    assert plan.downgrade_reason is None
    assert plan.assistant_text == "The current stage is Review."
    assert "82%" not in plan.assistant_text
    assert {ref.artifact for ref in plan.source_refs} == {"rfq", "rfq_stages"}


def test_rfq_code_answer_is_a_direct_fact_field():
    controller = RfqResponseController()
    rfq_id = uuid.uuid4()
    profile = _profile(rfq_id=rfq_id)

    plan = controller.compose_response(
        user_content="what is the rfq code?",
        rfq_detail=profile,
        tool_call_records=[],
        rfq_id=rfq_id,
    )

    assert plan.response_mode == "FACT_FIELD"
    assert plan.assistant_text == "The RFQ code is IF-25144."
    assert plan.grounded is True


def test_summary_answer_is_compact_and_structured():
    controller = RfqResponseController()
    rfq_id = uuid.uuid4()
    profile = _profile(rfq_id=rfq_id)
    snapshot_record = _record(
        "get_rfq_snapshot",
        _snapshot(rfq_id),
        system="rfq_intelligence_ms",
        artifact="rfq_intelligence_snapshot",
        locator=f"/intelligence/v1/rfqs/{rfq_id}/snapshot",
    )

    plan = controller.compose_response(
        user_content="tell me about this rfq",
        rfq_detail=profile,
        tool_call_records=[snapshot_record],
        rfq_id=rfq_id,
    )

    assert plan.response_mode == "RFQ_SUMMARY"
    assert plan.assistant_text.startswith("RFQ summary\n")
    assert "- RFQ: Boiler Upgrade" in plan.assistant_text
    assert "- Code: IF-25144" in plan.assistant_text
    assert "Readiness\n" in plan.assistant_text
    assert "- Readiness: manager workbook not available; snapshot workbook not_ready; review not_ready; intelligence partial" in plan.assistant_text
    assert plan.grounded is True


def test_current_details_answer_uses_unified_profile_and_snapshot_view():
    controller = RfqResponseController()
    rfq_id = uuid.uuid4()
    profile = _profile(rfq_id=rfq_id)
    snapshot_record = _record(
        "get_rfq_snapshot",
        _snapshot(rfq_id),
        system="rfq_intelligence_ms",
        artifact="rfq_intelligence_snapshot",
        locator=f"/intelligence/v1/rfqs/{rfq_id}/snapshot",
    )

    plan = controller.compose_response(
        user_content="what is the current details about this rfq",
        rfq_detail=profile,
        tool_call_records=[snapshot_record],
        rfq_id=rfq_id,
    )

    assert plan.grounded is True
    assert plan.response_mode == "RFQ_DETAIL"
    assert plan.assistant_text.startswith("Current RFQ details\n")
    assert "Core facts\n" in plan.assistant_text
    assert "- RFQ: Boiler Upgrade" in plan.assistant_text
    assert "- Deadline: 2026-05-01" in plan.assistant_text
    assert "Intelligence state\n" in plan.assistant_text
    assert "- Snapshot: partial" in plan.assistant_text
    assert "- Briefing: available" in plan.assistant_text
    assert "Known gaps\n" in plan.assistant_text
    assert "- commercial exclusions" in plan.assistant_text
    assert {ref.system for ref in plan.source_refs} == {"rfq_manager_ms", "rfq_intelligence_ms"}


def test_watchouts_answer_is_signal_based_structured_advisory():
    controller = RfqResponseController()
    rfq_id = uuid.uuid4()
    profile = _profile(rfq_id=rfq_id, progress=35)
    snapshot_record = _record(
        "get_rfq_snapshot",
        _snapshot(rfq_id),
        system="rfq_intelligence_ms",
        artifact="rfq_intelligence_snapshot",
        locator=f"/intelligence/v1/rfqs/{rfq_id}/snapshot",
    )

    plan = controller.compose_response(
        user_content="what should I watch out for in this rfq?",
        rfq_detail=profile,
        tool_call_records=[snapshot_record],
        rfq_id=rfq_id,
    )

    assert plan.grounded is True
    assert plan.response_mode == "RFQ_ADVISORY"
    assert plan.assistant_text.startswith("RFQ advisory\n")
    assert "Main concerns\n" in plan.assistant_text
    assert "- Progress is 35% against the current deadline of 2026-05-01." in plan.assistant_text
    assert "- The current intelligence snapshot still requires human review." in plan.assistant_text
    assert "Missing / incomplete\n" in plan.assistant_text
    assert "- Manager-backed workbook availability is still false." in plan.assistant_text
    assert "- Grounded gaps are still open: commercial exclusions, vendor clarifications." in plan.assistant_text
    assert "What needs attention\n" in plan.assistant_text
    assert "- Resolve the outstanding human review before relying on the intelligence output as final." in plan.assistant_text


def test_missing_question_uses_same_signal_based_advisory_sections():
    controller = RfqResponseController()
    rfq_id = uuid.uuid4()
    profile = _profile(rfq_id=rfq_id, progress=35)
    snapshot_record = _record(
        "get_rfq_snapshot",
        _snapshot(rfq_id),
        system="rfq_intelligence_ms",
        artifact="rfq_intelligence_snapshot",
        locator=f"/intelligence/v1/rfqs/{rfq_id}/snapshot",
    )

    plan = controller.compose_response(
        user_content="what is missing in this rfq?",
        rfq_detail=profile,
        tool_call_records=[snapshot_record],
        rfq_id=rfq_id,
    )

    assert plan.response_mode == "RFQ_ADVISORY"
    assert plan.assistant_text.startswith("RFQ advisory\nMissing / incomplete\n")
    assert "- Current intelligence snapshot is partial." in plan.assistant_text
    assert "- Snapshot workbook status is not_ready." in plan.assistant_text
    assert "- Grounded gaps are still open: commercial exclusions, vendor clarifications." in plan.assistant_text


def test_missing_grounded_profile_data_returns_explicit_unavailable_message():
    controller = RfqResponseController()

    plan = controller.compose_response(
        user_content="who owns this rfq?",
        rfq_detail=None,
        tool_call_records=[],
        rfq_id=uuid.uuid4(),
    )

    assert plan.grounded is False
    assert plan.response_mode == "RFQ_SUMMARY"
    assert plan.original_response_mode == "FACT_FIELD"
    assert plan.effective_response_mode == "RFQ_SUMMARY"
    assert plan.evidence_sufficient is False
    assert plan.downgrade_reason == "fact_field_unavailable"
    assert plan.assistant_text == "I don't have grounded RFQ data available right now."
    assert plan.source_refs == []


def test_advisory_downgrades_to_detail_with_caveat_when_snapshot_is_missing():
    controller = RfqResponseController()
    rfq_id = uuid.uuid4()
    profile = _profile(rfq_id=rfq_id, progress=90)
    profile = profile.model_copy(
        update={
            "source_package_available": True,
            "workbook_available": True,
        }
    )

    plan = controller.compose_response(
        user_content="what needs attention right now?",
        rfq_detail=profile,
        tool_call_records=[],
        rfq_id=rfq_id,
    )

    assert plan.response_mode == "RFQ_DETAIL"
    assert plan.original_response_mode == "RFQ_ADVISORY"
    assert plan.effective_response_mode == "RFQ_DETAIL"
    assert plan.evidence_sufficient is False
    assert plan.downgrade_reason == "snapshot_unavailable"
    assert plan.assistant_text.startswith(
        "I can show the current RFQ state, but grounded advisory signals "
        "are not fully available because the intelligence snapshot is missing."
    )
    assert "Current RFQ details\n" in plan.assistant_text
    assert plan.grounded is True


def test_compose_response_synthesizes_primary_profile_record_when_missing():
    controller = RfqResponseController()
    rfq_id = uuid.uuid4()
    profile = _profile(rfq_id=rfq_id)

    plan = controller.compose_response(
        user_content="what's the status of this rfq?",
        rfq_detail=profile,
        tool_call_records=[],
        rfq_id=rfq_id,
    )

    assert plan.grounded is True
    assert plan.response_mode == "FACT_FIELD"
    assert plan.tool_call_records[0].tool_name == "get_rfq_profile"
    assert plan.tool_call_records[0].result is not None
    assert plan.tool_call_records[0].result.source_ref is not None


def test_compose_response_stays_backward_compatible_without_retrieval():
    controller = RfqResponseController()
    rfq_id = uuid.uuid4()
    profile = _profile(rfq_id=rfq_id)

    plan = controller.compose_response(
        user_content="what is the deadline?",
        rfq_detail=profile,
        tool_call_records=[],
        rfq_id=rfq_id,
    )

    assert plan.response_mode == "FACT_FIELD"
    assert plan.effective_response_mode == "FACT_FIELD"
    assert plan.assistant_text == "The RFQ deadline is 2026-05-01."
    assert plan.tools_planned == ()
    assert plan.tools_executed == ()
    assert plan.tools_from_preload == ()


def test_detail_downgrades_to_summary_when_only_profile_evidence_exists():
    controller = RfqResponseController()
    rfq_id = uuid.uuid4()
    profile = _profile(rfq_id=rfq_id)

    plan = controller.compose_response(
        user_content="what are the current details about this rfq?",
        rfq_detail=profile,
        tool_call_records=[],
        rfq_id=rfq_id,
    )

    assert plan.response_mode == "RFQ_SUMMARY"
    assert plan.original_response_mode == "RFQ_DETAIL"
    assert plan.effective_response_mode == "RFQ_SUMMARY"
    assert plan.evidence_sufficient is False
    assert plan.downgrade_reason == "detail_evidence_profile_only"
    assert plan.assistant_text.startswith("RFQ summary\n")


def test_compose_response_with_retrieval_plans_tools_by_mode():
    controller = RfqResponseController()
    rfq_id = uuid.uuid4()
    tool_controller = RecordingToolController(rfq_id=rfq_id)

    plan = controller.compose_response_with_retrieval(
        user_content="what should I watch out for?",
        rfq_detail=None,
        preloaded_tool_call_records=[],
        rfq_id=rfq_id,
        tool_controller=tool_controller,
    )

    assert plan.response_mode == "RFQ_ADVISORY"
    assert plan.tools_planned == ("get_rfq_profile", "get_rfq_snapshot", "get_rfq_stage")
    assert plan.tools_executed == ("get_rfq_profile", "get_rfq_snapshot", "get_rfq_stage")
    assert tool_controller.calls == ["get_rfq_profile", "get_rfq_snapshot", "get_rfq_stage"]
    assert plan.evidence_sufficient is True


def test_compose_response_with_retrieval_reuses_preloaded_records():
    controller = RfqResponseController()
    rfq_id = uuid.uuid4()
    profile = _profile(rfq_id=rfq_id)
    preloaded_profile = _record(
        "get_rfq_profile",
        profile,
        system="rfq_manager_ms",
        artifact="rfq",
        locator=f"/rfq-manager/v1/rfqs/{rfq_id}",
    )
    preloaded_snapshot = _record(
        "get_rfq_snapshot",
        _snapshot(rfq_id),
        system="rfq_intelligence_ms",
        artifact="rfq_intelligence_snapshot",
        locator=f"/intelligence/v1/rfqs/{rfq_id}/snapshot",
    )
    tool_controller = RecordingToolController(rfq_id=rfq_id)

    plan = controller.compose_response_with_retrieval(
        user_content="what should I watch out for?",
        rfq_detail=profile,
        preloaded_tool_call_records=[preloaded_profile, preloaded_snapshot],
        rfq_id=rfq_id,
        tool_controller=tool_controller,
    )

    assert plan.tools_planned == ("get_rfq_profile", "get_rfq_snapshot", "get_rfq_stage")
    assert plan.tools_from_preload == ("get_rfq_profile", "get_rfq_snapshot")
    assert plan.tools_executed == ("get_rfq_stage",)
    assert tool_controller.calls == ["get_rfq_stage"]
