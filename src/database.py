"""SQLAlchemy engine, session factory, and declarative base."""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from src.config.settings import get_settings

Base = declarative_base()


@lru_cache
def get_engine() -> Engine:
    """Build the process-wide SQLAlchemy engine lazily."""

    settings = get_settings()
    return create_engine(
        settings.DATABASE_URL,
        echo=settings.APP_DEBUG,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Build the session factory lazily once the engine is available."""

    return sessionmaker(
        bind=get_engine(),
        autocommit=False,
        autoflush=False,
    )


def get_db():
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
