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

    if "expected_min_source_ref_count" in expect:
        assert observed["source_ref_count"] >= int(expect["expected_min_source_ref_count"])

    if "azure_call_occurred" in expect:
        assert observed["azure_call_occurred"] is bool(expect["azure_call_occurred"])

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
        assert observed["stable_prefix"] is not None
        _assert_required_patterns(observed["stable_prefix"], expect["stable_prefix_required"])

    if "stable_prefix_forbidden" in expect:
        assert observed["stable_prefix"] is not None
        _assert_forbidden_patterns(observed["stable_prefix"], expect["stable_prefix_forbidden"])

    if "expected_response_mode_selected" in expect:
        assert (
            observed["response_mode_selected"]
            == expect["expected_response_mode_selected"]
        )

    if "expected_response_mode_effective" in expect:
        assert (
            observed["response_mode_effective"]
            == expect["expected_response_mode_effective"]
        )

    if "expected_evidence_sufficient" in expect:
        assert observed["evidence_sufficient"] is bool(
            expect["expected_evidence_sufficient"]
        )

    if "expected_downgrade_reason" in expect:
        assert observed["downgrade_reason"] == expect["expected_downgrade_reason"]

    if "expected_grounded" in expect:
        assert observed["grounded"] is bool(expect["expected_grounded"])

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
