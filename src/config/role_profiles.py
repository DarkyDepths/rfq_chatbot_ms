"""Phase 5 Mode A role profile configuration."""

from __future__ import annotations

from typing import TypedDict

from src.config.stage_profiles import FULL_TOOL_ALLOW_LIST


class RoleProfile(TypedDict):
    tone_directive: str
    depth_directive: str
    tool_allow_list: frozenset[str]


ROLE_PROFILES: dict[str, RoleProfile] = {
    "estimation_dept_lead": {
        "tone_directive": (
            "Respond as a technical estimation peer using operationally useful language."
        ),
        "depth_directive": (
            "Provide working-level detail, assumptions, and next-step specifics when relevant."
        ),
        "tool_allow_list": FULL_TOOL_ALLOW_LIST,
    },
    "executive": {
        "tone_directive": "Respond in a decision-oriented executive tone.",
        "depth_directive": (
            "Lead with summary-level outcomes and include field-level detail only when requested."
        ),
        "tool_allow_list": FULL_TOOL_ALLOW_LIST,
    },
}


FALLBACK_ROLE: str = "estimation_dept_lead"
