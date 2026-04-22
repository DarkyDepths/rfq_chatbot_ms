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


# ──────────────────────────────────────────────
# Phase 6.5: Domain knowledge guardrail tests
# ──────────────────────────────────────────────

def test_domain_knowledge_with_recipe_is_domain_leak():
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="domain_knowledge",
        assistant_text="Here's a great bread recipe with flour and yeast ingredients...",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=None,
    )

    assert result == "domain_leak"


def test_domain_knowledge_about_pwht_passes():
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="domain_knowledge",
        assistant_text="PWHT is a post-weld heat treatment process used in fabrication...",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=None,
    )

    assert result == "pass"


# ──────────────────────────────────────────────
# Phase 6.5: Conversational guardrail tests
# ──────────────────────────────────────────────

def test_verbose_greeting_warning():
    guardrail = OutputGuardrail()
    long_greeting = "x" * 600

    result = guardrail.evaluate(
        intent="conversational",
        assistant_text=long_greeting,
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=None,
        conversational_subtype="greeting",
    )

    assert result == "verbose_greeting_warning"


def test_short_greeting_passes():
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="conversational",
        assistant_text="Hi! Ready to help with your RFQ.",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=None,
        conversational_subtype="greeting",
    )

    assert result == "pass"


def test_conversational_thanks_short_passes():
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="conversational",
        assistant_text="You're welcome!",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=None,
        conversational_subtype="thanks",
    )

    assert result == "pass"


def test_out_of_scope_always_passes():
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="out_of_scope",
        assistant_text="anything",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=None,
    )

    assert result == "pass"


# ──────────────────────────────────────────────
# Phase 6.5 regression: conversational off-domain leak detection
# ──────────────────────────────────────────────

def test_conversational_with_recipe_content_is_domain_leak():
    """If LLM generates a recipe in conversational mode, guardrail must catch it."""
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="conversational",
        assistant_text="Here's a great pasta recipe with flour and olive oil ingredients...",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=None,
        conversational_subtype="generic",
    )

    assert result == "domain_leak"


def test_conversational_with_sport_advice_is_domain_leak():
    """If LLM generates sports advice in conversational mode, guardrail must catch it."""
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="conversational",
        assistant_text="To play football, you need a ball and exercise regularly at the gym.",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=None,
        conversational_subtype="generic",
    )

    assert result == "domain_leak"


def test_conversational_greeting_without_off_domain_passes():
    """Normal greeting responses must not trigger domain leak."""
    guardrail = OutputGuardrail()

    result = guardrail.evaluate(
        intent="conversational",
        assistant_text="Hi! I'm ready to help with your RFQ. What would you like to check?",
        source_refs=[],
        grounding_gap_injected=False,
        capability_status_hit=None,
        conversational_subtype="greeting",
    )

    assert result == "pass"
