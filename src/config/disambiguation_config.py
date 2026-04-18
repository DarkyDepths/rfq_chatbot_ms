"""Phase 6 disambiguation detection and resolution configuration."""

from __future__ import annotations


DISAMBIGUATION_DETECTION_PATTERNS: list[str] = [
    "which rfq",
    "which project",
    "are you referring to",
]

MAX_RESOLUTION_WORD_COUNT: int = 10

RFQ_REFERENCE_PATTERNS: list[str] = [
    r"IF-\d+",
    r"RFQ-\d+",
    # UUID pattern for downstream RFQ ids
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
]
