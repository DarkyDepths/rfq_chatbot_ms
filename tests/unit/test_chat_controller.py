import uuid
from dataclasses import dataclass, field

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
from src.controllers.chat_controller import ChatController
from src.controllers.context_builder import ContextBuilder
from src.controllers.conversation_controller import ConversationController
from src.controllers.disambiguation_controller import DisambiguationController
from src.controllers.intent_controller import IntentController
from src.controllers.role_controller import RoleController
from src.controllers.stage_controller import StageController
from src.controllers.tool_controller import ToolController
from src.datasources.conversation_datasource import ConversationDatasource
from src.datasources.session_datasource import SessionDatasource
from src.models.session import ChatbotSessionCreate, SessionMode
from src.models.turn import TurnCreateCommand


@dataclass
class FakeAzureConnector:
    calls: list = field(default_factory=list)

    def create_chat_completion(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})

        class _Result:
            assistant_text = "Phase 3 assistant response"

        return _Result()


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
        raise AssertionError("Stage retrieval should not be called in this test")


class MissingProfileManagerConnector(FakeManagerConnector):
    def get_rfq(self, rfq_id):
        raise AssertionError("Profile preload intentionally unavailable")


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


def _build_chat_controller(
    db_session,
    *,
    manager_connector: ManagerConnector | None = None,
    intelligence_connector=None,
):
    session_ds = SessionDatasource(db_session)
    conversation_controller = ConversationController(
        ConversationDatasource(db_session),
        db_session,
    )
    fake_connector = FakeAzureConnector()
    manager_connector = manager_connector or FakeManagerConnector()
    intelligence_connector = intelligence_connector or FakeIntelligenceConnector()
    chat_controller = ChatController(
        session_datasource=session_ds,
        conversation_controller=conversation_controller,
        context_builder=ContextBuilder(),
        azure_openai_connector=fake_connector,
        tool_controller=ToolController(
            manager_connector=manager_connector,
            intelligence_connector=intelligence_connector,
        ),
        stage_controller=StageController(manager_connector=manager_connector),
        role_controller=RoleController(),
        intent_controller=IntentController(),
        disambiguation_controller=DisambiguationController(),
    )
    return session_ds, conversation_controller, fake_connector, chat_controller


def _create_session(session_ds, *, mode: SessionMode, rfq_id: str | None = None):
    return session_ds.create(
        ChatbotSessionCreate(
            user_id="u1",
            rfq_id=rfq_id,
            mode=mode,
            role="estimation_dept_lead",
        )
    )


def test_chat_controller_handles_turn_with_real_persistence(db_session):
    session_ds, conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(db_session)
    )
    chatbot_session = _create_session(session_ds, mode=SessionMode.PORTFOLIO)
    db_session.commit()

    response = chat_controller.handle_turn(
        chatbot_session.id,
        TurnCreateCommand(content="What is PWHT?"),
    )
    messages = conversation_controller.get_messages(response.conversation_id)

    assert response.role == "assistant"
    assert response.content == "Phase 3 assistant response"
    assert [message.role for message in messages] == ["user", "assistant"]
    assert fake_connector.calls[0]["messages"][0]["role"] == "system"
    assert fake_connector.calls[0]["messages"][-1]["role"] == "user"
    assert "Latest user turn:" in fake_connector.calls[0]["messages"][-1]["content"]
    assert "What is PWHT?" in fake_connector.calls[0]["messages"][-1]["content"]


def test_chat_controller_persists_tool_calls_and_source_refs_for_retrieval_turn(
    db_session,
):
    session_ds, conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(db_session)
    )
    chatbot_session = _create_session(
        session_ds,
        mode=SessionMode.RFQ_BOUND,
        rfq_id=str(uuid.uuid4()),
    )
    db_session.commit()

    response = chat_controller.handle_turn(
        chatbot_session.id,
        TurnCreateCommand(content="Who owns this RFQ and when is the deadline?"),
    )
    messages = conversation_controller.get_messages(response.conversation_id)
    assistant_message = messages[-1]

    assert response.role == "assistant"
    assert "The RFQ owner is Sarah." in response.content
    assert "The RFQ deadline is 2026-05-01." in response.content
    assert response.source_refs[0].system == "rfq_manager_ms"
    assert any(tool_call["tool_name"] == "get_rfq_profile" for tool_call in assistant_message.tool_calls)
    assert assistant_message.source_refs[0]["artifact"] == "rfq"
    assert len(fake_connector.calls) == 0


def test_chat_controller_builds_grounded_watchouts_without_azure(db_session):
    session_ds, _conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(db_session)
    )
    chatbot_session = _create_session(
        session_ds,
        mode=SessionMode.RFQ_BOUND,
        rfq_id=str(uuid.uuid4()),
    )
    db_session.commit()

    response = chat_controller.handle_turn(
        chatbot_session.id,
        TurnCreateCommand(content="what should I watch out for in this RFQ?"),
    )

    assert response.role == "assistant"
    assert response.content.startswith("RFQ advisory\n")
    assert "Main concerns\n" in response.content
    assert "Missing / incomplete\n" in response.content
    assert "What needs attention\n" in response.content
    assert len(response.source_refs) >= 1
    assert len(fake_connector.calls) == 0


def test_chat_controller_summary_turn_is_structured_and_skips_azure(db_session):
    session_ds, _conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(db_session)
    )
    chatbot_session = _create_session(
        session_ds,
        mode=SessionMode.RFQ_BOUND,
        rfq_id=str(uuid.uuid4()),
    )
    db_session.commit()

    response = chat_controller.handle_turn(
        chatbot_session.id,
        TurnCreateCommand(content="tell me about this rfq"),
    )

    assert response.role == "assistant"
    assert response.content.startswith("RFQ summary\n")
    assert "Readiness\n" in response.content
    assert len(fake_connector.calls) == 0


def test_chat_controller_detail_turn_is_structured_and_skips_azure(db_session):
    session_ds, _conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(db_session)
    )
    chatbot_session = _create_session(
        session_ds,
        mode=SessionMode.RFQ_BOUND,
        rfq_id=str(uuid.uuid4()),
    )
    db_session.commit()

    response = chat_controller.handle_turn(
        chatbot_session.id,
        TurnCreateCommand(content="what is the current details about this rfq"),
    )

    assert response.role == "assistant"
    assert response.content.startswith("Current RFQ details\n")
    assert "Core facts\n" in response.content
    assert "Intelligence state\n" in response.content
    assert len(fake_connector.calls) == 0


def test_chat_controller_first_turn_greeting_is_deterministic_and_skips_azure(db_session):
    session_ds, _conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(db_session)
    )
    chatbot_session = _create_session(
        session_ds,
        mode=SessionMode.RFQ_BOUND,
        rfq_id=str(uuid.uuid4()),
    )
    db_session.commit()

    response = chat_controller.handle_turn(
        chatbot_session.id,
        TurnCreateCommand(content="hello"),
    )

    assert response.role == "assistant"
    assert len(fake_connector.calls) == 0
    assert "Boiler Upgrade" in response.content
    assert "Acme Industrial" in response.content
    assert "Review" in response.content
    assert "Unavailable" not in response.content


def test_chat_controller_greeting_without_profile_omits_unavailable(db_session):
    session_ds, _conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(
            db_session,
            manager_connector=MissingProfileManagerConnector(),
        )
    )
    chatbot_session = _create_session(
        session_ds,
        mode=SessionMode.RFQ_BOUND,
        rfq_id=str(uuid.uuid4()),
    )
    db_session.commit()

    response = chat_controller.handle_turn(
        chatbot_session.id,
        TurnCreateCommand(content="hello"),
    )

    assert response.role == "assistant"
    assert len(fake_connector.calls) == 0
    assert response.content == "Hi! I'm ready to help with this RFQ. What would you like to check?"
    assert "Unavailable" not in response.content


def test_chat_controller_identity_is_deterministic_and_skips_azure(db_session):
    session_ds, _conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(db_session)
    )
    chatbot_session = _create_session(session_ds, mode=SessionMode.PORTFOLIO)
    db_session.commit()

    response = chat_controller.handle_turn(
        chatbot_session.id,
        TurnCreateCommand(content="who are you?"),
    )

    assert response.content == "I'm RFQ Copilot, your estimation assistant for RFQs."
    assert len(fake_connector.calls) == 0


def test_chat_controller_thanks_goodbye_and_reset_skip_azure(db_session):
    session_ds, _conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(db_session)
    )

    cases = {
        "thanks": "You're welcome.",
        "goodbye": "Goodbye.",
        "never mind": "No problem. We can start fresh. What would you like to check?",
        "reset": "No problem. We can start fresh. What would you like to check?",
        "start over": "No problem. We can start fresh. What would you like to check?",
    }

    for content, expected in cases.items():
        chatbot_session = _create_session(session_ds, mode=SessionMode.PORTFOLIO)
        db_session.commit()

        response = chat_controller.handle_turn(
            chatbot_session.id,
            TurnCreateCommand(content=content),
        )

        assert response.content == expected

    assert len(fake_connector.calls) == 0


def test_chat_controller_repeat_turn_uses_selected_history_for_azure_messages(db_session):
    session_ds, conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(db_session)
    )
    chatbot_session = _create_session(session_ds, mode=SessionMode.PORTFOLIO)
    db_session.commit()

    conversation = conversation_controller.get_or_create_conversation_for_session(chatbot_session.id)
    conversation_controller.create_user_message(conversation.id, "old user")
    conversation_controller.create_assistant_message(
        conversation.id,
        "old assistant",
        tool_calls=[],
        source_refs=[],
    )
    conversation_controller.create_user_message(conversation.id, "keep user 1")
    conversation_controller.create_assistant_message(
        conversation.id,
        "keep assistant 1",
        tool_calls=[],
        source_refs=[],
    )
    conversation_controller.create_user_message(conversation.id, "keep user 2")
    db_session.commit()

    response = chat_controller.handle_turn(
        chatbot_session.id,
        TurnCreateCommand(content="say that again"),
    )

    assert response.content == "Phase 3 assistant response"
    azure_messages = fake_connector.calls[0]["messages"]
    assert [message["content"] for message in azure_messages[1:-1]] == [
        "keep user 1",
        "keep assistant 1",
        "keep user 2",
    ]
