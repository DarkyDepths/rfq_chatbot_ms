from types import SimpleNamespace

from src.config.role_profiles import FALLBACK_ROLE, ROLE_PROFILES
from src.controllers.role_controller import RoleController


def _session(role):
    return SimpleNamespace(role=role)


def test_resolve_role_estimation_dept_lead_without_fallback():
    controller = RoleController()

    resolution = controller.resolve_role(_session("estimation_dept_lead"))

    assert resolution.role == "estimation_dept_lead"
    assert resolution.profile == ROLE_PROFILES["estimation_dept_lead"]
    assert resolution.fallback_used is False
    assert resolution.original_role == "estimation_dept_lead"


def test_resolve_role_executive_without_fallback():
    controller = RoleController()

    resolution = controller.resolve_role(_session("executive"))

    assert resolution.role == "executive"
    assert resolution.profile == ROLE_PROFILES["executive"]
    assert resolution.fallback_used is False
    assert resolution.original_role == "executive"


def test_resolve_role_historical_estimator_uses_fallback():
    controller = RoleController()

    resolution = controller.resolve_role(_session("estimator"))

    assert resolution.role == FALLBACK_ROLE
    assert resolution.profile == ROLE_PROFILES[FALLBACK_ROLE]
    assert resolution.fallback_used is True
    assert resolution.original_role == "estimator"


def test_resolve_role_empty_string_uses_fallback():
    controller = RoleController()

    resolution = controller.resolve_role(_session(""))

    assert resolution.role == FALLBACK_ROLE
    assert resolution.profile == ROLE_PROFILES[FALLBACK_ROLE]
    assert resolution.fallback_used is True
    assert resolution.original_role == ""


def test_resolve_role_random_string_uses_fallback():
    controller = RoleController()

    resolution = controller.resolve_role(_session("finance_manager"))

    assert resolution.role == FALLBACK_ROLE
    assert resolution.profile == ROLE_PROFILES[FALLBACK_ROLE]
    assert resolution.fallback_used is True
    assert resolution.original_role == "finance_manager"


def test_resolve_role_is_case_sensitive_and_uses_fallback_for_executive_caps():
    controller = RoleController()

    resolution = controller.resolve_role(_session("Executive"))

    assert resolution.role == FALLBACK_ROLE
    assert resolution.profile == ROLE_PROFILES[FALLBACK_ROLE]
    assert resolution.fallback_used is True
    assert resolution.original_role == "Executive"
