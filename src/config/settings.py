"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    DATABASE_URL: str

    APP_ENV: str = "development"
    APP_PORT: int = 8003
    APP_DEBUG: bool = False
    CORS_ORIGINS: str = "*"

    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-12-01-preview"
    AZURE_OPENAI_CHAT_DEPLOYMENT: str = ""
    AZURE_OPENAI_INTENT_DEPLOYMENT: str = ""
    AZURE_OPENAI_TIMEOUT_SECONDS: float = 30.0

    MANAGER_BASE_URL: str = ""
    INTELLIGENCE_BASE_URL: str = ""
    MANAGER_REQUEST_TIMEOUT_SECONDS: float = 10.0
    INTELLIGENCE_REQUEST_TIMEOUT_SECONDS: float = 10.0
    IAM_SERVICE_URL: str = ""

    AUTH_BYPASS_ENABLED: bool = False
    AUTH_BYPASS_USER_ID: str = "v1-demo-user"
    AUTH_BYPASS_USER_NAME: str = "System"
    AUTH_BYPASS_ROLE: str = "estimation_dept_lead"
    AUTH_BYPASS_DEBUG_HEADERS_ENABLED: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def build_settings(env_file: str | None = ".env") -> Settings:
    """Load settings and fail fast when DATABASE_URL is missing or invalid."""

    try:
        cfg = Settings(_env_file=env_file)
    except ValidationError as exc:
        raise RuntimeError(
            "Configuration error: DATABASE_URL is required. "
            "Set DATABASE_URL to a valid SQLAlchemy URL, for example: "
            "postgresql+psycopg2://rfq_chatbot_user:changeme@localhost:5434/rfq_chatbot_db"
        ) from exc

    database_url = (cfg.DATABASE_URL or "").strip()
    if not database_url:
        raise RuntimeError(
            "Configuration error: DATABASE_URL is required and cannot be empty. "
            "Set DATABASE_URL to a valid SQLAlchemy URL, for example: "
            "postgresql+psycopg2://rfq_chatbot_user:changeme@localhost:5434/rfq_chatbot_db"
        )

    try:
        make_url(database_url)
    except Exception as exc:
        raise RuntimeError(
            f"Configuration error: DATABASE_URL is not a valid SQLAlchemy URL: '{database_url}'. "
            "Example: postgresql+psycopg2://rfq_chatbot_user:changeme@localhost:5434/rfq_chatbot_db"
        ) from exc

    return cfg


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance lazily."""

    return build_settings()
