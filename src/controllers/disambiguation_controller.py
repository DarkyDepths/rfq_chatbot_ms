"""Disambiguation context assembly for Phase 6 RFQ clarification turns."""

from __future__ import annotations

from src.controllers.role_controller import RoleResolution


class DisambiguationController:
    """Builds lightweight context payloads for disambiguation prompt generation."""

    def build_disambiguation_context(
        self,
        user_content: str,
        role_resolution: RoleResolution,
    ) -> dict:
        """Return context consumed by ContextBuilder for disambiguation behavior."""

        return {
            "disambiguation_mode": True,
            "user_question": user_content,
            "role_profile": role_resolution.profile,
        }
