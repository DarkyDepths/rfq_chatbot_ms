"""Phase 5 Mode A stage profile configuration."""

from __future__ import annotations

from typing import TypedDict
from uuid import UUID


FULL_TOOL_ALLOW_LIST: frozenset[str] = frozenset(
    {"get_rfq_profile", "get_rfq_stage", "get_rfq_snapshot"}
)


class StageProfile(TypedDict):
    prompt_frame_fragment: str
    tool_allow_list: frozenset[str]


STAGE_PROFILES: dict[UUID, StageProfile] = {
    # Real manager-side current_stage_id from seeded manager manifest (RFQ-02).
    UUID("ed68fc92-e510-4595-b980-e564f5791ccd"): {
        "prompt_frame_fragment": (
            "Treat the RFQ as being in Go / No-Go and emphasize qualification "
            "risk, assumptions, and immediate decision clarity."
        ),
        "tool_allow_list": frozenset(
            {"get_rfq_profile", "get_rfq_stage", "get_rfq_snapshot"}
        ),
    }
}


DEFAULT_STAGE_PROFILE: StageProfile = {
    "prompt_frame_fragment": (
        "Use neutral stage framing when exact stage context is unavailable."
    ),
    "tool_allow_list": FULL_TOOL_ALLOW_LIST,
}
