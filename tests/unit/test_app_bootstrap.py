from fastapi import FastAPI

from src.app import app, create_app
from src.config.settings import build_settings, get_settings


def test_build_settings_accepts_valid_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./phase0_settings_check.db")
    get_settings.cache_clear()

    cfg = build_settings(env_file=None)

    assert cfg.DATABASE_URL == "sqlite:///./phase0_settings_check.db"


def test_get_settings_loads_lazily(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./phase0_lazy_settings_check.db")
    get_settings.cache_clear()

    cfg = get_settings()

    assert cfg.DATABASE_URL == "sqlite:///./phase0_lazy_settings_check.db"
    get_settings.cache_clear()


def test_create_app_returns_fastapi_instance():
    application = create_app()

    assert isinstance(application, FastAPI)
    assert application.title == "rfq_chatbot_ms"
    assert application.version == "0.1.0"


def test_module_level_app_is_available():
    assert isinstance(app, FastAPI)
