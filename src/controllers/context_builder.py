"""Minimal Phase 4 prompt assembly."""

from __future__ import annotations

from src.models.prompt import PromptEnvelope


class ContextBuilder:
    """Build the Phase 4 prompt envelope from history plus retrieved facts."""

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
    ) -> PromptEnvelope:
        """Return the frozen PromptEnvelope contract for the current turn."""

        transcript_lines = ["Conversation history:"]
        for message in recent_messages:
            transcript_lines.append(f"{message.role}: {message.content}")

        if latest_user_turn:
            transcript_lines.append(f"user: {latest_user_turn}")

        if retrieval_context_blocks:
            transcript_lines.append("")
            transcript_lines.append("Retrieved facts:")
            transcript_lines.extend(retrieval_context_blocks)

        transcript_lines.append("assistant:")

        return PromptEnvelope(
            stable_prefix=self.system_prompt,
            variable_suffix="\n".join(transcript_lines),
            total_budget=self.total_budget,
        )
