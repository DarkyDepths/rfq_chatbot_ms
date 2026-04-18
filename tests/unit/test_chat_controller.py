import uuid
from dataclasses import dataclass, field

from src.controllers.chat_controller import ChatController
from src.controllers.context_builder import ContextBuilder
from src.controllers.conversation_controller import ConversationController
from src.controllers.disambiguation_controller import DisambiguationController
from src.controllers.intent_controller import IntentController
from src.controllers.role_controller import RoleController
from src.controllers.stage_controller import StageController
from src.controllers.tool_controller import ToolController
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


def _build_chat_controller(db_session):
    session_ds = SessionDatasource(db_session)
    conversation_controller = ConversationController(
        ConversationDatasource(db_session),
        db_session,
    )
    fake_connector = FakeAzureConnector()
    chat_controller = ChatController(
        session_datasource=session_ds,
        conversation_controller=conversation_controller,
        context_builder=ContextBuilder(),
        azure_openai_connector=fake_connector,
        tool_controller=ToolController(
            manager_connector=FakeManagerConnector(),
            intelligence_connector=FakeIntelligenceConnector(),
        ),
        stage_controller=StageController(manager_connector=FakeManagerConnector()),
        role_controller=RoleController(),
        intent_controller=IntentController(),
        disambiguation_controller=DisambiguationController(),
    )
    return session_ds, conversation_controller, fake_connector, chat_controller


def test_chat_controller_handles_turn_with_real_persistence(db_session):
    session_ds, conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(db_session)
    )
    chatbot_session = session_ds.create(
        ChatbotSessionCreate(
            user_id="u1",
            rfq_id=None,
            mode=SessionMode.PORTFOLIO,
            role="estimation_dept_lead",
        )
    )
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
    assert "user: What is PWHT?" in fake_connector.calls[0]["messages"][1]["content"]


def test_chat_controller_persists_tool_calls_and_source_refs_for_retrieval_turn(
    db_session,
):
    session_ds, conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(db_session)
    )
    rfq_id = str(uuid.uuid4())
    chatbot_session = session_ds.create(
        ChatbotSessionCreate(
            user_id="u1",
            rfq_id=rfq_id,
            mode=SessionMode.RFQ_BOUND,
            role="estimation_dept_lead",
        )
    )
    db_session.commit()

    response = chat_controller.handle_turn(
        chatbot_session.id,
        TurnCreateCommand(content="Who owns this RFQ and when is the deadline?"),
    )
    messages = conversation_controller.get_messages(response.conversation_id)
    assistant_message = messages[-1]

    assert response.role == "assistant"
    assert response.source_refs[0].system == "rfq_manager_ms"
    assert assistant_message.tool_calls[0]["tool_name"] == "get_rfq_profile"
    assert assistant_message.source_refs[0]["artifact"] == "rfq"
    assert "Tool: get_rfq_profile" in fake_connector.calls[0]["messages"][1]["content"]
