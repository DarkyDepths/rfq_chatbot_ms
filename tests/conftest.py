"""Shared pytest fixtures for rfq_chatbot_ms tests."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.app import create_app
from src.database import Base
from src.database import get_db


@pytest.fixture
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(db_engine):
    testing_session_local = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def app(db_session):
    application = create_app()

    def _override_get_db():
        yield db_session

    application.dependency_overrides[get_db] = _override_get_db
    try:
        yield application
    finally:
        application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client

