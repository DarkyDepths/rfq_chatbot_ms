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
from src.connectors.manager_connector import (
    ManagerConnector,
    ManagerRfqDetail,
    ManagerRfqStageListResponse,
)
from src.utils.errors import UpstreamServiceError


KNOWN_STAGE_ID = next(iter(STAGE_PROFILES.keys()))


@dataclass
class FakeAzureOpenAIConnector:
    calls: list = field(default_factory=list)

    def create_chat_completion(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        stable_prefix = messages[0]["content"]

        if "template exactly: I don't have grounded facts for" in stable_prefix:
            return ChatCompletionResult(
                assistant_text=(
                    "I don't have grounded facts for RFQ intelligence briefing retrieval "
                    "yet because available after briefing rollout is enabled in a later phase."
                )
            )

        return ChatCompletionResult(assistant_text=f"assistant-response-{len(self.calls)}")


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
                "current_stage_name": "Review",
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
                briefing_panel_summary=SnapshotBriefingPanelSummary(
                    status="available",
                    executive_summary="Known summary",
                ),
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


def _override_step6_dependencies(
    app,
    *,
    azure_connector,
    manager_connector,
    intelligence_connector,
):
    app.dependency_overrides[get_azure_openai_connector] = lambda: azure_connector
    app.dependency_overrides[get_manager_connector] = lambda: manager_connector
    app.dependency_overrides[get_intelligence_connector] = lambda: intelligence_connector


def _clear_step6_dependencies(app):
    app.dependency_overrides.pop(get_azure_openai_connector, None)
    app.dependency_overrides.pop(get_manager_connector, None)
    app.dependency_overrides.pop(get_intelligence_connector, None)


def _create_session(client, *, mode: str, rfq_id: str | None = None, role: str | None = None):
    payload = {"mode": mode, "user_id": "chat-user"}
    if rfq_id is not None:
        payload["rfq_id"] = rfq_id
    if role is not None:
        payload["role"] = role

    response = client.post("/rfq-chatbot/v1/sessions", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def _log_values(caplog, field_name: str):
    return [record.__dict__[field_name] for record in caplog.records if field_name in record.__dict__]


def test_pipeline_portfolio_greeting_skips_retrieval_and_returns_200(client, app, caplog):
    fake_azure = FakeAzureOpenAIConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
    _override_step6_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        with caplog.at_level(logging.INFO):
            session_id = _create_session(client, mode="global")
            response = client.post(
                f"/rfq-chatbot/v1/sessions/{session_id}/turn",
                json={"content": "Hello copilot"},
            )

        payload = response.json()
        assert response.status_code == 200
        assert payload["source_refs"] == []
        assert manager.get_rfq_calls == 0
        assert manager.get_rfq_stages_calls == 0
        assert intelligence.get_snapshot_calls == 0
        assert _log_values(caplog, "phase5.confidence_marker_emitted")[-1] is False
    finally:
        _clear_step6_dependencies(app)


def test_pipeline_rfq_profile_reuses_stage_fetch_with_single_manager_get_rfq_call(
    client, app
):
    fake_azure = FakeAzureOpenAIConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
    _override_step6_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        session_id = _create_session(client, mode="rfq", rfq_id=str(uuid.uuid4()))
        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "Who owns this RFQ and when is the deadline?"},
        )

        payload = response.json()
        assert response.status_code == 200
        assert manager.get_rfq_calls == 1
        assert manager.get_rfq_stages_calls == 0
        assert intelligence.get_snapshot_calls == 0
        assert payload["source_refs"][0]["artifact"] == "rfq"
    finally:
        _clear_step6_dependencies(app)


def test_pipeline_capability_status_turn_skips_tool_retrieval_calls(client, app):
    fake_azure = FakeAzureOpenAIConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
    _override_step6_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        session_id = _create_session(client, mode="rfq", rfq_id=str(uuid.uuid4()))
        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "What is the briefing?"},
        )

        payload = response.json()
        assert response.status_code == 200
        assert payload["source_refs"] == []
        assert payload["content"].startswith("I don't have grounded facts for")
        assert manager.get_rfq_calls == 1
        assert manager.get_rfq_stages_calls == 0
        assert intelligence.get_snapshot_calls == 0
    finally:
        _clear_step6_dependencies(app)


def test_pipeline_stage_resolution_failure_degrades_for_non_retrieval_turn(
    client, app, caplog
):
    fake_azure = FakeAzureOpenAIConnector()
    manager = CountingManagerConnector(fail_get_rfq=True)
    intelligence = CountingIntelligenceConnector()
    _override_step6_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        with caplog.at_level(logging.INFO):
            session_id = _create_session(client, mode="rfq", rfq_id=str(uuid.uuid4()))
            response = client.post(
                f"/rfq-chatbot/v1/sessions/{session_id}/turn",
                json={"content": "Hello"},
            )

        payload = response.json()
        assert response.status_code == 200
        assert payload["source_refs"] == []
        assert "upstream_service_error" in _log_values(caplog, "phase5.stage_resolved")
    finally:
        _clear_step6_dependencies(app)


def test_pipeline_stage_resolution_failure_with_profile_query_surfaces_503(client, app):
    fake_azure = FakeAzureOpenAIConnector()
    manager = CountingManagerConnector(fail_get_rfq=True)
    intelligence = CountingIntelligenceConnector()
    _override_step6_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        session_id = _create_session(client, mode="rfq", rfq_id=str(uuid.uuid4()))
        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "Who owns this RFQ and when is the deadline?"},
        )

        assert response.status_code == 503
        assert response.json()["detail"] == "Manager service request failed"
        assert manager.get_rfq_calls == 2
    finally:
        _clear_step6_dependencies(app)


def test_pipeline_emits_required_phase5_fields_for_standard_turn(client, app, caplog):
    fake_azure = FakeAzureOpenAIConnector()
    manager = CountingManagerConnector()
    intelligence = CountingIntelligenceConnector()
    _override_step6_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=manager,
        intelligence_connector=intelligence,
    )

    try:
        with caplog.at_level(logging.INFO):
            session_id = _create_session(client, mode="rfq", rfq_id=str(uuid.uuid4()))
            response = client.post(
                f"/rfq-chatbot/v1/sessions/{session_id}/turn",
                json={"content": "What stage are we in?"},
            )

        assert response.status_code == 200
        assert _log_values(caplog, "phase5.stage_resolved")
        assert _log_values(caplog, "phase5.role_applied")
        assert _log_values(caplog, "phase5.role_fallback_used")
        assert _log_values(caplog, "phase5.tools_keyword_matched")
        assert _log_values(caplog, "phase5.tools_allowed_after_stage")
        assert _log_values(caplog, "phase5.tools_allowed_after_role")
        assert _log_values(caplog, "phase5.confidence_marker_emitted")
        assert not _log_values(caplog, "phase5.capability_status_hit")
    finally:
        _clear_step6_dependencies(app)
