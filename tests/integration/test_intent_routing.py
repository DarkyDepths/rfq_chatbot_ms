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
from src.connectors.manager_connector import ManagerConnector, ManagerRfqDetail
from src.utils.errors import UpstreamServiceError


KNOWN_STAGE_ID = next(iter(STAGE_PROFILES.keys()))


@dataclass
class EchoAzureConnector:
    calls: list = field(default_factory=list)

    def create_chat_completion(self, messages, tools=None):
        stable_prefix = messages[0]["content"]
        self.calls.append({"messages": messages, "tools": tools})
        latest_user_turn = messages[-1]["content"].lower()
        if "Domain scope recheck mode: classification only." in stable_prefix:
            if "brown field" in latest_user_turn or "aramco" in latest_user_turn:
                return ChatCompletionResult(assistant_text="definitely_relevant")
            if "legacy" in latest_user_turn:
                return ChatCompletionResult(assistant_text="possibly_relevant")
            return ChatCompletionResult(assistant_text="not_relevant")
        if "Grounding behavior: grounding gap mode." in stable_prefix:
            return ChatCompletionResult(
                assistant_text="I cannot retrieve the requested information right now."
            )
        return ChatCompletionResult(assistant_text="assistant-response")


class CountingManagerConnector(ManagerConnector):
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
        return {"data": []}


class CountingIntelligenceConnector:
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
    payload = {"mode": mode, "user_id": "intent-routing-user"}
    if rfq_id is not None:
        payload["rfq_id"] = rfq_id
    if role is not None:
        payload["role"] = role

    response = client.post("/rfq-chatbot/v1/sessions", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def _log_values(caplog, field_name: str):
    return [record.__dict__[field_name] for record in caplog.records if field_name in record.__dict__]


def test_route_rfq_specific_uses_tools_pipeline(client, app, caplog):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
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
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "rfq_specific"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "tools_pipeline"
        assert _log_values(caplog, "phase6.grounding_required")[-1] is True
        assert _log_values(caplog, "phase6.grounding_satisfied")[-1] is True
        assert _log_values(caplog, "phase6.grounding_gap_absence_injected") == []
        assert _log_values(caplog, "phase6.grounding_mismatch") == []
        assert manager.get_rfq_calls == 1
        assert intelligence.get_snapshot_calls == 1
    finally:
        _clear_dependencies(app)


def test_route_domain_knowledge_on_rfq_bound_uses_direct_llm_without_tools(client, app, caplog):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
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
        assert _log_values(caplog, "phase6.domain_recheck_invoked") == []
        assert _log_values(caplog, "phase6.grounding_required") == []
        assert _log_values(caplog, "phase6.grounding_satisfied") == []
        assert manager.get_rfq_calls == 1
        assert intelligence.get_snapshot_calls == 1
    finally:
        _clear_dependencies(app)


def test_grounding_gap_when_tool_retrieval_attempt_fails(client, app, caplog):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector(fail_get_rfq=True)
    intelligence = CountingIntelligenceConnector()
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
        content = response.json()["content"].lower()
        assert "don't have grounded" in content
        assert "deadline" in content
        assert response.json()["source_refs"] == []
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "rfq_specific"
        assert _log_values(caplog, "phase6.grounding_required")[-1] is True
        assert _log_values(caplog, "phase6.grounding_satisfied")[-1] is False
        assert _log_values(caplog, "phase6.grounding_gap_absence_injected")[-1] is True
        assert _log_values(caplog, "phase6.grounding_mismatch") == []
        assert len(fake_azure.calls) == 0
    finally:
        _clear_dependencies(app)


def test_rfq_specific_without_planner_keyword_uses_unified_grounded_summary(
    client, app, caplog
):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
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
                json={"content": "tell me about this RFQ"},
            )

        assert response.status_code == 200
        content = response.json()["content"]
        assert "Boiler Upgrade" in content
        assert "Sarah" in content
        assert "2026-05-01" in content
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "rfq_specific"
        assert _log_values(caplog, "phase6.grounding_required")[-1] is True
        assert _log_values(caplog, "phase6.grounding_satisfied")[-1] is True
        assert _log_values(caplog, "phase6.grounding_mismatch") == []
        assert _log_values(caplog, "phase6.grounding_gap_absence_injected") == []
        assert _log_values(caplog, "phase5.tools_keyword_matched")[-1] == []
        assert len(fake_azure.calls) == 0
    finally:
        _clear_dependencies(app)


def test_route_unsupported_dispatches_to_capability_status(client, app, caplog):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
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
                json={"content": "what's the briefing?"},
            )

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "unsupported"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "capability_status"
        assert manager.get_rfq_calls == 0
        assert intelligence.get_snapshot_calls == 0
    finally:
        _clear_dependencies(app)


def test_route_disambiguation_in_portfolio_session(client, app, caplog):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
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
        assert _log_values(caplog, "phase6.route_selected")[-1] == "disambiguation"
        assert manager.get_rfq_calls == 0
        assert intelligence.get_snapshot_calls == 0
    finally:
        _clear_dependencies(app)


def test_route_conversational_in_any_session(client, app, caplog):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
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
        assert manager.get_rfq_calls == 0
        assert intelligence.get_snapshot_calls == 0
        assert len(fake_azure.calls) == 0
    finally:
        _clear_dependencies(app)


def test_route_domain_knowledge_on_portfolio_session_uses_direct_llm(client, app, caplog):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
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
                json={"content": "how does RT work?"},
            )

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "domain_knowledge"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "direct_llm"
        assert _log_values(caplog, "phase6.domain_recheck_invoked") == []
        assert manager.get_rfq_calls == 0
        assert intelligence.get_snapshot_calls == 0
    finally:
        _clear_dependencies(app)


# ──────────────────────────────────────────────
# Phase 6.5 regression: out-of-scope routing integration
# ──────────────────────────────────────────────

def test_route_out_of_scope_bread_uses_deterministic_refusal(client, app, caplog):
    """Bread question must be classified out_of_scope and routed to deterministic_refusal."""
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
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
                json={"content": "how to prepare bread at home"},
            )

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "out_of_scope"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "deterministic_refusal"
        # No LLM call should have been made
        assert len(fake_azure.calls) == 0
        # Response must contain RFQ-redirect language
        content = response.json()["content"]
        assert "rfq" in content.lower() or "scope" in content.lower()
    finally:
        _clear_dependencies(app)


def test_route_out_of_scope_sport_uses_deterministic_refusal(client, app, caplog):
    """Sport question must be classified out_of_scope."""
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
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
                json={"content": "how to play sport"},
            )

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "out_of_scope"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "deterministic_refusal"
        assert len(fake_azure.calls) == 0
    finally:
        _clear_dependencies(app)


def test_route_out_of_scope_pasta_after_rfq_turn_stays_refused(client, app, caplog):
    """Multi-turn stability: pasta question after valid RFQ turn must still refuse."""
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
    _override_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        session_id = _create_session(client, mode="rfq", rfq_id=str(uuid.uuid4()))

        # Turn 1: valid RFQ question
        with caplog.at_level(logging.INFO):
            response1 = client.post(
                f"/rfq-chatbot/v1/sessions/{session_id}/turn",
                json={"content": "what's the deadline?"},
            )
        assert response1.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "rfq_specific"

        caplog.clear()

        # Turn 2: out-of-scope question (must refuse)
        with caplog.at_level(logging.INFO):
            response2 = client.post(
                f"/rfq-chatbot/v1/sessions/{session_id}/turn",
                json={"content": "how to cook pasta"},
            )
        assert response2.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "out_of_scope"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "deterministic_refusal"
    finally:
        _clear_dependencies(app)


def test_route_chitchat_joke_uses_deterministic_refusal(client, app, caplog):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
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
                json={"content": "tell me a joke"},
            )

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "out_of_scope"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "deterministic_refusal"
        assert len(fake_azure.calls) == 0
    finally:
        _clear_dependencies(app)


def test_route_how_are_you_uses_deterministic_refusal(client, app, caplog):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
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
                json={"content": "how are you?"},
            )

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "out_of_scope"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "deterministic_refusal"
        assert len(fake_azure.calls) == 0
    finally:
        _clear_dependencies(app)


def test_route_reset_phrases_skip_azure(client, app, caplog):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
    _override_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        for content in ("never mind", "start over"):
            session_id = _create_session(client, mode="global")
            caplog.clear()

            with caplog.at_level(logging.INFO):
                response = client.post(
                    f"/rfq-chatbot/v1/sessions/{session_id}/turn",
                    json={"content": content},
                )

            assert response.status_code == 200
            assert _log_values(caplog, "phase6.intent_classified")[-1] == "conversational"

        assert len(fake_azure.calls) == 0
    finally:
        _clear_dependencies(app)


def test_route_stainless_steel_pans_after_rfq_turn_is_refused(client, app, caplog):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
    _override_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        session_id = _create_session(client, mode="rfq", rfq_id=str(uuid.uuid4()))

        with caplog.at_level(logging.INFO):
            response1 = client.post(
                f"/rfq-chatbot/v1/sessions/{session_id}/turn",
                json={"content": "what's the deadline?"},
            )
        assert response1.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "rfq_specific"

        caplog.clear()

        with caplog.at_level(logging.INFO):
            response2 = client.post(
                f"/rfq-chatbot/v1/sessions/{session_id}/turn",
                json={"content": "and what about stainless steel pans?"},
            )

        assert response2.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "out_of_scope"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "deterministic_refusal"
        assert len(fake_azure.calls) == 0
    finally:
        _clear_dependencies(app)


def test_route_semantic_recheck_only_for_unresolved_knowledge_like_turn(client, app, caplog):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
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
        assert _log_values(caplog, "phase6.route_selected")[-1] == "direct_llm"
        assert _log_values(caplog, "phase6.domain_recheck_invoked")[-1] is True
        assert _log_values(caplog, "phase6.domain_recheck_label")[-1] == "definitely_relevant"
        assert _log_values(caplog, "phase6.domain_recheck_final_intent")[-1] == "domain_knowledge"
        assert len(fake_azure.calls) == 2
    finally:
        _clear_dependencies(app)


def test_route_strong_domain_anchor_skips_recheck(client, app, caplog):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
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
                json={"content": "do u know about aramco?"},
            )

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "domain_knowledge"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "direct_llm"
        assert _log_values(caplog, "phase6.domain_recheck_invoked") == []
        assert len(fake_azure.calls) == 1
    finally:
        _clear_dependencies(app)


def test_route_semantic_recheck_possibly_relevant_stays_out_of_scope(client, app, caplog):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
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
                json={"content": "what does legacy mean here?"},
            )

        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "out_of_scope"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "deterministic_refusal"
        assert _log_values(caplog, "phase6.domain_recheck_invoked")[-1] is True
        assert _log_values(caplog, "phase6.domain_recheck_label")[-1] == "possibly_relevant"
        assert _log_values(caplog, "phase6.domain_recheck_final_intent")[-1] == "out_of_scope"
        assert len(fake_azure.calls) == 1
    finally:
        _clear_dependencies(app)


def test_route_current_details_about_this_rfq_reaches_snapshot_tools_pipeline(client, app, caplog):
    fake_azure = EchoAzureConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
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
                json={"content": "what is the current details about this rfq"},
            )

        payload = response.json()
        assert response.status_code == 200
        assert _log_values(caplog, "phase6.intent_classified")[-1] == "rfq_specific"
        assert _log_values(caplog, "phase6.route_selected")[-1] == "tools_pipeline"
        assert _log_values(caplog, "phase6.grounding_satisfied")[-1] is True
        assert _log_values(caplog, "phase6.grounding_mismatch") == []
        assert any(
            source_ref["system"] == "rfq_intelligence_ms"
            for source_ref in payload["source_refs"]
        )
        assert intelligence.get_snapshot_calls >= 1
    finally:
        _clear_dependencies(app)
