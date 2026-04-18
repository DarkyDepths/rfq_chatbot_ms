"""Phase 6 deterministic intent pattern configuration."""

from __future__ import annotations

from typing import TypedDict

from src.config.capability_status import CAPABILITY_STATUS_ENTRIES


class IntentPattern(TypedDict):
    keywords: list[str]
    session_context: str  # "rfq_bound", "portfolio", "any"
    intent: str  # rfq_specific, general_knowledge, unsupported, disambiguation, conversational


INTENT_PATTERNS: list[IntentPattern] = [
    # 1) unsupported patterns first (derived from Phase 5 capability-status keys)
    *[
        {
            "keywords": [keyword],
            "session_context": "any",
            "intent": "unsupported",
        }
        for keyword in CAPABILITY_STATUS_ENTRIES.keys()
    ],
    # 2) disambiguation patterns (portfolio only)
    {
        "keywords": [
            "this rfq",
            "that rfq",
            "the rfq",
            "this project",
            "that project",
            "the project",
            "status of this",
            "status of that",
            "last one",
        ],
        "session_context": "portfolio",
        "intent": "disambiguation",
    },
    # 3) rfq_specific patterns
    {
        "keywords": [
            "rfq",
            "quote",
            "proposal",
            "if-",
            "rfq-",
            "uuid",
        ],
        "session_context": "any",
        "intent": "rfq_specific",
    },
    {
        "keywords": [
            "deadline",
            "owner",
            "status",
            "stage",
            "cost",
            "client",
            "priority",
            "timeline",
        ],
        "session_context": "rfq_bound",
        "intent": "rfq_specific",
    },
    # 4) general_knowledge patterns
    {
        "keywords": [
            "what is",
            "how does",
            "explain",
            "typical",
            "in general",
            "standard",
        ],
        "session_context": "any",
        "intent": "general_knowledge",
    },
]


FALLBACK_INTENT: str = "conversational"
