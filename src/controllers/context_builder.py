"""Phase 6 prompt assembly with stable-prefix behavioral directives."""

from __future__ import annotations

from src.config.prompt_templates import (
    CAPABILITY_ABSENCE_CONFIDENCE_TEMPLATE_LINES,
    DETERMINISTIC_CONFIDENCE_LINES,
    DISAMBIGUATION_LINES,
    DOMAIN_CONSTRAINTS_SECTION_LINES,
    DOMAIN_VOCABULARY_SECTION_LINES,
    GROUNDING_GAP_CONFIDENCE_LINES,
    GROUNDING_RULES_SECTION_LINES,
    PATTERN_BASED_CONFIDENCE_TEMPLATE_LINES,
    PERSONA_SECTION_LINES,
    RESPONSE_RULES_SECTION_LINES,
)
from src.config.role_profiles import FALLBACK_ROLE, ROLE_PROFILES
from src.models.prompt import PromptEnvelope


CONFIDENCE_PATTERN_MARKER = "Confidence: pattern-based (validated against 1 sample)"


class ContextBuilder:
    """Build the prompt envelope from history, retrieved facts, and Phase 5/6 signals."""

    history_window_size = 6
    total_budget = 4000

    def build(
        self,
        recent_messages,
        retrieval_context_blocks=None,
        latest_user_turn: str | None = None,
        stage_resolution=None,
        role_resolution=None,
        disambiguation_context: dict | None = None,
        any_pattern_based_tool_fired: bool = False,
        grounding_gap: bool = False,
        capability_status_hit=None,
    ) -> PromptEnvelope:
        """Return the frozen PromptEnvelope contract for the current turn."""

        stable_prefix = self._build_stable_prefix(
            stage_resolution=stage_resolution,
            role_resolution=role_resolution,
            disambiguation_context=disambiguation_context,
            any_pattern_based_tool_fired=any_pattern_based_tool_fired,
            grounding_gap=grounding_gap,
            capability_status_hit=capability_status_hit,
        )

        variable_suffix = self._build_variable_suffix(
            recent_messages=recent_messages,
            retrieval_context_blocks=retrieval_context_blocks,
            latest_user_turn=latest_user_turn,
            disambiguation_context=disambiguation_context,
            capability_status_hit=capability_status_hit,
        )

        return PromptEnvelope(
            stable_prefix=stable_prefix,
            variable_suffix=variable_suffix,
            total_budget=self.total_budget,
        )

    def _build_stable_prefix(
        self,
        *,
        stage_resolution,
        role_resolution,
        disambiguation_context: dict | None,
        any_pattern_based_tool_fired: bool,
        grounding_gap: bool,
        capability_status_hit,
    ) -> str:
        role_profile = ROLE_PROFILES[FALLBACK_ROLE]
        if role_resolution is not None and getattr(role_resolution, "profile", None):
            role_profile = role_resolution.profile
        if disambiguation_context is not None and disambiguation_context.get("role_profile"):
            role_profile = disambiguation_context["role_profile"]

        stage_fragment = "Use neutral stage framing when exact stage context is unavailable."
        stage_name = None
        if stage_resolution is not None:
            profile = getattr(stage_resolution, "profile", None)
            if profile:
                stage_fragment = profile.get("prompt_frame_fragment", stage_fragment)
            rfq_detail = getattr(stage_resolution, "rfq_detail", None)
            if rfq_detail is not None:
                stage_name = getattr(rfq_detail, "current_stage_name", None)

        confidence_directives = self._build_confidence_directives(
            any_pattern_based_tool_fired=any_pattern_based_tool_fired,
            grounding_gap=grounding_gap,
            capability_status_hit=capability_status_hit,
        )

        role_lines = [
            f"Role tone directive: {role_profile['tone_directive']}",
            f"Role depth directive: {role_profile['depth_directive']}",
        ]

        stage_lines = [f"Stage framing: {stage_fragment}"]
        if stage_name:
            stage_lines.append(f"Current stage label: {stage_name}")

        if disambiguation_context is not None:
            stage_lines.extend(DISAMBIGUATION_LINES)

        prefix_sections = [
            self._render_xml_section("persona", list(PERSONA_SECTION_LINES)),
            self._render_xml_section(
                "domain_constraints",
                list(DOMAIN_CONSTRAINTS_SECTION_LINES),
            ),
            self._render_xml_section(
                "domain_vocabulary",
                list(DOMAIN_VOCABULARY_SECTION_LINES),
            ),
            self._render_xml_section(
                "response_rules",
                list(RESPONSE_RULES_SECTION_LINES),
            ),
            self._render_xml_section("role_framing", role_lines),
            self._render_xml_section("stage_framing", stage_lines),
            self._render_xml_section("confidence_behavior", confidence_directives),
            self._render_xml_section(
                "grounding_rules",
                list(GROUNDING_RULES_SECTION_LINES),
            ),
        ]
        return "\n\n".join(prefix_sections)

    @staticmethod
    def _render_xml_section(tag: str, lines: list[str]) -> str:
        section_lines = [f"<{tag}>", *lines, f"</{tag}>"]
        return "\n".join(section_lines)

    @staticmethod
    def _build_confidence_directives(
        *,
        any_pattern_based_tool_fired: bool,
        grounding_gap: bool,
        capability_status_hit,
    ) -> list[str]:
        if capability_status_hit is not None:
            return [
                line.format(
                    capability_name=capability_status_hit.capability_name,
                    named_future_condition=capability_status_hit.named_future_condition,
                )
                for line in CAPABILITY_ABSENCE_CONFIDENCE_TEMPLATE_LINES
            ]

        if grounding_gap:
            return list(GROUNDING_GAP_CONFIDENCE_LINES)

        if any_pattern_based_tool_fired:
            return [
                line.format(confidence_pattern_marker=CONFIDENCE_PATTERN_MARKER)
                for line in PATTERN_BASED_CONFIDENCE_TEMPLATE_LINES
            ]

        return list(DETERMINISTIC_CONFIDENCE_LINES)

    @staticmethod
    def _build_variable_suffix(
        *,
        recent_messages,
        retrieval_context_blocks,
        latest_user_turn: str | None,
        disambiguation_context: dict | None,
        capability_status_hit,
    ) -> str:
        transcript_lines = ["Conversation history:"]
        for message in recent_messages:
            transcript_lines.append(f"{message.role}: {message.content}")

        # Capability-status and disambiguation modes are no-retrieval paths.
        if (
            retrieval_context_blocks
            and capability_status_hit is None
            and disambiguation_context is None
        ):
            transcript_lines.append("")
            transcript_lines.append("Retrieved facts:")
            transcript_lines.extend(retrieval_context_blocks)

        if latest_user_turn:
            transcript_lines.append(f"user: {latest_user_turn}")

        transcript_lines.append("assistant:")
        return "\n".join(transcript_lines)
