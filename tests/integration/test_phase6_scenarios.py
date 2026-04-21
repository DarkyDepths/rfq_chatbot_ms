import logging
import uuid
from dataclasses import dataclass, field

from src.app_context import (
    get_azure_openai_connector,
    get_intelligence_connector,
    get_manager_connector,
)
from src.config.capability_status import CAPABILITY_STATUS_ENTRIES
from src.config.stage_profiles import STAGE_PROFILES
from src.connectors.azure_openai_connector import ChatCompletionResult
from src.connectors.intelligence_connector import (
    IntelligenceConnector,
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
from src.utils.errors import UpstreamServiceError
from tests.integration import test_phase5_scenarios as phase5_scenarios


KNOWN_STAGE_ID = next(iter(STAGE_PROFILES.keys()))


@dataclass
class ScenarioAzureConnector:
    calls: list = field(default_factory=list)

    def create_chat_completion(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        stable_prefix = messages[0]["content"]
        variable_suffix = messages[-1]["content"]
        latest_user_turn = variable_suffix.lower()
        latest_turn_marker = "latest user turn:\n"
        if latest_turn_marker in latest_user_turn:
            latest_user_turn = latest_user_turn.split(latest_turn_marker, 1)[1]

        if "Disambiguation behavior: RFQ resolution mode." in stable_prefix:
            return ChatCompletionResult(
                assistant_text=(
                    "Which RFQ are you referring to? You can provide the RFQ code "
                    "(e.g., IF-25144) or bind this session to a specific RFQ."
                )
            )

        if "Grounding behavior: grounding gap mode." in stable_prefix:
            return ChatCompletionResult(
                assistant_text="I cannot retrieve the requested information right now."
            )

        if "template exactly: I don't have grounded facts for" in stable_prefix:
            template_line = stable_prefix.split("template exactly: ", 1)[1].split("\n", 1)[0]
            return ChatCompletionResult(assistant_text=template_line)

        if "pwht" in latest_user_turn:
            return ChatCompletionResult(
                assistant_text="PWHT is post-weld heat treatment used to reduce residual stress."
            )

        if "rt" in latest_user_turn:
            return ChatCompletionResult(
                assistant_text="RT is radiographic testing used to detect internal weld defects."
            )

        return ChatCompletionResult(assistant_text="assistant-response")


class ScenarioManagerConnector(ManagerConnector):
    def __init__(self, *, fail_get_rfq: bool = False):
        self.fail_get_rfq = fail_get_rfq
        self.get_rfq_calls = 0
        self.get_rfq_stages_calls = 0

    def get_rfq(self, rfq_id):
        self.get_rfq_calls += 1
        if self.fail_get_rfq:
            raise UpstreamServiceError("Manager service request failed")

        return ManagerRfqDetail.model_validate(
            {
                "id": str(rfq_id),
                "rfq_code": "IF-25144",
                "name": "Boiler Upgrade",
                "client": "Acme Industrial",
                "status": "open",
                "progress": 35,
                "deadline": "2026-05-01",
                "current_stage_name": "Go / No-Go",
                "workflow_name": "Industrial RFQ",
                "industry": "Oil & Gas",
                "country": "SA",
                "priority": "critical",
                "owner": "Sarah",
                "workflow_id": str(uuid.uuid4()),
                "current_stage_id": str(KNOWN_STAGE_ID),
                "source_package_available": True,
                "workbook_available": False,
                "created_at": "2026-04-01T10:00:00Z",
                "updated_at": "2026-04-10T10:00:00Z",
            }
        )

    def get_rfq_stages(self, rfq_id):
        self.get_rfq_stages_calls += 1
        return ManagerRfqStageListResponse.model_validate({"data": []})


class ScenarioIntelligenceConnector(IntelligenceConnector):
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
                analytical_status_summary=SnapshotAnalyticalStatusSummary(status="not_ready"),
                outcome_summary=SnapshotOutcomeSummary(status="not_recorded"),
                consumer_hints=SnapshotConsumerHints(),
                overall_status="partial",
            ),
            schema_version="1.0",
            created_at="2026-04-10T10:00:00Z",
            updated_at="2026-04-10T10:00:00Z",
        )


def _override_dependencies(
    app,
    *,
    azure_connector,
    manager_connector,
    intelligence_connector,
):
    app.dependency_overrides[get_azure_openai_connector] = lambda: azure_connector
    app.dependency_overrides[get_manager_connector] = lambda: manager_connector
    app.dependency_overrides[get_intelligence_connector] = lambda: intelligence_connector


def _clear_dependencies(app):
    app.dependency_overrides.pop(get_azure_openai_connector, None)
    app.dependency_overrides.pop(get_manager_connector, None)
    app.dependency_overrides.pop(get_intelligence_connector, None)


def _setup_scenario_dependencies(app, *, fail_get_rfq: bool = False):
    azure = ScenarioAzureConnector()
    manager = ScenarioManagerConnector(fail_get_rfq=fail_get_rfq)
    intelligence = ScenarioIntelligenceConnector()
    _override_dependencies(
        app,
        azure_connector=azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )
    return azure, manager, intelligence


def _create_session(client, *, mode: str, rfq_id: str | None = None, role: str | None = None):
    payload = {"mode": mode, "user_id": "phase6-user"}
    if rfq_id is not None:
        payload["rfq_id"] = rfq_id
    if role is not None:
        payload["role"] = role

    response = client.post("/rfq-chatbot/v1/sessions", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def _submit_turn(client, session_id: str, content: str):
    return client.post(
        f"/rfq-chatbot/v1/sessions/{session_id}/turn",
        json={"content": content},
    )


def _log_values(caplog, field_name: str):
    return [record.__dict__[field_name] for record in caplog.records if field_name in record.__dict__]


def test_phase6_scenario_1_intent_rfq_specific_on_bound_session(client, app, caplog):
    azure, manager, intelligence = _setup_scenario_dependencies(app)

    try:
        session_id = _create_session(client, mode="rfq", rfq_id=str(uuid.uuid4()))

        with caplog.at_level(logging.INFO):
            response = _submit_turn(client, session_id, "what's the deadline?")

        payload = response.json()
        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "rfq_specific"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "tools_pipeline"
        assert _log_values(caplog, "phase6.output_guardrail_result")[-1] == "pass"
        assert _log_values(caplog, "phase5.tools_allowed_after_role")[-1] == ["get_rfq_profile"]
        assert payload["source_refs"]
        assert manager.get_rfq_calls == 1
        assert intelligence.get_snapshot_calls == 1
    finally:
        _clear_dependencies(app)


def test_phase6_scenario_2_intent_domain_knowledge_on_bound_session(client, app, caplog):
    azure, manager, intelligence = _setup_scenario_dependencies(app)

    try:
        session_id = _create_session(
            client,
            mode="rfq",
            rfq_id=str(uuid.uuid4()),
            role="executive",
        )

        with caplog.at_level(logging.INFO):
            response = _submit_turn(client, session_id, "what is PWHT?")

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "domain_knowledge"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "direct_llm"
        assert manager.get_rfq_calls == 1
        assert intelligence.get_snapshot_calls == 1

        stable_prefix = azure.calls[-1]["messages"][0]["content"]
        assert "Current stage label:" not in stable_prefix
    finally:
        _clear_dependencies(app)


def test_phase6_scenario_3_intent_domain_knowledge_on_portfolio_session(client, app, caplog):
    _, manager, intelligence = _setup_scenario_dependencies(app)

    try:
        session_id = _create_session(client, mode="global")

        with caplog.at_level(logging.INFO):
            response = _submit_turn(client, session_id, "how does RT work?")

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "domain_knowledge"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "direct_llm"
        assert manager.get_rfq_calls == 0
        assert intelligence.get_snapshot_calls == 0
    finally:
        _clear_dependencies(app)


def test_phase6_scenario_4_intent_unsupported_via_capability_status(client, app, caplog):
    _, manager, intelligence = _setup_scenario_dependencies(app)

    try:
        session_id = _create_session(client, mode="global")

        with caplog.at_level(logging.INFO):
            response = _submit_turn(client, session_id, "what's the briefing?")

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "unsupported"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "capability_status"
        expected_capability = CAPABILITY_STATUS_ENTRIES["briefing"]["capability_name"]
        assert expected_capability in _log_values(caplog, "phase5.capability_status_hit")
        assert manager.get_rfq_calls == 0
        assert intelligence.get_snapshot_calls == 0
    finally:
        _clear_dependencies(app)


def test_phase6_scenario_5_intent_conversational_fallback(client, app, caplog):
    _, manager, intelligence = _setup_scenario_dependencies(app)

    try:
        session_id = _create_session(client, mode="global")

        with caplog.at_level(logging.INFO):
            response = _submit_turn(client, session_id, "hello copilot")

        payload = response.json()
        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "conversational"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "conversational"
        assert _log_values(caplog, "phase6.output_guardrail_result") == []
        assert payload["source_refs"] == []
        assert manager.get_rfq_calls == 0
        assert intelligence.get_snapshot_calls == 0
    finally:
        _clear_dependencies(app)


def test_phase6_scenario_6_grounding_enforcement_with_tool_success(client, app, caplog):
    _, manager, intelligence = _setup_scenario_dependencies(app)

    try:
        session_id = _create_session(client, mode="rfq", rfq_id=str(uuid.uuid4()))

        with caplog.at_level(logging.INFO):
            response = _submit_turn(client, session_id, "who is the owner?")

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "rfq_specific"
        assert _log_values(caplog, "phase6.grounding_required")[-1] is True
        assert _log_values(caplog, "phase6.grounding_satisfied")[-1] is True
        assert _log_values(caplog, "phase6.output_guardrail_result")[-1] == "pass"
        assert manager.get_rfq_calls == 1
        assert intelligence.get_snapshot_calls == 1
    finally:
        _clear_dependencies(app)


def test_phase6_scenario_7_grounding_enforcement_with_tool_failure(client, app, caplog):
    _, manager, intelligence = _setup_scenario_dependencies(app, fail_get_rfq=True)

    try:
        session_id = _create_session(client, mode="rfq", rfq_id=str(uuid.uuid4()))

        with caplog.at_level(logging.INFO):
            response = _submit_turn(client, session_id, "what's the deadline?")

        assert response.status_code == 200
        assert "cannot retrieve the requested information" in response.json()["content"].lower()
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "rfq_specific"
        assert _log_values(caplog, "phase6.grounding_required")[-1] is True
        assert _log_values(caplog, "phase6.grounding_satisfied")[-1] is False
        assert _log_values(caplog, "phase6.grounding_gap_absence_injected")[-1] is True
        assert manager.get_rfq_calls >= 1
        assert intelligence.get_snapshot_calls == 1
    finally:
        _clear_dependencies(app)


def test_phase6_scenario_8_grounding_mismatch_no_tool_keyword_match(client, app, caplog):
    _, manager, intelligence = _setup_scenario_dependencies(app)

    try:
        session_id = _create_session(client, mode="rfq", rfq_id=str(uuid.uuid4()))

        with caplog.at_level(logging.INFO):
            response = _submit_turn(client, session_id, "tell me about this RFQ")

        assert response.status_code == 200
        assert "cannot retrieve the requested information" in response.json()["content"].lower()
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "rfq_specific"
        assert _log_values(caplog, "phase6.grounding_required")[-1] is True
        assert _log_values(caplog, "phase6.grounding_satisfied")[-1] is False
        assert _log_values(caplog, "phase6.grounding_mismatch")[-1] is True
        assert _log_values(caplog, "phase6.grounding_gap_absence_injected")[-1] is True
        assert manager.get_rfq_calls == 1
        assert intelligence.get_snapshot_calls == 1
    finally:
        _clear_dependencies(app)


def test_phase6_scenario_9_disambiguation_trigger(client, app, caplog):
    _, manager, intelligence = _setup_scenario_dependencies(app)

    try:
        session_id = _create_session(client, mode="global")

        with caplog.at_level(logging.INFO):
            response = _submit_turn(client, session_id, "what's the status of this RFQ?")

        assert response.status_code == 200
        assert "which rfq" in response.json()["content"].lower()
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "disambiguation"
        assert _log_values(caplog, "phase6.disambiguation_triggered")[-1] is True
        assert manager.get_rfq_calls == 0
        assert intelligence.get_snapshot_calls == 0
    finally:
        _clear_dependencies(app)


def test_phase6_scenario_10_disambiguation_resolution(client, app, caplog):
    _, manager, intelligence = _setup_scenario_dependencies(app)

    try:
        session_id = _create_session(client, mode="global")

        with caplog.at_level(logging.INFO):
            first = _submit_turn(client, session_id, "what's the status of this RFQ?")
            second = _submit_turn(client, session_id, "IF-25144")

        assert first.status_code == 200
        assert second.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "rfq_specific"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "tools_pipeline"
        assert _log_values(caplog, "phase6.disambiguation_resolved")[-1] == "IF-25144"
        assert manager.get_rfq_calls == 0
        assert intelligence.get_snapshot_calls == 0
    finally:
        _clear_dependencies(app)


def test_phase6_scenario_11_disambiguation_abandonment(client, app, caplog):
    _, manager, intelligence = _setup_scenario_dependencies(app)

    try:
        session_id = _create_session(client, mode="global")

        with caplog.at_level(logging.INFO):
            first = _submit_turn(client, session_id, "what's the status of this RFQ?")
            second = _submit_turn(client, session_id, "never mind, what is PWHT?")

        assert first.status_code == 200
        assert second.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "domain_knowledge"
        assert _log_values(caplog, "phase6.disambiguation_abandoned")[-1] is True
        assert manager.get_rfq_calls == 0
        assert intelligence.get_snapshot_calls == 0
    finally:
        _clear_dependencies(app)


def test_phase6_scenario_12_output_guardrail_soft_enforcement(client, app, caplog):
    _, manager, intelligence = _setup_scenario_dependencies(app)

    try:
        session_id = _create_session(client, mode="rfq", rfq_id=str(uuid.uuid4()))

        with caplog.at_level(logging.INFO):
            response = _submit_turn(client, session_id, "tell me about this RFQ")

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.grounding_mismatch")[-1] is True
        assert _log_values(caplog, "phase6.grounding_gap_absence_injected")[-1] is True
        assert _log_values(caplog, "phase6.output_guardrail_result")[-1] == "pass"
        assert manager.get_rfq_calls == 1
        assert intelligence.get_snapshot_calls == 1
    finally:
        _clear_dependencies(app)


def test_phase6_scenario_13_phase5_regression_guard(client, app, caplog):
    phase5_tests = [
        phase5_scenarios.test_phase5_scenario_1_role_contrast_same_rfq,
        phase5_scenarios.test_phase5_scenario_2_stage_contrast_same_question,
        phase5_scenarios.test_phase5_scenario_3_confidence_marker_presence_and_absence,
        phase5_scenarios.test_phase5_scenario_4_capability_status_absence,
        phase5_scenarios.test_phase5_scenario_5_trivial_no_retrieval_turn,
        phase5_scenarios.test_phase5_scenario_6_graceful_degradation_on_stage_resolution_failure,
    ]

    for phase5_test in phase5_tests:
        caplog.clear()
        if phase5_test is phase5_scenarios.test_phase5_scenario_5_trivial_no_retrieval_turn:
            phase5_test(client, app)
            continue

        phase5_test(client, app, caplog)


def test_phase6_scenario_14_mode_b_domain_knowledge_works(client, app, caplog):
    _, manager, intelligence = _setup_scenario_dependencies(app)

    try:
        session_id = _create_session(client, mode="global")

        with caplog.at_level(logging.INFO):
            response = _submit_turn(client, session_id, "in general, how does RT work?")

        assert response.status_code == 200
        assert response.json()["content"].strip()
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "domain_knowledge"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "direct_llm"
        assert _log_values(caplog, "phase6.output_guardrail_result")[-1] == "pass"
        assert _log_values(caplog, "phase6.grounding_required") == []
        assert manager.get_rfq_calls == 0
        assert intelligence.get_snapshot_calls == 0
    finally:
        _clear_dependencies(app)
