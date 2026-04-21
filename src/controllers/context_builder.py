"""Phase 6 prompt assembly with stable-prefix behavioral directives."""

from __future__ import annotations

import logging

from src.config.prompt_templates import (
    CAPABILITY_ABSENCE_CONFIDENCE_TEMPLATE_LINES,
    CONVERSATIONAL_RULES,
    DETERMINISTIC_CONFIDENCE_LINES,
    DISAMBIGUATION_LINES,
    DOMAIN_CONSTRAINTS_SECTION_LINES,
    DOMAIN_VOCABULARY_SECTION_LINES,
    FORMAT_HINTS,
    GREETING_BEHAVIOR_SECTION_LINES,
    GROUNDING_GAP_CONFIDENCE_LINES,
    GROUNDING_RULES_SECTION_LINES,
    PATTERN_BASED_CONFIDENCE_TEMPLATE_LINES,
    PERSONA_SECTION_LINES,
    RESPONSE_FORMATTING,
    RESPONSE_RULES_SECTION_LINES,
)
from src.config.role_profiles import FALLBACK_ROLE, ROLE_PROFILES
from src.models.prompt import PromptEnvelope


logger = logging.getLogger(__name__)

CONFIDENCE_PATTERN_MARKER = "Confidence: pattern-based (validated against 1 sample)"


# ──────────────────────────────────────────────
# History window by intent (Pack FD-7)
# ──────────────────────────────────────────────
HISTORY_WINDOW = {
    "greeting": 2,
    "identity": 2,
    "thanks": 1,
    "goodbye": 1,
    "domain_knowledge": 3,
    "rfq_specific": None,  # None = full bounded history (existing behavior)
    "unsupported": 2,
    "disambiguation": 3,
    "out_of_scope": 0,  # No history needed for deterministic refusal
}


class ContextBuilder:
    """Build the prompt envelope from history, retrieved facts, and Phase 5/6 signals."""

    history_window_size = 6
    total_budget = 4000

    def build(
        self,
        recent_messages,
        retrieval_context_blocks=None,
        supplemental_context_blocks=None,
        latest_user_turn: str | None = None,
        stage_resolution=None,
        role_resolution=None,
        disambiguation_context: dict | None = None,
        any_pattern_based_tool_fired: bool = False,
        grounding_gap: bool = False,
        capability_status_hit=None,
        turn_guidance_lines: list[str] | None = None,
        greeting_mode: bool = False,
        include_history_in_variable_suffix: bool = True,
        intent: str | None = None,
        conversational_subtype: str | None = None,
    ) -> PromptEnvelope:
        """Return the frozen PromptEnvelope contract for the current turn."""

        # Apply intent-based history truncation
        truncated_messages = self._truncate_history(
            recent_messages, intent=intent, conversational_subtype=conversational_subtype,
        )

        stable_prefix = self._build_stable_prefix(
            stage_resolution=stage_resolution,
            role_resolution=role_resolution,
            disambiguation_context=disambiguation_context,
            any_pattern_based_tool_fired=any_pattern_based_tool_fired,
            grounding_gap=grounding_gap,
            capability_status_hit=capability_status_hit,
            turn_guidance_lines=turn_guidance_lines,
            greeting_mode=greeting_mode,
            intent=intent,
            conversational_subtype=conversational_subtype,
        )

        variable_suffix = self._build_variable_suffix(
            recent_messages=truncated_messages,
            retrieval_context_blocks=retrieval_context_blocks,
            supplemental_context_blocks=supplemental_context_blocks,
            latest_user_turn=latest_user_turn,
            disambiguation_context=disambiguation_context,
            capability_status_hit=capability_status_hit,
            include_history=include_history_in_variable_suffix,
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
        turn_guidance_lines: list[str] | None,
        greeting_mode: bool,
        intent: str | None = None,
        conversational_subtype: str | None = None,
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

        # ── Intent-aware prompt composition (FD-7 matrix) ──
        # If intent is provided, use the matrix. Otherwise, fall back to
        # legacy behavior (include everything) for backward compatibility.
        if intent is not None:
            prefix_sections = self._build_intent_aware_sections(
                intent=intent,
                conversational_subtype=conversational_subtype,
                role_lines=role_lines,
                stage_lines=stage_lines,
                confidence_directives=confidence_directives,
                greeting_mode=greeting_mode,
                turn_guidance_lines=turn_guidance_lines,
            )
        else:
            # Legacy path: include ALL sections (backward compatibility)
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
                self._render_xml_section(
                    "greeting_behavior",
                    list(GREETING_BEHAVIOR_SECTION_LINES),
                ),
                self._render_xml_section("role_framing", role_lines),
                self._render_xml_section("stage_framing", stage_lines),
                self._render_xml_section("confidence_behavior", confidence_directives),
                self._render_xml_section(
                    "grounding_rules",
                    list(GROUNDING_RULES_SECTION_LINES),
                ),
            ]
            if greeting_mode:
                prefix_sections.append(self._render_xml_section("turn_mode", ["greeting"]))
            if turn_guidance_lines:
                prefix_sections.append(
                    self._render_xml_section("turn_guidance", list(turn_guidance_lines))
                )

        return "\n\n".join(prefix_sections)

    def _build_intent_aware_sections(
        self,
        *,
        intent: str,
        conversational_subtype: str | None,
        role_lines: list[str],
        stage_lines: list[str],
        confidence_directives: list[str],
        greeting_mode: bool,
        turn_guidance_lines: list[str] | None,
    ) -> list[str]:
        """Build prefix sections based on the FD-7 intent inclusion matrix."""
        sections: list[str] = []

        # Always include persona
        sections.append(self._render_xml_section("persona", list(PERSONA_SECTION_LINES)))

        # Domain constraints: for greeting, domain_knowledge, rfq_specific, unsupported
        if intent in ("domain_knowledge", "rfq_specific", "unsupported"):
            sections.append(
                self._render_xml_section("domain_constraints", list(DOMAIN_CONSTRAINTS_SECTION_LINES))
            )
        elif intent == "conversational" and conversational_subtype in ("greeting", "chitchat", None):
            sections.append(
                self._render_xml_section("domain_constraints", list(DOMAIN_CONSTRAINTS_SECTION_LINES))
            )

        # Domain vocabulary: include for domain_knowledge and rfq_specific
        if intent in ("domain_knowledge", "rfq_specific"):
            sections.append(
                self._render_xml_section("domain_vocabulary", list(DOMAIN_VOCABULARY_SECTION_LINES))
            )

        # Response rules: FULL for domain_knowledge and rfq_specific, LITE for others
        if intent in ("domain_knowledge", "rfq_specific"):
            sections.append(
                self._render_xml_section("response_rules", list(RESPONSE_RULES_SECTION_LINES))
            )
        else:
            sections.append(self._lite_response_rules_section())

        # Greeting behavior: ONLY for greeting subtype
        if intent == "conversational" and conversational_subtype == "greeting":
            sections.append(
                self._render_xml_section("greeting_behavior", list(GREETING_BEHAVIOR_SECTION_LINES))
            )

        # Conversational rules: for conversational intents EXCEPT greeting (which has its own)
        if intent == "conversational" and conversational_subtype != "greeting":
            sections.append(CONVERSATIONAL_RULES)

        # Response formatting: for domain_knowledge and rfq_specific only
        if intent in ("domain_knowledge", "rfq_specific"):
            sections.append(RESPONSE_FORMATTING)

        # Role framing: ONLY for rfq_specific
        if intent == "rfq_specific":
            sections.append(self._render_xml_section("role_framing", role_lines))

        # Stage framing: ONLY for rfq_specific
        if intent == "rfq_specific":
            sections.append(self._render_xml_section("stage_framing", stage_lines))

        # Disambiguation mode relies on explicit disambiguation directives in the stable prefix.
        if intent == "disambiguation":
            sections.append(self._render_xml_section("stage_framing", stage_lines))

        # Confidence behavior: rfq_specific plus unsupported capability-status mode.
        if intent in ("rfq_specific", "unsupported"):
            sections.append(self._render_xml_section("confidence_behavior", confidence_directives))

        # Grounding rules: ONLY for rfq_specific
        if intent == "rfq_specific":
            sections.append(
                self._render_xml_section("grounding_rules", list(GROUNDING_RULES_SECTION_LINES))
            )

        # Turn mode
        if greeting_mode:
            sections.append(self._render_xml_section("turn_mode", ["greeting"]))

        # Turn guidance with format hint
        if turn_guidance_lines:
            guidance = list(turn_guidance_lines)
            # Add format hint
            format_key = conversational_subtype if intent == "conversational" else intent
            format_hint = FORMAT_HINTS.get(format_key, "plain_prose_short")
            guidance.append(f"<format_hint>{format_hint}</format_hint>")
            sections.append(self._render_xml_section("turn_guidance", guidance))

        return sections

    @staticmethod
    def _lite_response_rules_section() -> str:
        """Return a stripped-down response rules section — only the 3 core rules."""
        return """<response_rules>
- Lead with the answer, not the process.
- Be concise — match response depth to what the user asked.
- Do not proactively expand beyond the question.
</response_rules>"""

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
        supplemental_context_blocks,
        latest_user_turn: str | None,
        disambiguation_context: dict | None,
        capability_status_hit,
        include_history: bool,
    ) -> str:
        transcript_lines: list[str] = []

        if include_history:
            transcript_lines.append("Conversation history:")
            for message in recent_messages:
                transcript_lines.append(f"{message.role}: {message.content}")

        if supplemental_context_blocks:
            if transcript_lines:
                transcript_lines.append("")
            transcript_lines.append("Session context:")
            transcript_lines.extend(supplemental_context_blocks)

        # Capability-status and disambiguation modes are no-retrieval paths.
        if (
            retrieval_context_blocks
            and capability_status_hit is None
            and disambiguation_context is None
        ):
            if transcript_lines:
                transcript_lines.append("")
            transcript_lines.append("Retrieved facts:")
            transcript_lines.extend(retrieval_context_blocks)

        if latest_user_turn:
            if transcript_lines and not include_history:
                transcript_lines.append("")
            if include_history:
                transcript_lines.append(f"user: {latest_user_turn}")
            else:
                transcript_lines.append("Latest user turn:")
                transcript_lines.append(latest_user_turn)

        if include_history:
            transcript_lines.append("assistant:")
        return "\n".join(transcript_lines)

    @staticmethod
    def _truncate_history(recent_messages, *, intent: str | None, conversational_subtype: str | None):
        """Apply intent-based history truncation."""
        if intent is None:
            return recent_messages

        history_key = conversational_subtype if intent == "conversational" else intent
        max_turns = HISTORY_WINDOW.get(history_key, 3)
        if max_turns is not None and len(recent_messages) > max_turns:
            return recent_messages[-max_turns:]
        return recent_messages
