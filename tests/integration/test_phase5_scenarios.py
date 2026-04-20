import logging
import uuid
from dataclasses import dataclass, field

from src.app_context import (
    get_azure_openai_connector,
    get_intelligence_connector,
    get_manager_connector,
)
from src.config.capability_status import CAPABILITY_STATUS_ENTRIES
from src.config.stage_profiles import DEFAULT_STAGE_PROFILE, STAGE_PROFILES
from src.connectors.azure_openai_connector import ChatCompletionResult
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
from src.controllers.context_builder import CONFIDENCE_PATTERN_MARKER
from src.utils.errors import UpstreamServiceError


KNOWN_STAGE_ID = next(iter(STAGE_PROFILES.keys()))


@dataclass
class EchoAzureOpenAIConnector:
    calls: list = field(default_factory=list)

    def create_chat_completion(self, messages, tools=None):
        stable_prefix = messages[0]["content"]
        variable_suffix = messages[-1]["content"]
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "stable_prefix": stable_prefix,
                "variable_suffix": variable_suffix,
            }
        )

        if "template exactly: I don't have grounded facts for" in stable_prefix:
            template_line = stable_prefix.split("template exactly: ", 1)[1].split("\n", 1)[0]
            return ChatCompletionResult(assistant_text=template_line)

        if (
            "Selection reason: User asked for the current RFQ snapshot or currently known facts"
            in variable_suffix
        ):
            return ChatCompletionResult(
                assistant_text=(
                    "Snapshot-based answer.\n"
                    f"{CONFIDENCE_PATTERN_MARKER}"
                )
            )

        if "Role tone directive: Respond in a decision-oriented executive tone." in stable_prefix:
            return ChatCompletionResult(assistant_text="Executive response.")

        if (
            "Role tone directive: Respond as a technical estimation peer using operationally useful language."
            in stable_prefix
        ):
            return ChatCompletionResult(assistant_text="Working-level estimation response.")

        return ChatCompletionResult(assistant_text="assistant-response")


class ScenarioManagerConnector(ManagerConnector):
    def __init__(self, *, rfq_details_by_id=None, fail_get_rfq=False):
        self.rfq_details_by_id = rfq_details_by_id or {}
        self.fail_get_rfq = fail_get_rfq
        self.get_rfq_calls = 0
        self.get_rfq_stages_calls = 0

    def get_rfq(self, rfq_id):
        self.get_rfq_calls += 1
        if self.fail_get_rfq:
            raise UpstreamServiceError("Manager service request failed")

        key = str(rfq_id)
        if key in self.rfq_details_by_id:
            return self.rfq_details_by_id[key]

        return _make_manager_rfq_detail(
            rfq_id=rfq_id,
            stage_id=KNOWN_STAGE_ID,
            stage_name="Go / No-Go",
        )

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
                    }
                ]
            }
        )


class ScenarioIntelligenceConnector:
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


def _make_manager_rfq_detail(*, rfq_id, stage_id, stage_name) -> ManagerRfqDetail:
    return ManagerRfqDetail.model_validate(
        {
            "id": str(rfq_id),
            "rfq_code": "IF-25144",
            "name": "Boiler Upgrade",
            "client": "Acme Industrial",
            "status": "open",
            "progress": 35,
            "deadline": "2026-05-01",
            "current_stage_name": stage_name,
            "workflow_name": "Industrial RFQ",
            "industry": "Oil & Gas",
            "country": "SA",
            "priority": "critical",
            "owner": "Sarah",
            "workflow_id": str(uuid.uuid4()),
            "current_stage_id": str(stage_id),
            "source_package_available": True,
            "workbook_available": False,
            "created_at": "2026-04-01T10:00:00Z",
            "updated_at": "2026-04-10T10:00:00Z",
        }
    )


def _override_phase5_dependencies(app, *, azure_connector, manager_connector, intelligence_connector):
    app.dependency_overrides[get_azure_openai_connector] = lambda: azure_connector
    app.dependency_overrides[get_manager_connector] = lambda: manager_connector
    app.dependency_overrides[get_intelligence_connector] = lambda: intelligence_connector


def _clear_phase5_dependencies(app):
    app.dependency_overrides.pop(get_azure_openai_connector, None)
    app.dependency_overrides.pop(get_manager_connector, None)
    app.dependency_overrides.pop(get_intelligence_connector, None)


def _create_session(client, *, mode, rfq_id=None, role=None):
    payload = {"mode": mode, "user_id": "scenario-user"}
    if rfq_id is not None:
        payload["rfq_id"] = rfq_id
    if role is not None:
        payload["role"] = role

    response = client.post("/rfq-chatbot/v1/sessions", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def _log_values(caplog, field_name):
    return [record.__dict__[field_name] for record in caplog.records if field_name in record.__dict__]


def test_phase5_scenario_1_role_contrast_same_rfq(client, app, caplog):
    fake_azure = EchoAzureOpenAIConnector()
    manager = ScenarioManagerConnector()
    intelligence = ScenarioIntelligenceConnector()
    _override_phase5_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        rfq_id = str(uuid.uuid4())
        lead_session_id = _create_session(
            client,
            mode="rfq",
            rfq_id=rfq_id,
            role="estimation_dept_lead",
        )
        executive_session_id = _create_session(
            client,
            mode="rfq",
            rfq_id=rfq_id,
            role="executive",
        )

        with caplog.at_level(logging.INFO):
            lead_response = client.post(
                f"/rfq-chatbot/v1/sessions/{lead_session_id}/turn",
                json={"content": "Who owns this RFQ and when is the deadline?"},
            )
            executive_response = client.post(
                f"/rfq-chatbot/v1/sessions/{executive_session_id}/turn",
                json={"content": "Who owns this RFQ and when is the deadline?"},
            )

        lead_payload = lead_response.json()
        executive_payload = executive_response.json()

        assert lead_response.status_code == 200
        assert executive_response.status_code == 200
        assert lead_payload["source_refs"] == executive_payload["source_refs"]
        assert lead_payload["content"] != executive_payload["content"]

        role_values = _log_values(caplog, "phase5.role_applied")
        assert "estimation_dept_lead" in role_values
        assert "executive" in role_values
    finally:
        _clear_phase5_dependencies(app)


def test_phase5_scenario_2_stage_contrast_same_question(client, app, caplog):
    fake_azure = EchoAzureOpenAIConnector()
    unknown_stage_id = uuid.uuid4()
    while unknown_stage_id in STAGE_PROFILES:
        unknown_stage_id = uuid.uuid4()

    known_rfq_id = str(uuid.uuid4())
    unknown_rfq_id = str(uuid.uuid4())
    manager = ScenarioManagerConnector(
        rfq_details_by_id={
            known_rfq_id: _make_manager_rfq_detail(
                rfq_id=known_rfq_id,
                stage_id=KNOWN_STAGE_ID,
                stage_name="Go / No-Go",
            ),
            unknown_rfq_id: _make_manager_rfq_detail(
                rfq_id=unknown_rfq_id,
                stage_id=unknown_stage_id,
                stage_name="Unknown Stage",
            ),
        }
    )
    intelligence = ScenarioIntelligenceConnector()
    _override_phase5_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        known_session_id = _create_session(client, mode="rfq", rfq_id=known_rfq_id)
        unknown_session_id = _create_session(client, mode="rfq", rfq_id=unknown_rfq_id)

        with caplog.at_level(logging.INFO):
            known_response = client.post(
                f"/rfq-chatbot/v1/sessions/{known_session_id}/turn",
                json={"content": "Who owns this RFQ and when is the deadline?"},
            )
            unknown_response = client.post(
                f"/rfq-chatbot/v1/sessions/{unknown_session_id}/turn",
                json={"content": "Who owns this RFQ and when is the deadline?"},
            )

        assert known_response.status_code == 200
        assert unknown_response.status_code == 200

        stage_values = _log_values(caplog, "phase5.stage_resolved")
        assert "success" in stage_values
        assert "default_profile_applied" in stage_values

        known_prefix = fake_azure.calls[0]["stable_prefix"]
        unknown_prefix = fake_azure.calls[1]["stable_prefix"]
        assert known_prefix != unknown_prefix
        assert "Stage framing:" in known_prefix
        assert "Stage framing:" in unknown_prefix
        assert DEFAULT_STAGE_PROFILE["prompt_frame_fragment"] in unknown_prefix
    finally:
        _clear_phase5_dependencies(app)


def test_phase5_scenario_3_confidence_marker_presence_and_absence(client, app, caplog):
    fake_azure = EchoAzureOpenAIConnector()
    manager = ScenarioManagerConnector()
    intelligence = ScenarioIntelligenceConnector()
    _override_phase5_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        session_id = _create_session(client, mode="rfq", rfq_id=str(uuid.uuid4()))

        with caplog.at_level(logging.INFO):
            snapshot_response = client.post(
                f"/rfq-chatbot/v1/sessions/{session_id}/turn",
                json={"content": "Give me the current snapshot summary for this RFQ"},
            )
            profile_response = client.post(
                f"/rfq-chatbot/v1/sessions/{session_id}/turn",
                json={"content": "Who owns this RFQ and when is the deadline?"},
            )

        assert snapshot_response.status_code == 200
        assert profile_response.status_code == 200

        assert CONFIDENCE_PATTERN_MARKER in snapshot_response.json()["content"]
        assert CONFIDENCE_PATTERN_MARKER not in profile_response.json()["content"]

        marker_values = _log_values(caplog, "phase5.confidence_marker_emitted")
        assert True in marker_values
        assert False in marker_values
    finally:
        _clear_phase5_dependencies(app)


def test_phase5_scenario_4_capability_status_absence(client, app, caplog):
    fake_azure = EchoAzureOpenAIConnector()
    manager = ScenarioManagerConnector()
    intelligence = ScenarioIntelligenceConnector()
    _override_phase5_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        session_id = _create_session(client, mode="global")

        with caplog.at_level(logging.INFO):
            response = client.post(
                f"/rfq-chatbot/v1/sessions/{session_id}/turn",
                json={"content": "what's the briefing?"},
            )

        assert response.status_code == 200
        assert manager.get_rfq_calls == 0
        assert intelligence.get_snapshot_calls == 0

        expected_capability = CAPABILITY_STATUS_ENTRIES["briefing"]["capability_name"]
        assert expected_capability in _log_values(caplog, "phase5.capability_status_hit")

        stable_prefix = fake_azure.calls[-1]["stable_prefix"]
        assert "template exactly: I don't have grounded facts for" in stable_prefix
        assert CAPABILITY_STATUS_ENTRIES["briefing"]["named_future_condition"] in stable_prefix
    finally:
        _clear_phase5_dependencies(app)


def test_phase5_scenario_5_trivial_no_retrieval_turn(client, app):
    fake_azure = EchoAzureOpenAIConnector()
    manager = ScenarioManagerConnector()
    intelligence = ScenarioIntelligenceConnector()
    _override_phase5_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        session_id = _create_session(client, mode="global")
        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "Hello copilot"},
        )

        payload = response.json()
        assert response.status_code == 200
        assert payload["source_refs"] == []
        assert CONFIDENCE_PATTERN_MARKER not in payload["content"]
        assert manager.get_rfq_calls == 0
        assert intelligence.get_snapshot_calls == 0
    finally:
        _clear_phase5_dependencies(app)


def test_phase5_scenario_6_graceful_degradation_on_stage_resolution_failure(
    client, app, caplog
):
    fake_azure = EchoAzureOpenAIConnector()
    manager = ScenarioManagerConnector(fail_get_rfq=True)
    intelligence = ScenarioIntelligenceConnector()
    _override_phase5_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        session_id = _create_session(client, mode="rfq", rfq_id=str(uuid.uuid4()))

        with caplog.at_level(logging.INFO):
            response = client.post(
                f"/rfq-chatbot/v1/sessions/{session_id}/turn",
                json={"content": "what's the deadline?"},
            )

        assert response.status_code == 200
        assert "upstream_service_error" in _log_values(caplog, "phase5.stage_resolved")

        stable_prefix = fake_azure.calls[-1]["stable_prefix"]
        assert DEFAULT_STAGE_PROFILE["prompt_frame_fragment"] in stable_prefix
    finally:
        _clear_phase5_dependencies(app)
