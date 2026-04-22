import uuid
from dataclasses import dataclass, field

from src.app_context import (
    get_azure_openai_connector,
    get_intelligence_connector,
    get_manager_connector,
)
from src.connectors.azure_openai_connector import ChatCompletionResult
from src.models.conversation import Message
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


@dataclass
class FakeAzureOpenAIConnector:
    calls: list = field(default_factory=list)

    def create_chat_completion(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        prompt = messages[-1]["content"]
        if (
            "Selection reason: User asked for the current RFQ snapshot or currently known facts"
            in prompt
            and '"overall_status": "partial"' in prompt
        ):
            return ChatCompletionResult(
                assistant_text=(
                    "The current RFQ snapshot is partial and intelligence briefing is available."
                )
            )

        if (
            "Selection reason: User asked about RFQ profile metadata from manager" in prompt
            and '"owner": "Sarah"' in prompt
            and '"deadline": "2026-05-01"' in prompt
        ):
            return ChatCompletionResult(
                assistant_text="The RFQ owner is Sarah and the deadline is 2026-05-01."
            )
        return ChatCompletionResult(assistant_text=f"assistant-response-{len(self.calls)}")


class FakeManagerConnector(ManagerConnector):
    def __init__(self, *, fail=False):
        self.fail = fail

    def get_rfq(self, rfq_id):
        if self.fail:
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
                briefing_panel_summary=SnapshotBriefingPanelSummary(
                    status="available",
                    executive_summary="Known summary",
                ),
                workbook_panel=SnapshotWorkbookPanel(status="not_ready"),
                review_panel=SnapshotReviewPanel(
                    status="not_ready",
                    active_findings_count=0,
                ),
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


def _override_phase4_dependencies(app, *, azure_connector, manager_connector=None):
    app.dependency_overrides[get_azure_openai_connector] = lambda: azure_connector
    app.dependency_overrides[get_manager_connector] = (
        lambda: manager_connector or FakeManagerConnector()
    )
    app.dependency_overrides[get_intelligence_connector] = (
        lambda: FakeIntelligenceConnector()
    )


def _clear_phase4_dependencies(app):
    app.dependency_overrides.pop(get_azure_openai_connector, None)
    app.dependency_overrides.pop(get_manager_connector, None)
    app.dependency_overrides.pop(get_intelligence_connector, None)


def test_first_turn_creates_conversation_and_persists_messages(client, app):
    fake_azure = FakeAzureOpenAIConnector()
    _override_phase4_dependencies(app, azure_connector=fake_azure)
    try:
        session_response = client.post(
            "/rfq-chatbot/v1/sessions",
            json={"mode": "global", "user_id": "chat-user"},
        )
        session_id = session_response.json()["id"]

        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "Hello copilot"},
        )
        payload = response.json()

        assert response.status_code == 200
        assert payload["conversation_id"]
        assert payload["role"] == "assistant"
        assert payload["content"] == "Hi! I'm RFQ Copilot. How can I help with your RFQs?"
        assert len(fake_azure.calls) == 0

        readback = client.get(
            f"/rfq-chatbot/v1/conversations/{payload['conversation_id']}"
        )
        history = readback.json()["messages"]

        assert readback.status_code == 200
        assert [message["role"] for message in history] == ["user", "assistant"]
    finally:
        _clear_phase4_dependencies(app)


def test_second_turn_reuses_conversation_and_history(client, app):
    fake_azure = FakeAzureOpenAIConnector()
    _override_phase4_dependencies(app, azure_connector=fake_azure)
    try:
        session_response = client.post(
            "/rfq-chatbot/v1/sessions",
            json={"mode": "global", "user_id": "chat-user"},
        )
        session_id = session_response.json()["id"]

        first_turn = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "what is PWHT?"},
        )
        second_turn = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "how does RT work?"},
        )

        assert first_turn.status_code == 200
        assert second_turn.status_code == 200
        assert (
            first_turn.json()["conversation_id"] == second_turn.json()["conversation_id"]
        )

        readback = client.get(
            f"/rfq-chatbot/v1/conversations/{first_turn.json()['conversation_id']}"
        )
        history = readback.json()["messages"]

        assert [message["content"] for message in history] == [
            "what is PWHT?",
            "assistant-response-1",
            "how does RT work?",
            "assistant-response-2",
        ]
    finally:
        _clear_phase4_dependencies(app)


def test_post_turn_returns_404_for_missing_session(client, app):
    fake_azure = FakeAzureOpenAIConnector()
    _override_phase4_dependencies(app, azure_connector=fake_azure)
    try:
        response = client.post(
            f"/rfq-chatbot/v1/sessions/{uuid.uuid4()}/turn",
            json={"content": "Hello copilot"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    finally:
        _clear_phase4_dependencies(app)


def test_get_conversation_returns_404_for_missing_conversation(client):
    response = client.get(f"/rfq-chatbot/v1/conversations/{uuid.uuid4()}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_turn_with_manager_backed_retrieval_returns_grounded_answer(client, app):
    fake_azure = FakeAzureOpenAIConnector()
    _override_phase4_dependencies(app, azure_connector=fake_azure)
    rfq_id = str(uuid.uuid4())
    try:
        session_response = client.post(
            "/rfq-chatbot/v1/sessions",
            json={"mode": "rfq", "user_id": "chat-user", "rfq_id": rfq_id},
        )
        session_id = session_response.json()["id"]

        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "Who owns this RFQ and when is the deadline?"},
        )

        assert response.status_code == 200
        assert "Sarah" in response.json()["content"]
        assert "2026-05-01" in response.json()["content"]
        assert response.json()["source_refs"][0]["system"] == "rfq_manager_ms"
        assert len(fake_azure.calls) == 0

        readback = client.get(
            f"/rfq-chatbot/v1/conversations/{response.json()['conversation_id']}"
        )
        assert readback.json()["messages"][1]["source_refs"][0]["artifact"] == "rfq"
    finally:
        _clear_phase4_dependencies(app)


def test_turn_with_intelligence_backed_retrieval_returns_grounded_answer(client, app):
    fake_azure = FakeAzureOpenAIConnector()
    _override_phase4_dependencies(app, azure_connector=fake_azure)
    rfq_id = str(uuid.uuid4())
    try:
        session_response = client.post(
            "/rfq-chatbot/v1/sessions",
            json={"mode": "rfq", "user_id": "chat-user", "rfq_id": rfq_id},
        )
        session_id = session_response.json()["id"]

        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "Give me the current snapshot summary for this RFQ"},
        )

        assert response.status_code == 200
        content = response.json()["content"]
        assert "Boiler Upgrade" in content
        assert "Acme Industrial" in content
        assert "partial" in content.lower()
        assert "briefing" in content.lower()
        assert any(
            source_ref["system"] == "rfq_intelligence_ms"
            for source_ref in response.json()["source_refs"]
        )
        assert len(fake_azure.calls) == 0
    finally:
        _clear_phase4_dependencies(app)


def test_downstream_failure_is_surfaced_explicitly(client, app):
    fake_azure = FakeAzureOpenAIConnector()
    _override_phase4_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=FakeManagerConnector(fail=True),
    )
    rfq_id = str(uuid.uuid4())
    try:
        session_response = client.post(
            "/rfq-chatbot/v1/sessions",
            json={"mode": "rfq", "user_id": "chat-user", "rfq_id": rfq_id},
        )
        session_id = session_response.json()["id"]

        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "Who owns this RFQ and when is the deadline?"},
        )

        assert response.status_code == 200
        assert response.json()["source_refs"] == []
        content = response.json()["content"].lower()
        assert "don't have grounded" in content
        assert "owner" in content
        assert "deadline" in content
        assert len(fake_azure.calls) == 0
    finally:
        _clear_phase4_dependencies(app)


def test_downstream_failure_persists_turn_under_graceful_degradation(client, app, db_session):
    fake_azure = FakeAzureOpenAIConnector()
    _override_phase4_dependencies(
        app,
        azure_connector=fake_azure,
        manager_connector=FakeManagerConnector(fail=True),
    )
    rfq_id = str(uuid.uuid4())
    try:
        session_response = client.post(
            "/rfq-chatbot/v1/sessions",
            json={"mode": "rfq", "user_id": "chat-user", "rfq_id": rfq_id},
        )
        session_id = session_response.json()["id"]

        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "Who owns this RFQ and when is the deadline?"},
        )

        assert response.status_code == 200
        assert db_session.query(Message).count() == 2
    finally:
        _clear_phase4_dependencies(app)


def test_retrieval_with_human_readable_rfq_code_fails_clearly(client, app):
    fake_azure = FakeAzureOpenAIConnector()
    _override_phase4_dependencies(app, azure_connector=fake_azure)
    try:
        session_response = client.post(
            "/rfq-chatbot/v1/sessions",
            json={"mode": "rfq", "user_id": "chat-user", "rfq_id": "IF-25144"},
        )
        session_id = session_response.json()["id"]

        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "Who owns this RFQ and when is the deadline?"},
        )

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "Phase 5 retrieval requires session.rfq_id to be a downstream UUID. "
            "Human-readable RFQ codes like 'IF-25144' are not supported here yet."
        )
    finally:
        _clear_phase4_dependencies(app)


def test_invalid_rfq_code_failure_does_not_persist_user_message(client, app, db_session):
    fake_azure = FakeAzureOpenAIConnector()
    _override_phase4_dependencies(app, azure_connector=fake_azure)
    try:
        session_response = client.post(
            "/rfq-chatbot/v1/sessions",
            json={"mode": "rfq", "user_id": "chat-user", "rfq_id": "IF-25144"},
        )
        session_id = session_response.json()["id"]

        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "Who owns this RFQ and when is the deadline?"},
        )

        assert response.status_code == 422
        assert db_session.query(Message).count() == 0
    finally:
        _clear_phase4_dependencies(app)


def test_ambiguous_retrieval_request_fails_clearly(client, app):
    fake_azure = FakeAzureOpenAIConnector()
    _override_phase4_dependencies(app, azure_connector=fake_azure)
    rfq_id = str(uuid.uuid4())
    try:
        session_response = client.post(
            "/rfq-chatbot/v1/sessions",
            json={"mode": "rfq", "user_id": "chat-user", "rfq_id": rfq_id},
        )
        session_id = session_response.json()["id"]

        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "Give me the current snapshot and deadline for this RFQ"},
        )

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "This retrieval request is ambiguous; ask for one RFQ fact at a time"
        )
    finally:
        _clear_phase4_dependencies(app)


def test_ambiguous_retrieval_failure_does_not_persist_user_message(client, app, db_session):
    fake_azure = FakeAzureOpenAIConnector()
    _override_phase4_dependencies(app, azure_connector=fake_azure)
    rfq_id = str(uuid.uuid4())
    try:
        session_response = client.post(
            "/rfq-chatbot/v1/sessions",
            json={"mode": "rfq", "user_id": "chat-user", "rfq_id": rfq_id},
        )
        session_id = session_response.json()["id"]

        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "Give me the current snapshot and deadline for this RFQ"},
        )

        assert response.status_code == 422
        assert db_session.query(Message).count() == 0
    finally:
        _clear_phase4_dependencies(app)


def test_unsupported_retrieval_returns_capability_status_and_persists_messages(
    client, app, db_session
):
    fake_azure = FakeAzureOpenAIConnector()
    _override_phase4_dependencies(app, azure_connector=fake_azure)
    rfq_id = str(uuid.uuid4())
    try:
        session_response = client.post(
            "/rfq-chatbot/v1/sessions",
            json={"mode": "rfq", "user_id": "chat-user", "rfq_id": rfq_id},
        )
        session_id = session_response.json()["id"]

        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "What is the grand total of this RFQ?"},
        )
        payload = response.json()

        assert response.status_code == 200
        assert payload["role"] == "assistant"
        assert payload["content"] == "assistant-response-1"
        assert payload["source_refs"] == []
        assert db_session.query(Message).count() == 2
    finally:
        _clear_phase4_dependencies(app)


def test_global_mode_capability_status_question_returns_valid_turn_response(client, app):
    fake_azure = FakeAzureOpenAIConnector()
    _override_phase4_dependencies(app, azure_connector=fake_azure)
    try:
        session_response = client.post(
            "/rfq-chatbot/v1/sessions",
            json={"mode": "global", "user_id": "chat-user"},
        )
        session_id = session_response.json()["id"]

        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": "what is the briefing?"},
        )
        payload = response.json()

        assert response.status_code == 200
        assert response.status_code != 422
        assert payload["role"] == "assistant"
        assert payload["source_refs"] == []
        assert payload["content"]
    finally:
        _clear_phase4_dependencies(app)
