from src.controllers.conversation_controller import ConversationController
from src.datasources.conversation_datasource import ConversationDatasource
from src.datasources.session_datasource import SessionDatasource
from src.models.session import ChatbotSessionCreate, SessionMode


def test_conversation_controller_creates_and_reuses_conversation(db_session):
    session_ds = SessionDatasource(db_session)
    conversation_ds = ConversationDatasource(db_session)
    controller = ConversationController(conversation_ds, db_session)
    chatbot_session = session_ds.create(
        ChatbotSessionCreate(
            user_id="u1",
            rfq_id=None,
            mode=SessionMode.PORTFOLIO,
            role="estimation_dept_lead",
        )
    )
    db_session.commit()

    first = controller.get_or_create_conversation_for_session(chatbot_session.id)
    second = controller.get_or_create_conversation_for_session(chatbot_session.id)

    assert first.id == second.id
    assert first.session_id == chatbot_session.id


def test_conversation_controller_persists_messages(db_session):
    session_ds = SessionDatasource(db_session)
    conversation_ds = ConversationDatasource(db_session)
    controller = ConversationController(conversation_ds, db_session)
    chatbot_session = session_ds.create(
        ChatbotSessionCreate(
            user_id="u1",
            rfq_id="IF-25144",
            mode=SessionMode.RFQ_BOUND,
            role="estimation_dept_lead",
        )
    )
    db_session.commit()
    conversation = controller.get_or_create_conversation_for_session(chatbot_session.id)

    user_message = controller.create_user_message(conversation.id, "What is PWHT?")
    assistant_message = controller.create_assistant_message(
        conversation.id,
        "PWHT stands for post weld heat treatment.",
    )
    messages = controller.get_messages(conversation.id)

    assert user_message.turn_number == 1
    assert assistant_message.turn_number == 2
    assert [message.role for message in messages] == ["user", "assistant"]
