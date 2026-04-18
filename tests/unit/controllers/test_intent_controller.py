from types import SimpleNamespace

from src.controllers.intent_controller import IntentController
from src.models.session import SessionMode


def _session(mode: SessionMode):
    return SimpleNamespace(mode=mode)


def test_unsupported_keyword_wins_over_rfq_specific_keyword():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="what's the briefing deadline?",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
    )

    assert result.intent == "unsupported"


def test_disambiguation_fires_for_rfq_reference_in_portfolio_session():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="tell me about this RFQ",
        session=_session(SessionMode.PORTFOLIO),
        last_assistant_content=None,
    )

    assert result.intent == "disambiguation"


def test_disambiguation_does_not_fire_for_same_reference_in_rfq_bound_session():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="tell me about this RFQ",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
    )

    assert result.intent == "rfq_specific"


def test_what_is_pwht_in_portfolio_session_is_general_knowledge():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="what is PWHT?",
        session=_session(SessionMode.PORTFOLIO),
        last_assistant_content=None,
    )

    assert result.intent == "general_knowledge"


def test_what_is_pwht_in_rfq_bound_session_is_general_knowledge():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="what is PWHT?",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
    )

    assert result.intent == "general_knowledge"


def test_deadline_question_in_rfq_bound_session_is_rfq_specific():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="what's the deadline?",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
    )

    assert result.intent == "rfq_specific"


def test_deadline_question_in_portfolio_session_is_disambiguation():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="what's the deadline?",
        session=_session(SessionMode.PORTFOLIO),
        last_assistant_content=None,
    )

    assert result.intent == "disambiguation"


def test_hello_is_conversational():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="hello copilot",
        session=_session(SessionMode.PORTFOLIO),
        last_assistant_content=None,
    )

    assert result.intent == "conversational"


def test_briefing_question_is_unsupported():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="what's the briefing?",
        session=_session(SessionMode.PORTFOLIO),
        last_assistant_content=None,
    )

    assert result.intent == "unsupported"


def test_random_unrecognized_text_defaults_to_conversational():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="zxv qqq lorem",
        session=_session(SessionMode.PORTFOLIO),
        last_assistant_content=None,
    )

    assert result.intent == "conversational"


def test_disambiguation_resolution_short_rfq_selector_reclassifies_to_rfq_specific():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="IF-25144",
        session=_session(SessionMode.PORTFOLIO),
        last_assistant_content="Which RFQ are you referring to?",
    )

    assert result.intent == "rfq_specific"
    assert result.disambiguation_resolved is True
    assert result.resolved_rfq_reference == "IF-25144"
    assert result.disambiguation_abandoned is False


def test_disambiguation_resolution_can_be_abandoned_with_general_knowledge_follow_up():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="never mind, what is PWHT?",
        session=_session(SessionMode.PORTFOLIO),
        last_assistant_content="Which RFQ are you referring to?",
    )

    assert result.intent == "general_knowledge"
    assert result.disambiguation_resolved is False
    assert result.resolved_rfq_reference is None
    assert result.disambiguation_abandoned is True


def test_disambiguation_resolution_can_be_abandoned_with_conversational_turn():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="hello",
        session=_session(SessionMode.PORTFOLIO),
        last_assistant_content="Which RFQ are you referring to?",
    )

    assert result.intent == "conversational"
    assert result.disambiguation_resolved is False
    assert result.resolved_rfq_reference is None
    assert result.disambiguation_abandoned is True


def test_without_disambiguation_prompt_uses_normal_classification_and_flags_false():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="what is PWHT?",
        session=_session(SessionMode.PORTFOLIO),
        last_assistant_content="Sure, let's continue.",
    )

    assert result.intent == "general_knowledge"
    assert result.disambiguation_resolved is False
    assert result.resolved_rfq_reference is None
    assert result.disambiguation_abandoned is False


def test_empty_user_content_defaults_to_conversational():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="",
        session=_session(SessionMode.PORTFOLIO),
        last_assistant_content=None,
    )

    assert result.intent == "conversational"


def test_whitespace_user_content_defaults_to_conversational():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="   \t  ",
        session=_session(SessionMode.PORTFOLIO),
        last_assistant_content=None,
    )

    assert result.intent == "conversational"
