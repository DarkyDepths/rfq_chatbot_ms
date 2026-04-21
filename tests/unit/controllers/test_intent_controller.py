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


def test_what_is_pwht_in_portfolio_session_is_domain_knowledge():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="what is PWHT?",
        session=_session(SessionMode.PORTFOLIO),
        last_assistant_content=None,
    )

    assert result.intent == "domain_knowledge"


def test_what_is_pwht_in_rfq_bound_session_is_domain_knowledge():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="what is PWHT?",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
    )

    assert result.intent == "domain_knowledge"


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


def test_hello_is_conversational_in_portfolio_and_rfq_bound_modes():
    controller = IntentController()

    portfolio_result = controller.classify_intent(
        user_content="hello copilot",
        session=_session(SessionMode.PORTFOLIO),
        last_assistant_content=None,
    )
    rfq_bound_result = controller.classify_intent(
        user_content="hello copilot",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
    )

    assert portfolio_result.intent == "conversational"
    assert rfq_bound_result.intent == "conversational"


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


def test_disambiguation_resolution_can_be_abandoned_with_domain_knowledge_follow_up():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="never mind, what is PWHT?",
        session=_session(SessionMode.PORTFOLIO),
        last_assistant_content="Which RFQ are you referring to?",
    )

    assert result.intent == "domain_knowledge"
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

    assert result.intent == "domain_knowledge"
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


def test_short_ambiguous_follow_up_uses_rfq_specific_continuity_tiebreaker():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="and this one?",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
        last_resolved_intent="rfq_specific",
    )

    assert result.intent == "rfq_specific"


def test_clear_domain_knowledge_signal_overrides_rfq_continuity_tiebreaker():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="what is pwht?",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
        last_resolved_intent="rfq_specific",
    )

    assert result.intent == "domain_knowledge"


# ──────────────────────────────────────────────
# Phase 6.5: Domain boundary tests
# ──────────────────────────────────────────────

def test_bread_question_is_out_of_scope():
    """'how to prepare bread at home' matches explanatory patterns but no domain terms → out_of_scope."""
    controller = IntentController()

    result = controller.classify_intent(
        user_content="how to prepare bread at home",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
    )

    assert result.intent == "out_of_scope"


def test_weather_is_out_of_scope():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="what is the weather today?",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
    )

    assert result.intent == "out_of_scope"


def test_purchase_order_is_domain_knowledge():
    """'what is a purchase order?' contains tier 2 term → domain_knowledge."""
    controller = IntentController()

    result = controller.classify_intent(
        user_content="what is a purchase order?",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
    )

    assert result.intent == "domain_knowledge"


def test_asme_is_domain_knowledge():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="explain ASME Section VIII",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
    )

    assert result.intent == "domain_knowledge"


# ──────────────────────────────────────────────
# Phase 6.5: Conversational sub-type tests
# ──────────────────────────────────────────────

def test_hello_has_greeting_subtype():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="hello",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
    )

    assert result.intent == "conversational"
    assert result.conversational_subtype == "greeting"


def test_who_are_you_has_identity_subtype():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="who are you?",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
    )

    assert result.intent == "conversational"
    assert result.conversational_subtype == "identity"


def test_thanks_has_thanks_subtype():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="thanks!",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
    )

    assert result.intent == "conversational"
    assert result.conversational_subtype == "thanks"


def test_goodbye_has_goodbye_subtype():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="goodbye",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
    )

    assert result.intent == "conversational"
    assert result.conversational_subtype == "goodbye"


def test_never_mind_has_reset_subtype():
    controller = IntentController()

    result = controller.classify_intent(
        user_content="never mind",
        session=_session(SessionMode.RFQ_BOUND),
        last_assistant_content=None,
    )

    assert result.intent == "conversational"
    assert result.conversational_subtype == "reset"
