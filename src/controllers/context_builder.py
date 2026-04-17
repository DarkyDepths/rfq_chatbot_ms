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
        any_pattern_based_tool_fired: bool = False,
        capability_status_hit=None,
    ) -> PromptEnvelope:
        """Return the frozen PromptEnvelope contract for the current turn."""

        stable_prefix = self._build_stable_prefix(
            stage_resolution=stage_resolution,
            role_resolution=role_resolution,
            any_pattern_based_tool_fired=any_pattern_based_tool_fired,
            capability_status_hit=capability_status_hit,
        )

        variable_suffix = self._build_variable_suffix(
            recent_messages=recent_messages,
            retrieval_context_blocks=retrieval_context_blocks,
            latest_user_turn=latest_user_turn,
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
        any_pattern_based_tool_fired: bool,
        capability_status_hit,
    ) -> str:
        role_profile = ROLE_PROFILES[FALLBACK_ROLE]
        if role_resolution is not None and getattr(role_resolution, "profile", None):
            role_profile = role_resolution.profile

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
            capability_status_hit=capability_status_hit,
        )

        stage_lines = [f"Stage framing: {stage_fragment}"]
        if stage_name:
            stage_lines.append(f"Current stage label: {stage_name}")

        prefix_lines = [
            self.system_prompt,
            "",
            f"Role tone directive: {role_profile['tone_directive']}",
            f"Role depth directive: {role_profile['depth_directive']}",
            "",
            *stage_lines,
            "",
            *confidence_directives,
        ]
        return "\n".join(prefix_lines)

    @staticmethod
    def _build_confidence_directives(
        *,
        any_pattern_based_tool_fired: bool,
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
        capability_status_hit,
    ) -> str:
        transcript_lines = ["Conversation history:"]
        for message in recent_messages:
            transcript_lines.append(f"{message.role}: {message.content}")

        # Capability-status mode is a no-retrieval path.
        if retrieval_context_blocks and capability_status_hit is None:
            transcript_lines.append("")
            transcript_lines.append("Retrieved facts:")
            transcript_lines.extend(retrieval_context_blocks)

        if latest_user_turn:
            transcript_lines.append(f"user: {latest_user_turn}")

        transcript_lines.append("assistant:")
        return "\n".join(transcript_lines)
