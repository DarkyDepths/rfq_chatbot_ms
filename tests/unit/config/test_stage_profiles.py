from src.config.stage_profiles import (
    DEFAULT_STAGE_PROFILE,
    FULL_TOOL_ALLOW_LIST,
    STAGE_PROFILES,
)


def test_default_stage_profile_tool_allow_list_matches_full_tool_set():
    assert DEFAULT_STAGE_PROFILE["tool_allow_list"] == frozenset(
        {"get_rfq_profile", "get_rfq_stage", "get_rfq_snapshot"}
    )


def test_stage_profiles_are_non_empty_and_within_full_tool_set():
    assert STAGE_PROFILES
    for profile in STAGE_PROFILES.values():
        assert profile["prompt_frame_fragment"].strip()
        assert profile["tool_allow_list"].issubset(FULL_TOOL_ALLOW_LIST)
