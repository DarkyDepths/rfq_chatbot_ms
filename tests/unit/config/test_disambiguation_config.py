import re

from src.config.disambiguation_config import (
    DISAMBIGUATION_DETECTION_PATTERNS,
    MAX_RESOLUTION_WORD_COUNT,
    RFQ_REFERENCE_PATTERNS,
)


def test_disambiguation_detection_patterns_is_non_empty():
    assert DISAMBIGUATION_DETECTION_PATTERNS


def test_max_resolution_word_count_is_positive():
    assert MAX_RESOLUTION_WORD_COUNT > 0


def test_rfq_reference_patterns_is_non_empty():
    assert RFQ_REFERENCE_PATTERNS


def test_rfq_reference_patterns_are_valid_regex():
    for pattern in RFQ_REFERENCE_PATTERNS:
        re.compile(pattern)
