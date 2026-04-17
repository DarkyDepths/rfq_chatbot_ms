"""Role resolution controller for Phase 5 Mode A."""

from __future__ import annotations

from dataclasses import dataclass

from src.config.role_profiles import (
    FALLBACK_ROLE,
    ROLE_PROFILES,
    RoleProfile,
)
from src.models.session import ChatbotSession


@dataclass(frozen=True)
class RoleResolution:
    """Internal role-resolution result used by the turn pipeline."""

    role: str
    profile: RoleProfile
    fallback_used: bool
    original_role: str | None


class RoleController:
    """Resolves a role profile from the persisted session role value."""

    def resolve_role(self, session: ChatbotSession) -> RoleResolution:
        """Resolve the role profile with the frozen estimation fallback rule."""

        original_role = session.role
        if original_role in ROLE_PROFILES:
            return RoleResolution(
                role=original_role,
                profile=ROLE_PROFILES[original_role],
                fallback_used=False,
                original_role=original_role,
            )

        return RoleResolution(
            role=FALLBACK_ROLE,
            profile=ROLE_PROFILES[FALLBACK_ROLE],
            fallback_used=True,
            original_role=original_role,
        )
