import importlib
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pydantic import ValidationError

from src.models import ConfidenceLevel, SessionMode, SourceRef, ToolResultEnvelope


def test_confidence_level_exposes_exact_phase1_values():
    assert [member.value for member in ConfidenceLevel] == [
        "deterministic",
        "pattern_1_sample",
        "absent",
    ]


def test_tool_result_envelope_requires_source_ref_when_confidence_is_present():
    try:
        ToolResultEnvelope(
            value={"grand_total": 1247350},
            confidence=ConfidenceLevel.DETERMINISTIC,
        )
    except ValidationError as exc:
        assert "source_ref is required when confidence is not 'absent'" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValidationError when source_ref is missing")


def test_tool_result_envelope_allows_absent_without_source_ref():
    envelope = ToolResultEnvelope(
        value=None,
        confidence=ConfidenceLevel.ABSENT,
    )

    assert envelope.source_ref is None


def test_tool_result_envelope_accepts_source_ref_for_pattern_based_results():
    envelope = ToolResultEnvelope(
        value={"deadline_days": 14},
        confidence=ConfidenceLevel.PATTERN_1_SAMPLE,
        source_ref=SourceRef(
            system="intelligence",
            artifact="canonical_project_profile",
            locator="field=deadline_days",
        ),
        validated_against="1_sample",
    )

    assert envelope.source_ref is not None
    assert envelope.validated_against == "1_sample"


def test_confidence_level_rejects_invalid_value():
    try:
        ToolResultEnvelope(
            value="bad",
            confidence="guess",  # type: ignore[arg-type]
        )
    except ValidationError as exc:
        assert "deterministic" in str(exc)
        assert "pattern_1_sample" in str(exc)
        assert "absent" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValidationError for invalid confidence")


def test_session_mode_exposes_exact_phase1_values():
    assert [member.value for member in SessionMode] == [
        "rfq_bound",
        "portfolio",
        "pending_pivot",
    ]


def test_session_mode_rejects_invalid_value():
    try:
        SessionMode("global")
    except ValueError as exc:
        assert "global" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError for invalid session mode")


def test_models_package_exports_phase1_contracts():
    models = importlib.import_module("src.models")

    assert hasattr(models, "ChatbotSession")
    assert hasattr(models, "Conversation")
    assert hasattr(models, "Message")
    assert hasattr(models, "PromptEnvelope")
    assert hasattr(models, "TurnRequest")
    assert hasattr(models, "TurnResponse")


def test_alembic_upgrade_creates_phase1_tables(tmp_path, monkeypatch):
    database_path = tmp_path / "phase1_migration.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")

    repo_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(repo_root / "alembic.ini"))

    command.upgrade(alembic_cfg, "head")

    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = sa.inspect(engine)
        assert sorted(inspector.get_table_names()) == [
            "alembic_version",
            "chatbot_conversations",
            "chatbot_messages",
            "chatbot_sessions",
        ]
    finally:
        engine.dispose()
