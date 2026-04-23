import uuid
from dataclasses import dataclass, field
import logging

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
from src.controllers.rfq_response_controller import RfqResponsePlan
from src.controllers.role_controller import RoleController
from src.controllers.stage_controller import StageController
from src.controllers.tool_controller import ToolController
from src.datasources.conversation_datasource import ConversationDatasource
from src.datasources.session_datasource import SessionDatasource
from src.models.conversation import ToolCallRecord
from src.models.envelope import ConfidenceLevel, SourceRef
from src.models.session import ChatbotSessionCreate, SessionMode
from src.models.turn import TurnCreateCommand
from src.tools.common.envelope import build_tool_result_envelope


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
        self.get_rfq_stages_calls += 1
        return {
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


class MissingProfileManagerConnector(FakeManagerConnector):
    def get_rfq(self, rfq_id):
        raise AssertionError("Profile preload intentionally unavailable")


class FakeIntelligenceConnector:
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


class SpyRfqResponseController:
    def __init__(self):
        self.calls: list[dict] = []

    def compose_response_with_retrieval(
        self,
        *,
        user_content,
        rfq_detail,
        preloaded_tool_call_records,
        rfq_id,
        tool_controller,
    ):
        self.calls.append(
            {
                "user_content": user_content,
                "rfq_detail": rfq_detail,
                "preloaded_tool_call_records": preloaded_tool_call_records,
                "rfq_id": rfq_id,
                "tool_controller": tool_controller,
            }
        )
        source_ref = SourceRef(
            system="rfq_manager_ms",
            artifact="rfq",
            locator=f"/rfq-manager/v1/rfqs/{rfq_id}",
        )
        result = build_tool_result_envelope(
            value={"owner": "Sarah"},
            system=source_ref.system,
            artifact=source_ref.artifact,
            locator=source_ref.locator,
            confidence=ConfidenceLevel.DETERMINISTIC,
        )
        record = ToolCallRecord(
            tool_name="get_rfq_profile",
            arguments={"rfq_id": str(rfq_id), "selection_reason": "spy"},
            result=result,
            source_refs=[source_ref],
        )
        return RfqResponsePlan(
            response_mode="FACT_FIELD",
            assistant_text="spy deterministic answer",
            grounded=True,
            source_refs=[source_ref],
            tool_call_records=[record],
            original_response_mode="FACT_FIELD",
            effective_response_mode="FACT_FIELD",
            evidence_sufficient=True,
            tools_planned=("get_rfq_profile",),
            tools_executed=(),
            tools_from_preload=("get_rfq_profile",),
        )


def _build_chat_controller(
    db_session,
    *,
    manager_connector: ManagerConnector | None = None,
    intelligence_connector=None,
    rfq_response_controller=None,
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
        rfq_response_controller=rfq_response_controller,
    )
    return session_ds, conversation_controller, fake_connector, chat_controller


def _log_values(caplog, field_name: str):
    return [record.__dict__[field_name] for record in caplog.records if field_name in record.__dict__]


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


def test_chat_controller_rfq_specific_uses_response_controller_retrieval_path(db_session):
    spy_response_controller = SpyRfqResponseController()
    manager_connector = FakeManagerConnector()
    intelligence_connector = FakeIntelligenceConnector()
    session_ds, conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(
            db_session,
            manager_connector=manager_connector,
            intelligence_connector=intelligence_connector,
            rfq_response_controller=spy_response_controller,
        )
    )
    rfq_id = str(uuid.uuid4())
    chatbot_session = _create_session(
        session_ds,
        mode=SessionMode.RFQ_BOUND,
        rfq_id=rfq_id,
    )
    db_session.commit()

    response = chat_controller.handle_turn(
        chatbot_session.id,
        TurnCreateCommand(content="Who owns this RFQ?"),
    )
    messages = conversation_controller.get_messages(response.conversation_id)
    assistant_message = messages[-1]

    assert len(spy_response_controller.calls) == 1
    call = spy_response_controller.calls[0]
    assert call["user_content"] == "Who owns this RFQ?"
    assert str(call["rfq_id"]) == rfq_id
    assert call["rfq_detail"].rfq_code == "IF-25144"
    assert call["tool_controller"] is chat_controller.tool_controller
    assert [record.tool_name for record in call["preloaded_tool_call_records"]] == [
        "get_rfq_profile",
        "get_rfq_snapshot",
    ]
    assert response.content == "spy deterministic answer"
    assert assistant_message.tool_calls[0]["tool_name"] == "get_rfq_profile"
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


def test_chat_controller_reuses_first_turn_preload_for_mode_driven_retrieval(db_session):
    manager_connector = FakeManagerConnector()
    intelligence_connector = FakeIntelligenceConnector()
    session_ds, _conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(
            db_session,
            manager_connector=manager_connector,
            intelligence_connector=intelligence_connector,
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
        TurnCreateCommand(content="what should I watch out for in this RFQ?"),
    )

    assert response.content.startswith("RFQ advisory\n")
    assert manager_connector.get_rfq_calls == 1
    assert intelligence_connector.get_snapshot_calls == 1
    assert manager_connector.get_rfq_stages_calls == 1
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


def test_chat_controller_phase7b_trace_is_additive_for_rfq_specific(db_session, caplog):
    session_ds, _conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(db_session)
    )
    chatbot_session = _create_session(
        session_ds,
        mode=SessionMode.RFQ_BOUND,
        rfq_id=str(uuid.uuid4()),
    )
    db_session.commit()

    with caplog.at_level(logging.INFO):
        response = chat_controller.handle_turn(
            chatbot_session.id,
            TurnCreateCommand(content="what is the deadline?"),
        )

    assert response.role == "assistant"
    assert _log_values(caplog, "phase6.rfq_response_mode")[-1] == "FACT_FIELD"
    assert _log_values(caplog, "phase6.grounding_required")[-1] is True
    assert _log_values(caplog, "phase6.grounding_satisfied")[-1] is True
    assert _log_values(caplog, "phase6.output_guardrail_result")[-1] == "pass"
    assert _log_values(caplog, "phase5.tools_keyword_matched")[-1] == []
    assert _log_values(caplog, "phase5.tools_allowed_after_stage")[-1] == []
    assert _log_values(caplog, "phase5.tools_allowed_after_role")[-1] == []
    assert _log_values(caplog, "phase7b.response_mode_selected")[-1] == "FACT_FIELD"
    assert _log_values(caplog, "phase7b.response_mode_effective")[-1] == "FACT_FIELD"
    assert _log_values(caplog, "phase7b.evidence_sufficient")[-1] is True
    assert _log_values(caplog, "phase7b.evidence_downgrade_reason")[-1] is None
    assert _log_values(caplog, "phase7b.tools_planned")[-1] == ["get_rfq_profile"]
    assert _log_values(caplog, "phase7b.tools_executed")[-1] == []
    assert _log_values(caplog, "phase7b.tools_from_preload")[-1] == ["get_rfq_profile"]
    assert _log_values(caplog, "phase7b.source_ref_count")[-1] == 1
    assert _log_values(caplog, "phase7b.grounded")[-1] is True
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


def test_chat_controller_domain_knowledge_does_not_emit_phase7b_trace(db_session, caplog):
    session_ds, _conversation_controller, fake_connector, chat_controller = (
        _build_chat_controller(db_session)
    )
    chatbot_session = _create_session(session_ds, mode=SessionMode.PORTFOLIO)
    db_session.commit()

    with caplog.at_level(logging.INFO):
        response = chat_controller.handle_turn(
            chatbot_session.id,
            TurnCreateCommand(content="What is PWHT?"),
        )

    assert response.content == "Phase 3 assistant response"
    assert len(fake_connector.calls) == 1
    assert _log_values(caplog, "phase6.route_selected")[-1] == "direct_llm"
    assert _log_values(caplog, "phase7b.response_mode_selected") == []
    assert _log_values(caplog, "phase7b.response_mode_effective") == []


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
