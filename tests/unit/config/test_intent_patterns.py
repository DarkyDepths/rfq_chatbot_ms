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
