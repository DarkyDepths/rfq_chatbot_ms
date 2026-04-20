"""Golden set regression suite for Phase 7 Step 3."""

from __future__ import annotations

from pathlib import Path

import pytest

from golden_set.harness import case_paths, load_case, run_case


CASE_PATHS = case_paths()


def _case_id(case_path: Path) -> str:
    return load_case(case_path)["id"]


@pytest.mark.parametrize("case_path", CASE_PATHS, ids=_case_id)
def test_golden_cases(case_path: Path, client, app, db_session, caplog):
    case = load_case(case_path)
    run_case(case, client=client, app=app, db_session=db_session, caplog=caplog)


def test_golden_case_suite_has_required_minimum_case_count():
    assert len(CASE_PATHS) >= 20


def test_defense_demo_beats_are_present_in_case_suite():
    ids = {load_case(path)["id"] for path in CASE_PATHS}

    required_demo_ids = {
        "beat0_welcome_rfq_bound",
        "beat1_deterministic_grounded",
        "beat2_pattern_based_confidence",
        "beat3_honest_absence",
        "beat4_role_contrast_estimation",
        "beat4_role_contrast_executive",
    }

    assert required_demo_ids.issubset(ids)
