"""Phase 5 prompt assembly with stable-prefix behavioral directives."""

from __future__ import annotations

from src.config.role_profiles import FALLBACK_ROLE, ROLE_PROFILES
from src.models.prompt import PromptEnvelope


CONFIDENCE_PATTERN_MARKER = "Confidence: pattern-based (validated against 1 sample)"


class ContextBuilder:
    """Build the prompt envelope from history, retrieved facts, and Phase 5 signals."""

    system_prompt = (
        "You are RFQ Copilot, a conversational assistant for estimation engineers "
        "working on industrial RFQs. In this phase you may receive retrieved "
        "read-only RFQ facts from manager or intelligence services. Use those "
        "retrieved facts faithfully, do not invent missing RFQ specifics, and say "
        "clearly when information is unavailable. For general questions without "
        "retrieved facts, answer helpfully and honestly."
    )
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

        stage_lines = [f"Stage framing: {stage_fragment}"]
        if stage_name:
            stage_lines.append(f"Current stage label: {stage_name}")

        disambiguation_lines: list[str] = []
        if disambiguation_context is not None:
            disambiguation_lines = [
                "Disambiguation behavior: RFQ resolution mode.",
                (
                    "The user asked a question that references an RFQ, but no RFQ is "
                    "bound to this session."
                ),
                (
                    "Generate a clarification response asking the user to identify which "
                    "RFQ they mean."
                ),
                (
                    "You may ask for an RFQ code (e.g., IF-25144, RFQ-01) or suggest "
                    "the user bind their session."
                ),
                "Do not answer the user's question directly. Ask for clarification only.",
            ]

        prefix_lines = [
            self.system_prompt,
            "",
            f"Role tone directive: {role_profile['tone_directive']}",
            f"Role depth directive: {role_profile['depth_directive']}",
            "",
            *stage_lines,
            "",
            *disambiguation_lines,
            *( [""] if disambiguation_lines else [] ),
            *confidence_directives,
        ]
        return "\n".join(prefix_lines)

    @staticmethod
    def _build_confidence_directives(
        *,
        any_pattern_based_tool_fired: bool,
        grounding_gap: bool,
        capability_status_hit,
    ) -> list[str]:
        if capability_status_hit is not None:
            return [
                "Confidence behavior: capability absence response mode.",
                (
                    "If the user asks for this unsupported capability, respond using this "
                    "template exactly: I don't have grounded facts for "
                    f"{capability_status_hit.capability_name} yet because "
                    f"{capability_status_hit.named_future_condition}."
                ),
                "Optionally add one sentence redirecting to capabilities you can answer now.",
                "Do not invent any capability status beyond the provided condition.",
                "Do not append any confidence marker line for this response mode.",
            ]

        if grounding_gap:
            return [
                "Grounding behavior: grounding gap mode.",
                (
                    "The user asked an RFQ-specific question but no grounded tool evidence "
                    "is available."
                ),
                "Do not generate any RFQ-specific factual claims. Instead, respond honestly:",
                "state that you cannot retrieve the requested information right now,",
                "and suggest what you can help with or ask the user to rephrase.",
                "Do not append any confidence marker line for this response mode.",
            ]

        if any_pattern_based_tool_fired:
            return [
                "Confidence behavior: pattern-based evidence mode.",
                (
                    "When composing the final answer, end with this exact final line: "
                    f"{CONFIDENCE_PATTERN_MARKER}"
                ),
            ]

        return [
            "Confidence behavior: deterministic evidence mode.",
            "Do not append any confidence marker line.",
        ]

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
