from types import SimpleNamespace
import uuid

from src.config.role_profiles import ROLE_PROFILES
from src.config.stage_profiles import DEFAULT_STAGE_PROFILE
from src.controllers.context_builder import CONFIDENCE_PATTERN_MARKER, ContextBuilder
from src.controllers.role_controller import RoleResolution
from src.controllers.stage_controller import StageResolution
from src.controllers.tool_controller import CapabilityStatusHit
from src.models.prompt import PromptEnvelope


def _role_resolution(role: str) -> RoleResolution:
    return RoleResolution(
        role=role,
        profile=ROLE_PROFILES[role],
        fallback_used=False,
        original_role=role,
    )


def _stage_resolution(fragment: str, stage_name: str | None = None) -> StageResolution:
    profile = {
        "prompt_frame_fragment": fragment,
        "tool_allow_list": DEFAULT_STAGE_PROFILE["tool_allow_list"],
    }
    rfq_detail = None
    if stage_name is not None:
        rfq_detail = SimpleNamespace(current_stage_name=stage_name)
    return StageResolution(profile=profile, rfq_detail=rfq_detail, stage_id=uuid.uuid4())


def test_context_builder_returns_prompt_envelope_with_frozen_public_fields():
    builder = ContextBuilder()

    prompt = builder.build(
        [SimpleNamespace(role="user", content="Hello")],
        latest_user_turn="Need help",
    )

    assert isinstance(prompt, PromptEnvelope)
    assert list(prompt.model_dump().keys()) == [
        "stable_prefix",
        "variable_suffix",
        "total_budget",
    ]
    for tag in [
        "persona",
        "domain_constraints",
        "domain_vocabulary",
        "response_rules",
        "role_framing",
        "stage_framing",
        "confidence_behavior",
        "grounding_rules",
    ]:
        assert f"<{tag}>" in prompt.stable_prefix
        assert f"</{tag}>" in prompt.stable_prefix


def test_stable_prefix_includes_phase7_domain_vocabulary_and_response_rules():
    builder = ContextBuilder()

    prompt = builder.build(
        [SimpleNamespace(role="user", content="hello")],
        latest_user_turn="What is PWHT?",
    )

    assert "MR package" in prompt.stable_prefix
    assert "BOQ" in prompt.stable_prefix
    assert "PWHT" in prompt.stable_prefix
    assert "RT" in prompt.stable_prefix
    assert "U-Stamp / NB registration" in prompt.stable_prefix
    assert "SAMSS / SAES / SAEP" in prompt.stable_prefix
    assert "cost-per-ton" in prompt.stable_prefix
    assert "Lead with the direct answer" in prompt.stable_prefix
    assert "Use markdown formatting when useful" in prompt.stable_prefix
    assert "Keep responses concise by default" in prompt.stable_prefix
    assert "source system and artifact" in prompt.stable_prefix
    assert "Avoid fabrication when evidence is missing" in prompt.stable_prefix


def test_stable_prefix_changes_with_role_profile_directives():
    builder = ContextBuilder()

    executive_prompt = builder.build(
        [SimpleNamespace(role="user", content="Status?")],
        role_resolution=_role_resolution("executive"),
    )
    lead_prompt = builder.build(
        [SimpleNamespace(role="user", content="Status?")],
        role_resolution=_role_resolution("estimation_dept_lead"),
    )

    assert executive_prompt.stable_prefix != lead_prompt.stable_prefix
    assert ROLE_PROFILES["executive"]["tone_directive"] in executive_prompt.stable_prefix
    assert (
        ROLE_PROFILES["estimation_dept_lead"]["tone_directive"]
        in lead_prompt.stable_prefix
    )


def test_stable_prefix_changes_with_stage_profile_fragment():
    builder = ContextBuilder()

    stage_a = builder.build(
        [SimpleNamespace(role="user", content="Status?")],
        stage_resolution=_stage_resolution("Stage A framing", stage_name="Review"),
    )
    stage_b = builder.build(
        [SimpleNamespace(role="user", content="Status?")],
        stage_resolution=_stage_resolution("Stage B framing", stage_name="Award"),
    )

    assert stage_a.stable_prefix != stage_b.stable_prefix
    assert "Stage framing: Stage A framing" in stage_a.stable_prefix
    assert "Current stage label: Review" in stage_a.stable_prefix
    assert "Stage framing: Stage B framing" in stage_b.stable_prefix
    assert "Current stage label: Award" in stage_b.stable_prefix


def test_stable_prefix_includes_literal_pattern_based_marker_directive_when_enabled():
    builder = ContextBuilder()

    prompt = builder.build(
        [SimpleNamespace(role="user", content="Need snapshot")],
        any_pattern_based_tool_fired=True,
    )

    assert CONFIDENCE_PATTERN_MARKER in prompt.stable_prefix


def test_stable_prefix_omits_literal_pattern_marker_when_not_enabled():
    builder = ContextBuilder()

    prompt = builder.build(
        [SimpleNamespace(role="user", content="Need profile")],
        any_pattern_based_tool_fired=False,
    )

    assert CONFIDENCE_PATTERN_MARKER not in prompt.stable_prefix


def test_capability_status_mode_injects_absence_directive_and_suppresses_retrieval_blocks():
    builder = ContextBuilder()
    hit = CapabilityStatusHit(
        matched_keyword="briefing",
        capability_name="RFQ intelligence briefing retrieval",
        named_future_condition="available after briefing rollout is enabled in a later phase",
    )

    prompt = builder.build(
        [SimpleNamespace(role="assistant", content="Earlier answer")],
        retrieval_context_blocks=["Tool: get_rfq_profile"],
        latest_user_turn="Show briefing",
        capability_status_hit=hit,
    )

    assert "I don't have grounded facts for" in prompt.stable_prefix
    assert hit.capability_name in prompt.stable_prefix
    assert hit.named_future_condition in prompt.stable_prefix
    assert "Retrieved facts:" not in prompt.variable_suffix


def test_variable_suffix_keeps_phase4_composition_order_with_new_signals_absent():
    builder = ContextBuilder()

    prompt = builder.build(
        [
            SimpleNamespace(role="user", content="Hello"),
            SimpleNamespace(role="assistant", content="Hi there"),
        ],
        retrieval_context_blocks=["Tool: get_rfq_profile", "Value: {\"owner\": \"Sarah\"}"],
        latest_user_turn="What is the deadline?",
    )

    lines = prompt.variable_suffix.splitlines()
    assert lines[0] == "Conversation history:"
    assert lines[1] == "user: Hello"
    assert lines[2] == "assistant: Hi there"
    assert lines[3] == ""
    assert lines[4] == "Retrieved facts:"
    assert lines[5] == "Tool: get_rfq_profile"
    assert lines[6] == "Value: {\"owner\": \"Sarah\"}"
    assert lines[7] == "user: What is the deadline?"
    assert lines[8] == "assistant:"


def test_grounding_gap_injects_absence_directive():
    builder = ContextBuilder()

    prompt = builder.build(
        [SimpleNamespace(role="user", content="Need deadline")],
        latest_user_turn="What's the deadline?",
        grounding_gap=True,
    )

    assert "Grounding behavior: grounding gap mode." in prompt.stable_prefix
    assert "state that you cannot retrieve the requested information right now" in prompt.stable_prefix


def test_grounding_gap_suppresses_pattern_based_marker_directive():
    builder = ContextBuilder()

    prompt = builder.build(
        [SimpleNamespace(role="user", content="Need deadline")],
        latest_user_turn="What's the deadline?",
        grounding_gap=True,
        any_pattern_based_tool_fired=True,
    )

    assert CONFIDENCE_PATTERN_MARKER not in prompt.stable_prefix


def test_pattern_based_marker_behavior_unchanged_when_grounding_gap_is_false():
    builder = ContextBuilder()

    prompt = builder.build(
        [SimpleNamespace(role="user", content="Need snapshot")],
        latest_user_turn="Give me a snapshot",
        grounding_gap=False,
        any_pattern_based_tool_fired=True,
    )

    assert "Confidence behavior: pattern-based evidence mode." in prompt.stable_prefix
    assert CONFIDENCE_PATTERN_MARKER in prompt.stable_prefix


def test_capability_status_precedence_overrides_grounding_gap_mode():
    builder = ContextBuilder()
    hit = CapabilityStatusHit(
        matched_keyword="briefing",
        capability_name="RFQ intelligence briefing retrieval",
        named_future_condition="available after briefing rollout is enabled in a later phase",
    )

    prompt = builder.build(
        [SimpleNamespace(role="assistant", content="Earlier answer")],
        latest_user_turn="Show briefing",
        grounding_gap=True,
        capability_status_hit=hit,
    )

    assert "Confidence behavior: capability absence response mode." in prompt.stable_prefix
    assert "Grounding behavior: grounding gap mode." not in prompt.stable_prefix


def test_disambiguation_context_injects_rfq_resolution_directive():
    builder = ContextBuilder()

    prompt = builder.build(
        [SimpleNamespace(role="user", content="What's the status?")],
        latest_user_turn="What's the status of this RFQ?",
        disambiguation_context={
            "disambiguation_mode": True,
            "user_question": "What's the status of this RFQ?",
            "role_profile": ROLE_PROFILES["executive"],
        },
    )

    assert "Disambiguation behavior: RFQ resolution mode." in prompt.stable_prefix
    assert "Do not answer the user's question directly. Ask for clarification only." in prompt.stable_prefix
    assert ROLE_PROFILES["executive"]["tone_directive"] in prompt.stable_prefix


def test_disambiguation_context_suppresses_retrieval_blocks_in_variable_suffix():
    builder = ContextBuilder()

    prompt = builder.build(
        [SimpleNamespace(role="assistant", content="Earlier answer")],
        retrieval_context_blocks=["Tool: get_rfq_profile", "Value: {\"owner\": \"Sarah\"}"],
        latest_user_turn="What's the status of this RFQ?",
        disambiguation_context={
            "disambiguation_mode": True,
            "user_question": "What's the status of this RFQ?",
            "role_profile": ROLE_PROFILES["estimation_dept_lead"],
        },
    )

    assert "Retrieved facts:" not in prompt.variable_suffix


def test_without_disambiguation_context_behavior_is_unchanged():
    builder = ContextBuilder()

    prompt = builder.build(
        [SimpleNamespace(role="assistant", content="Earlier answer")],
        retrieval_context_blocks=["Tool: get_rfq_profile"],
        latest_user_turn="What is the deadline?",
    )

    assert "Disambiguation behavior: RFQ resolution mode." not in prompt.stable_prefix
    assert "Retrieved facts:" in prompt.variable_suffix
