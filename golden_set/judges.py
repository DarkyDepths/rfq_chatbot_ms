"""Structural assertion helpers for golden_set case evaluation."""

from __future__ import annotations

import re

from src.controllers.context_builder import CONFIDENCE_PATTERN_MARKER


def assert_turn_expectations(expect: dict, observed: dict) -> None:
    """Assert one observed turn against structural expectations."""

    if "intent" in expect:
        assert observed["intent"] == expect["intent"]

    if "route" in expect:
        assert observed["route"] == expect["route"]

    if "tools_include" in expect:
        expected_tools = set(expect["tools_include"])
        assert expected_tools.issubset(set(observed["tools"]))

    if "tools_exclude" in expect:
        excluded_tools = set(expect["tools_exclude"])
        assert excluded_tools.isdisjoint(set(observed["tools"]))

    if "source_refs_present" in expect:
        assert observed["source_refs_present"] is bool(expect["source_refs_present"])

    if "required_patterns" in expect:
        _assert_required_patterns(observed["content"], expect["required_patterns"])

    if "forbidden_patterns" in expect:
        _assert_forbidden_patterns(observed["content"], expect["forbidden_patterns"])

    if "confidence_marker" in expect:
        _assert_confidence_marker(
            observed["content"],
            expected_mode=expect["confidence_marker"],
        )

    if "stable_prefix_required" in expect:
        _assert_required_patterns(observed["stable_prefix"], expect["stable_prefix_required"])

    if "stable_prefix_forbidden" in expect:
        _assert_forbidden_patterns(observed["stable_prefix"], expect["stable_prefix_forbidden"])

    if "disambiguation_resolved" in expect:
        _assert_disambiguation_flag(
            observed.get("disambiguation_resolved"),
            bool(expect["disambiguation_resolved"]),
        )

    if "disambiguation_abandoned" in expect:
        _assert_disambiguation_flag(
            observed.get("disambiguation_abandoned"),
            bool(expect["disambiguation_abandoned"]),
        )


def _assert_required_patterns(content: str, patterns: list[str]) -> None:
    for pattern in patterns:
        assert re.search(pattern, content, flags=re.IGNORECASE), (
            f"required pattern not found: {pattern}"
        )


def _assert_forbidden_patterns(content: str, patterns: list[str]) -> None:
    for pattern in patterns:
        assert not re.search(pattern, content, flags=re.IGNORECASE), (
            f"forbidden pattern found: {pattern}"
        )


def _assert_confidence_marker(content: str, *, expected_mode: str) -> None:
    marker_present = CONFIDENCE_PATTERN_MARKER in content

    if expected_mode == "present":
        assert marker_present
        return

    if expected_mode == "absent":
        assert not marker_present
        return

    if expected_mode == "any":
        return

    raise AssertionError(f"Unsupported confidence_marker expectation: {expected_mode}")


def _assert_disambiguation_flag(observed_value, expected_value: bool) -> None:
    if expected_value:
        assert observed_value is True
    else:
        assert observed_value in (None, False)
