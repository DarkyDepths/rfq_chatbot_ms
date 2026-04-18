from src.config.role_profiles import ROLE_PROFILES
from src.controllers.disambiguation_controller import DisambiguationController
from src.controllers.role_controller import RoleResolution


def _role_resolution(role: str) -> RoleResolution:
    return RoleResolution(
        role=role,
        profile=ROLE_PROFILES[role],
        fallback_used=False,
        original_role=role,
    )


def test_build_disambiguation_context_returns_expected_fields():
    controller = DisambiguationController()
    role_resolution = _role_resolution("estimation_dept_lead")

    context = controller.build_disambiguation_context(
        user_content="what's the status of this RFQ?",
        role_resolution=role_resolution,
    )

    assert context["disambiguation_mode"] is True
    assert context["user_question"] == "what's the status of this RFQ?"
    assert context["role_profile"] == ROLE_PROFILES["estimation_dept_lead"]


def test_build_disambiguation_context_passes_through_role_profile_for_executive():
    controller = DisambiguationController()
    role_resolution = _role_resolution("executive")

    context = controller.build_disambiguation_context(
        user_content="which one are we talking about?",
        role_resolution=role_resolution,
    )

    assert context["role_profile"] == ROLE_PROFILES["executive"]
