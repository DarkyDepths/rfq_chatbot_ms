from src.config.capability_status import CAPABILITY_STATUS_ENTRIES
from src.config.intent_patterns import FALLBACK_INTENT, INTENT_PATTERNS


ALLOWED_INTENTS = {
    "rfq_specific",
    "general_knowledge",
    "unsupported",
    "disambiguation",
    "conversational",
}


def test_fallback_intent_is_conversational():
    assert FALLBACK_INTENT == "conversational"


def test_intent_patterns_use_only_five_intent_taxonomy():
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
