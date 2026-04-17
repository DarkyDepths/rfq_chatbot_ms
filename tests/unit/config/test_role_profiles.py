from src.config.role_profiles import FALLBACK_ROLE, ROLE_PROFILES
from src.config.stage_profiles import FULL_TOOL_ALLOW_LIST


def test_role_profiles_contains_exactly_two_frozen_roles():
    assert set(ROLE_PROFILES) == {"estimation_dept_lead", "executive"}


def test_fallback_role_is_estimation_dept_lead():
    assert FALLBACK_ROLE == "estimation_dept_lead"


def test_role_profile_tool_allow_lists_are_subsets_of_full_tool_set():
    for profile in ROLE_PROFILES.values():
        assert profile["tool_allow_list"].issubset(FULL_TOOL_ALLOW_LIST)
