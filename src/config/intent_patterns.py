"""Phase 6 deterministic intent pattern configuration."""

from __future__ import annotations

import random
import re
from typing import TypedDict

from src.config.capability_status import CAPABILITY_STATUS_ENTRIES


class IntentPattern(TypedDict):
    keywords: list[str]
    session_context: str  # "rfq_bound", "portfolio", "any"
    intent: str  # rfq_specific, domain_knowledge, unsupported, disambiguation, conversational


# ──────────────────────────────────────────────
# Domain vocabulary gate (Pack FD-2)
# ──────────────────────────────────────────────

DOMAIN_VOCAB_TIER1 = {
    # GHI / project-specific
    "rfq", "boq", "mr", "material requisition", "pwht", "rt", "ut", "nde",
    "asme", "api", "aramco", "saes", "saep", "samss", "u-stamp", "u stamp",
    "nb", "national board", "pressure vessel", "heat exchanger",
    "cost-per-ton", "cost per ton", "tonnage", "man-hours", "man hours",
    "p&id", "ga drawing", "data sheet", "hydrostatic test", "pneumatic test",
    "itp", "inspection test plan", "mdr", "manufacturer data report",
    "mtr", "material test report", "rvl", "avl",
    "if-25144", "sa-aypp", "ghi", "albassam",
}

DOMAIN_VOCAB_TIER2 = {
    # Fabrication & manufacturing
    "fabrication", "welding", "wps", "pqr", "weld map", "ndt", "radiography",
    "ultrasonic", "magnetic particle", "dye penetrant", "post-weld heat treatment",
    "stress relief", "hot forming", "cold forming", "rolling", "forging",
    "casting", "machining", "grinding", "surface finish", "dimensional inspection",
    "fit-up", "tack weld", "root pass", "fill pass", "cap pass",
    "back gouging", "preheat", "interpass temperature",
    # Metallurgy & materials
    "carbon steel", "stainless steel", "alloy steel", "duplex", "super duplex",
    "inconel", "monel", "hastelloy", "titanium", "clad", "overlay", "lining",
    "corrosion allowance", "material grade", "material specification",
    "sa-516", "sa-240", "sa-312", "sa-106", "sa-333", "sa-182", "sa-350", "a105",
    "impact test", "charpy", "hardness test", "pmi",
    "positive material identification", "nace", "sour service",
    "hydrogen induced cracking", "hic", "ssc", "stress corrosion cracking",
    # Vessel & exchanger design
    "shell", "head", "nozzle", "flange", "tube sheet", "baffle", "saddle",
    "skirt", "lifting lug", "davit", "manway", "handhole", "reinforcement pad",
    "gasket", "bolt", "stud", "expansion joint", "bellows",
    "impingement plate", "wear plate", "floating head", "fixed tube sheet",
    "u-tube", "kettle reboiler", "condenser", "cooler", "heater", "reactor",
    "column", "tower", "drum", "separator", "accumulator",
    # Piping & valves
    "piping", "valve", "gate valve", "globe valve", "ball valve", "check valve",
    "butterfly valve", "safety valve", "relief valve", "psv",
    "pressure safety valve", "rupture disc", "pipe spool", "pipe support",
    "flange rating", "socket weld", "butt weld", "orifice plate",
    # Codes & standards
    "section viii", "division 1", "division 2", "tema",
    "api 650", "api 620", "api 661", "api 560",
    "astm", "aws", "ped", "dosh", "saso",
    "code compliance", "design code", "construction code",
    "authorized inspector", "third party inspection", "tpi",
    # Procurement & commercial
    "procurement", "estimation", "proposal", "bid", "tender", "quotation",
    "rfp", "purchase order", "letter of intent", "loi", "contract",
    "subcontract", "vendor", "supplier", "manufacturer", "lead time",
    "delivery schedule", "shipping", "packing", "preservation",
    "fob", "cif", "cfr", "dap", "ddp", "incoterms",
    "bill of lading", "packing list", "commercial invoice",
    "performance bond", "advance payment guarantee", "retention",
    "payment milestone", "cash flow", "bank guarantee", "letter of credit",
    "escalation", "variation", "change order", "claim",
    "liquidated damages", "warranty", "defects liability",
    # Project management & EPC
    "epc", "feed", "ifc", "afc", "scope of work", "sow",
    "work breakdown structure", "wbs", "critical path", "gantt", "milestone",
    "s-curve", "earned value", "cost control", "budget", "forecast",
    "risk register", "moc", "management of change",
    "project execution plan", "quality plan", "qa/qc", "hse",
    # Oil & gas / petrochemical
    "upstream", "downstream", "midstream", "refinery", "petrochemical",
    "lng", "ngl", "fpso", "pipeline", "gas plant",
    "desalination", "water treatment", "compressor", "pump", "turbine",
    "boiler", "fired heater", "furnace",
    # Saudi-specific
    "saudi aramco", "sabic", "swcc", "yanbu", "jubail", "ras tanura",
    "abqaiq", "jazan", "neom", "saudi vision 2030", "iktva",
}

# Combined set for fast lookup
DOMAIN_VOCABULARY = DOMAIN_VOCAB_TIER1 | DOMAIN_VOCAB_TIER2


def message_contains_domain_term(message: str) -> bool:
    """Check if user message contains at least one domain vocabulary term.
    Uses word-boundary matching for short terms, substring for multi-word terms.
    """
    text = message.lower()
    for term in DOMAIN_VOCABULARY:
        if " " in term:
            # Multi-word term: substring match
            if term in text:
                return True
        else:
            # Single-word term: word boundary match to avoid false positives
            # e.g., "head" shouldn't match "heading" in casual context
            if len(term) <= 3:
                # Very short terms (rt, ut, nb, mr, etc.): require word boundaries
                if re.search(rf'\b{re.escape(term)}\b', text):
                    return True
            else:
                # Longer single words: substring is safe enough
                if term in text:
                    return True
    return False


# ──────────────────────────────────────────────
# Conversational sub-type patterns (Pack FD-5)
# ──────────────────────────────────────────────

CONVERSATIONAL_SUBTYPES = {
    "greeting": [
        "hello", "hi", "hey", "good morning", "good afternoon",
        "good evening", "greetings", "howdy", "bonjour", "salam",
        "مرحبا", "السلام عليكم",
    ],
    "identity": [
        "who are you", "what are you", "what can you do",
        "what's your role", "what is your role", "introduce yourself",
        "what do you do", "your name", "are you gpt", "what model",
    ],
    "thanks": [
        "thanks", "thank you", "thx", "appreciated", "great job",
        "perfect", "awesome", "well done", "merci", "شكرا",
    ],
    "goodbye": [
        "bye", "goodbye", "see you", "that's all", "done for now",
        "good night", "gotta go", "talk later",
    ],
    "correction": [
        "no i meant", "actually i", "not that", "i was asking about",
        "let me rephrase", "i meant", "what i mean is", "to clarify",
    ],
    "reset": [
        "never mind", "forget it", "start over", "scratch that",
        "ignore that", "disregard",
    ],
    "repeat": [
        "say that again", "repeat that", "can you repeat",
        "i didn't get that", "explain again", "come again",
    ],
    "chitchat": [
        "how are you", "what's up", "how's it going",
        "tell me a joke", "what do you think",
    ],
}


def classify_conversational_subtype(message: str) -> str:
    """Classify a conversational message into a sub-type.
    Returns the sub-type key or 'generic' if no match.
    """
    text = message.lower().strip()
    for subtype, patterns in CONVERSATIONAL_SUBTYPES.items():
        for pattern in patterns:
            if pattern in text:
                return subtype
    return "generic"


# ──────────────────────────────────────────────
# Out-of-scope refusal variants (Pack FD-3)
# ──────────────────────────────────────────────

OUT_OF_SCOPE_REFUSALS = [
    "I'm focused on RFQ lifecycle, industrial estimation, and procurement workflows. "
    "How can I help with your RFQ?",

    "That's outside my scope — I specialize in RFQ management, estimation, "
    "fabrication compliance, and procurement. What would you like to check?",

    "I'm scoped to industrial estimation and RFQ workflows. "
    "I can help with stages, deadlines, BOQ context, compliance, and more — "
    "what do you need?",

    "I work within the RFQ lifecycle — estimation, procurement, fabrication, "
    "and project delivery. Want to check something on your RFQ?",

    "That falls outside my domain. I can help with RFQ status, cost analysis, "
    "MR packages, compliance standards, and related topics. What's on your mind?",
]


def get_out_of_scope_refusal() -> str:
    return random.choice(OUT_OF_SCOPE_REFUSALS)


# ──────────────────────────────────────────────
# Off-domain indicators for guardrail (Pack FD-10)
# ──────────────────────────────────────────────

OFF_DOMAIN_INDICATORS = [
    "recipe", "ingredient", "cooking", "baking", "bread", "cake",
    "travel", "vacation", "hotel", "flight", "tourist",
    "movie", "film", "song", "lyrics", "album", "actor",
    "game", "score", "team", "league", "championship",
    "homework", "essay", "school", "exam", "quiz",
    "diet", "exercise", "workout", "calories", "weight loss",
    "weather forecast", "horoscope", "zodiac",
    "joke", "riddle", "puzzle", "trivia",
]


def response_contains_off_domain_content(response_text: str) -> bool:
    """Check if LLM response contains off-domain content indicators."""
    text = response_text.lower()
    matches = [ind for ind in OFF_DOMAIN_INDICATORS if ind in text]
    return len(matches) >= 2  # Require 2+ indicators to reduce false positives


def message_contains_off_domain_indicator(message_text: str) -> bool:
    """Check whether a user message clearly includes an off-domain topic cue."""
    text = message_text.lower()
    return any(indicator in text for indicator in OFF_DOMAIN_INDICATORS)


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
    # 4) domain_knowledge patterns
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
        "intent": "domain_knowledge",
    },
]


FALLBACK_INTENT: str = "conversational"
