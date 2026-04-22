from src.config.capability_status import CAPABILITY_STATUS_ENTRIES
from src.config.intent_patterns import (
    DOMAIN_VOCABULARY,
    DOMAIN_VOCAB_TIER1,
    DOMAIN_VOCAB_TIER2,
    FALLBACK_INTENT,
    INTENT_PATTERNS,
    classify_conversational_subtype,
    get_out_of_scope_refusal,
    message_contains_domain_term,
    message_is_knowledge_like_turn,
    response_contains_off_domain_content,
    OUT_OF_SCOPE_REFUSALS,
)


ALLOWED_INTENTS = {
    "rfq_specific",
    "domain_knowledge",
    "unsupported",
    "disambiguation",
    "conversational",
}


def test_fallback_intent_is_conversational():
    assert FALLBACK_INTENT == "conversational"


def test_intent_patterns_use_only_allowed_intent_taxonomy():
    intents = {entry["intent"] for entry in INTENT_PATTERNS}
    assert intents.issubset(ALLOWED_INTENTS)
    assert intents.difference(ALLOWED_INTENTS) == set()


def test_unsupported_patterns_precede_rfq_specific_patterns():
    unsupported_indices = [
        index for index, entry in enumerate(INTENT_PATTERNS) if entry["intent"] == "unsupported"
    ]
    rfq_specific_indices = [
        index for index, entry in enumerate(INTENT_PATTERNS) if entry["intent"] == "rfq_specific"
    ]

    assert unsupported_indices
    assert rfq_specific_indices
    assert max(unsupported_indices) < min(rfq_specific_indices)


def test_unsupported_keywords_align_with_capability_status_entries():
    capability_keywords = set(CAPABILITY_STATUS_ENTRIES.keys())

    for entry in INTENT_PATTERNS:
        if entry["intent"] != "unsupported":
            continue
        for keyword in entry["keywords"]:
            assert keyword in capability_keywords


# ──────────────────────────────────────────────
# Phase 6.5: Domain vocabulary gate tests
# ──────────────────────────────────────────────

def test_domain_vocab_tier1_and_tier2_are_nonempty():
    assert len(DOMAIN_VOCAB_TIER1) > 0
    assert len(DOMAIN_VOCAB_TIER2) > 0


def test_domain_vocabulary_is_union_of_tiers():
    assert DOMAIN_VOCABULARY == DOMAIN_VOCAB_TIER1 | DOMAIN_VOCAB_TIER2


def test_message_contains_domain_term_pwht():
    assert message_contains_domain_term("what is PWHT?") is True


def test_message_contains_domain_term_bread():
    assert message_contains_domain_term("how to prepare bread at home") is False


def test_message_contains_domain_term_purchase_order():
    assert message_contains_domain_term("explain purchase order") is True


def test_message_contains_domain_term_rejects_weak_household_material_context():
    assert message_contains_domain_term(
        "what stainless steel should I use for my home sink?"
    ) is False


def test_message_contains_domain_term_rejects_weak_household_component_context():
    assert message_contains_domain_term(
        "can you help me pick a valve for my garden hose?"
    ) is False


def test_message_contains_domain_term_accepts_strong_domain_signal_with_weak_term():
    assert message_contains_domain_term(
        "what stainless steel grade is typical for ASME Section VIII vessels?"
    ) is True


def test_message_is_knowledge_like_turn_handles_informal_entity_question():
    assert message_is_knowledge_like_turn("do u know about aramco?") is True


def test_message_is_knowledge_like_turn_handles_meaning_question():
    assert message_is_knowledge_like_turn(
        "brown field and green field what do they mean"
    ) is True


def test_message_is_knowledge_like_turn_handles_general_question_form():
    assert message_is_knowledge_like_turn("what's aramco?") is True


def test_message_is_knowledge_like_turn_rejects_plain_statement():
    assert message_is_knowledge_like_turn("please review the attached sheet") is False


# ──────────────────────────────────────────────
# Phase 6.5: Conversational sub-type tests
# ──────────────────────────────────────────────

def test_classify_conversational_subtype_greeting():
    assert classify_conversational_subtype("hello") == "greeting"


def test_classify_conversational_subtype_identity():
    assert classify_conversational_subtype("who are you") == "identity"


def test_classify_conversational_subtype_thanks():
    assert classify_conversational_subtype("thanks!") == "thanks"


def test_classify_conversational_subtype_generic():
    assert classify_conversational_subtype("random question here") == "generic"


def test_classify_conversational_subtype_uses_phrase_boundaries():
    assert classify_conversational_subtype("which option is better?") != "greeting"
    assert classify_conversational_subtype("this seems wrong") != "greeting"
    assert classify_conversational_subtype("what do you think?") != "greeting"


def test_classify_conversational_subtype_reset_variants():
    assert classify_conversational_subtype("never mind") == "reset"
    assert classify_conversational_subtype("reset") == "reset"
    assert classify_conversational_subtype("start over") == "reset"


# ──────────────────────────────────────────────
# Phase 6.5: Out-of-scope refusal tests
# ──────────────────────────────────────────────

def test_get_out_of_scope_refusal_returns_from_pool():
    refusal = get_out_of_scope_refusal()
    assert refusal in OUT_OF_SCOPE_REFUSALS


# ──────────────────────────────────────────────
# Phase 6.5: Off-domain content detection tests
# ──────────────────────────────────────────────

def test_response_contains_off_domain_with_recipe():
    assert response_contains_off_domain_content(
        "Here's a great bread recipe with flour and yeast ingredients"
    ) is True


def test_response_contains_off_domain_with_pwht():
    assert response_contains_off_domain_content(
        "PWHT is a post-weld heat treatment process used in fabrication"
    ) is False


# ──────────────────────────────────────────────
# Phase 6.5 regression: off-domain indicator coverage
# ──────────────────────────────────────────────

def test_message_off_domain_sport():
    from src.config.intent_patterns import message_contains_off_domain_indicator
    assert message_contains_off_domain_indicator("how to play sport") is True


def test_message_off_domain_pasta():
    from src.config.intent_patterns import message_contains_off_domain_indicator
    assert message_contains_off_domain_indicator("how to cook pasta") is True


def test_message_off_domain_pizza():
    from src.config.intent_patterns import message_contains_off_domain_indicator
    assert message_contains_off_domain_indicator("and what about making pizza?") is True


def test_message_off_domain_crepes():
    from src.config.intent_patterns import message_contains_off_domain_indicator
    assert message_contains_off_domain_indicator("crepes recipe please") is True


def test_message_off_domain_does_not_fire_on_rfq():
    from src.config.intent_patterns import message_contains_off_domain_indicator
    assert message_contains_off_domain_indicator("what is the rfq deadline?") is False
