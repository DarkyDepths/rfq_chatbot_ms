import logging
import uuid
from dataclasses import dataclass, field

from src.app_context import (
    get_azure_openai_connector,
    get_intelligence_connector,
    get_manager_connector,
)
from src.config.stage_profiles import STAGE_PROFILES
from src.connectors.azure_openai_connector import ChatCompletionResult
from src.connectors.intelligence_connector import IntelligenceConnector
from src.connectors.manager_connector import (
    ManagerConnector,
    ManagerRfqDetail,
    ManagerRfqStageListResponse,
)


KNOWN_STAGE_ID = next(iter(STAGE_PROFILES.keys()))


@dataclass
class ObservabilityAzureConnector:
    calls: list = field(default_factory=list)

    def create_chat_completion(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        stable_prefix = messages[0]["content"]
        latest_user_turn = messages[-1]["content"].lower()

        if "Domain scope recheck mode: classification only." in stable_prefix:
            if "brown field" in latest_user_turn:
                return ChatCompletionResult(assistant_text="definitely_relevant")
            return ChatCompletionResult(assistant_text="not_relevant")

        if "Disambiguation behavior: RFQ resolution mode." in stable_prefix:
            return ChatCompletionResult(
                assistant_text="Which RFQ are you referring to?"
            )

        if "Grounding behavior: grounding gap mode." in stable_prefix:
            return ChatCompletionResult(
                assistant_text="I cannot retrieve the requested information right now."
            )

        if "template exactly: I don't have grounded facts for" in stable_prefix:
            return ChatCompletionResult(
                assistant_text=(
                    "I don't have grounded facts for RFQ intelligence briefing retrieval yet "
                    "because available after briefing rollout is enabled in a later phase."
                )
            )

        return ChatCompletionResult(assistant_text="assistant-response")


class ObservabilityManagerConnector(ManagerConnector):
    def __init__(self):
        self.get_rfq_calls = 0
        self.get_rfq_stages_calls = 0

    def get_rfq(self, rfq_id):
        self.get_rfq_calls += 1
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


class ObservabilityIntelligenceConnector(IntelligenceConnector):
    def __init__(self):
        self.get_snapshot_calls = 0

    def get_snapshot(self, rfq_id):
        self.get_snapshot_calls += 1
        raise AssertionError("Snapshot retrieval is not expected in observability tests")


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


def _create_session(client, *, mode: str, rfq_id: str | None = None, role: str | None = None):
    payload = {"mode": mode, "user_id": "observability-user"}
    if rfq_id is not None:
        payload["rfq_id"] = rfq_id
    if role is not None:
        payload["role"] = role

    response = client.post("/rfq-chatbot/v1/sessions", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def _log_values(caplog, field_name: str):
    return [record.__dict__[field_name] for record in caplog.records if field_name in record.__dict__]


def test_observability_rfq_specific_emits_phase5_and_phase6_fields(client, app, caplog):
    fake_azure = ObservabilityAzureConnector()
    manager = ObservabilityManagerConnector()
    intelligence = ObservabilityIntelligenceConnector()
    _override_dependencies(
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
        assert _log_values(caplog, "phase5.stage_resolved")
        assert _log_values(caplog, "phase5.role_applied")
        assert _log_values(caplog, "phase5.role_fallback_used")
        assert _log_values(caplog, "phase5.tools_keyword_matched")
        assert _log_values(caplog, "phase5.tools_allowed_after_stage")
        assert _log_values(caplog, "phase5.tools_allowed_after_role")
        assert _log_values(caplog, "phase5.confidence_marker_emitted")
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "rfq_specific"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "tools_pipeline"
        assert _log_values(caplog, "phase6.grounding_required")[-1] is True
        assert _log_values(caplog, "phase6.grounding_satisfied")[-1] is True
        assert _log_values(caplog, "phase6.output_guardrail_result")[-1] == "pass"
    finally:
        _clear_dependencies(app)


def test_observability_domain_knowledge_has_no_stage_tool_or_grounding_fields(client, app, caplog):
    fake_azure = ObservabilityAzureConnector()
    manager = ObservabilityManagerConnector()
    intelligence = ObservabilityIntelligenceConnector()
    _override_dependencies(
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
                json={"content": "what is PWHT?"},
            )

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "domain_knowledge"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "direct_llm"
        assert _log_values(caplog, "phase5.stage_resolved") == []
        assert _log_values(caplog, "phase5.tools_keyword_matched") == []
        assert _log_values(caplog, "phase5.tools_allowed_after_stage") == []
        assert _log_values(caplog, "phase5.tools_allowed_after_role") == []
        assert _log_values(caplog, "phase6.domain_recheck_invoked") == []
        assert _log_values(caplog, "phase6.domain_recheck_label") == []
        assert _log_values(caplog, "phase6.domain_recheck_final_intent") == []
        assert _log_values(caplog, "phase6.grounding_required") == []
        assert _log_values(caplog, "phase6.grounding_satisfied") == []
    finally:
        _clear_dependencies(app)


def test_observability_semantic_recheck_emits_fallback_fields(client, app, caplog):
    fake_azure = ObservabilityAzureConnector()
    manager = ObservabilityManagerConnector()
    intelligence = ObservabilityIntelligenceConnector()
    _override_dependencies(
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
                json={"content": "brown field and green field what do they mean"},
            )

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "domain_knowledge"
        assert _log_values(caplog, "phase6.domain_recheck_invoked")[-1] is True
        assert _log_values(caplog, "phase6.domain_recheck_label")[-1] == "definitely_relevant"
        assert _log_values(caplog, "phase6.domain_recheck_final_intent")[-1] == "domain_knowledge"
    finally:
        _clear_dependencies(app)


def test_observability_disambiguation_emits_trigger_field(client, app, caplog):
    fake_azure = ObservabilityAzureConnector()
    manager = ObservabilityManagerConnector()
    intelligence = ObservabilityIntelligenceConnector()
    _override_dependencies(
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
                json={"content": "what's the status of this RFQ?"},
            )

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "disambiguation"
        assert _log_values(caplog, "phase6.disambiguation_triggered")[-1] is True
    finally:
        _clear_dependencies(app)


def test_observability_disambiguation_resolution_emits_resolved_field(client, app, caplog):
    fake_azure = ObservabilityAzureConnector()
    manager = ObservabilityManagerConnector()
    intelligence = ObservabilityIntelligenceConnector()
    _override_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        session_id = _create_session(client, mode="global")

        with caplog.at_level(logging.INFO):
            first = client.post(
                f"/rfq-chatbot/v1/sessions/{session_id}/turn",
                json={"content": "what's the status of this RFQ?"},
            )
            second = client.post(
                f"/rfq-chatbot/v1/sessions/{session_id}/turn",
                json={"content": "IF-25144"},
            )

        assert first.status_code == 200
        assert second.status_code == 200
        assert _log_values(caplog, "phase6.disambiguation_resolved")[-1] == "IF-25144"
    finally:
        _clear_dependencies(app)


def test_observability_conversational_has_guardrail_pass(client, app, caplog):
    fake_azure = ObservabilityAzureConnector()
    manager = ObservabilityManagerConnector()
    intelligence = ObservabilityIntelligenceConnector()
    _override_dependencies(
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
                json={"content": "hello"},
            )

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "conversational"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "conversational"
        assert _log_values(caplog, "phase6.output_guardrail_result") == []
        assert len(fake_azure.calls) == 0
    finally:
        _clear_dependencies(app)
