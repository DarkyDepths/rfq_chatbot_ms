from src.controllers.output_guardrail import OutputGuardrail
from src.controllers.tool_controller import CapabilityStatusHit


def test_rfq_specific_with_source_refs_passes():
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="rfq_specific",
        assistant_text="answer",
        source_refs=[{"system": "rfq_manager_ms"}],
        grounding_gap_injected=False,
        capability_status_hit=None,
    )

    assert result == "pass"


def test_rfq_specific_without_source_refs_and_no_grounding_gap_is_violation():
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="rfq_specific",
        assistant_text="answer",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=None,
    )

    assert result == "grounding_violation"


def test_rfq_specific_without_source_refs_with_grounding_gap_passes():
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="rfq_specific",
        assistant_text="answer",
        source_refs=[],
        grounding_gap_injected=True,
        capability_status_hit=None,
    )

    assert result == "pass"


def test_disambiguation_with_question_mark_passes():
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="disambiguation",
        assistant_text="Which RFQ are you referring to?",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=None,
    )

    assert result == "pass"


def test_disambiguation_with_which_passes():
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="disambiguation",
        assistant_text="which rfq are you referring to",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=None,
    )

    assert result == "pass"


def test_disambiguation_without_shape_signals_is_violation():
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="disambiguation",
        assistant_text="Please clarify the project details",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=None,
    )

    assert result == "disambiguation_shape_violation"


def test_unsupported_with_capability_name_present_passes():
    guardrail = OutputGuardrail()
    hit = CapabilityStatusHit(
        matched_keyword="briefing",
        capability_name="RFQ intelligence briefing retrieval",
        named_future_condition="available in a later phase",
    )

    result = guardrail.evaluate(
        intent="unsupported",
        assistant_text="I don't have grounded facts for RFQ intelligence briefing retrieval yet.",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=hit,
    )

    assert result == "pass"


def test_unsupported_with_capability_name_missing_is_violation():
    guardrail = OutputGuardrail()
    hit = CapabilityStatusHit(
        matched_keyword="briefing",
        capability_name="RFQ intelligence briefing retrieval",
        named_future_condition="available in a later phase",
    )

    result = guardrail.evaluate(
        intent="unsupported",
        assistant_text="This capability is not available yet.",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=hit,
    )

    assert result == "unsupported_routing_violation"


def test_general_knowledge_always_passes():
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="general_knowledge",
        assistant_text="PWHT is a post-weld heat treatment process.",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=None,
    )

    assert result == "pass"


def test_conversational_always_passes():
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="conversational",
        assistant_text="Hello!",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=None,
    )

    assert result == "pass"
