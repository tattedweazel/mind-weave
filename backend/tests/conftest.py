import os
import uuid

# Ensure config validates before any `app` import (SECRET_KEY / APP_ENV).
os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault(
    "SECRET_KEY",
    "pytest-secret-key-at-least-sixteen-characters",
)
os.environ.setdefault("AUTH_LOGIN_RATE_LIMIT", "10000/minute")
os.environ.setdefault("AUTH_REGISTER_RATE_LIMIT", "10000/minute")
os.environ.setdefault("AUTH_REFRESH_RATE_LIMIT", "10000/minute")
os.environ.setdefault("AUTH_GOOGLE_SESSION_RATE_LIMIT", "10000/minute")
os.environ.setdefault("WORKFLOW_RUN_RATE_LIMIT", "10000/minute")
os.environ.setdefault("LMSTUDIO_API_KEY", "pytest-lmstudio-key")

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.api.deps import get_current_user
from app.domain.sandbox.starter_workflow_seed import ensure_starter_sandbox_workflow
from app.domain.services.palette_service import PaletteService
from app.domain.services.persona_service import PersonaService
from app.domain.services.system_palette_service import SystemPaletteService
from app.main import app
from app.persistence import db as app_db
from app.persistence.db import get_session
from app.persistence.tables import User

# Create a clean SQLite database for each test session
engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


def get_session_override():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_session] = get_session_override


@pytest.fixture(name="db_session")
def db_session_fixture(client: TestClient):
    """SQLModel session on the same in-memory engine as API tests (after tables + seed user exist)."""
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture():
    import app.main as app_main_layer
    import app.persistence.db as persistence_db_layer

    persistence_db_layer.engine = engine
    app_main_layer.engine = persistence_db_layer.engine

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        PersonaService(session).initialize_default_personas()
        PaletteService(session).initialize_default_palette()
        SystemPaletteService(session).initialize_builtin_system_palettes()
        ensure_starter_sandbox_workflow(session)

        # Create test user
        test_user = User(id=uuid.uuid4(), username="testuser", password_hash="fakehash", is_admin=False)
        session.add(test_user)
        session.commit()
        session.refresh(test_user)

    def override_get_current_user():
        with Session(engine) as s:
            return s.get(User, test_user.id)

    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_current_user, None)
    SQLModel.metadata.drop_all(engine)
    # Lifespan uses app_db.engine (often file SQLite); tests use `engine` override — close both
    # to avoid ResourceWarning: unclosed database.
    app_db.engine.dispose(close=True)
    engine.dispose(close=True)


@pytest.fixture(name="client_anonymous")
def client_anonymous_fixture():
    """TestClient with DB session override but real JWT/cookie auth (for 401 tests)."""
    import app.main as app_main_layer
    import app.persistence.db as persistence_db_layer

    persistence_db_layer.engine = engine
    app_main_layer.engine = persistence_db_layer.engine

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        PersonaService(session).initialize_default_personas()
        PaletteService(session).initialize_default_palette()
        SystemPaletteService(session).initialize_builtin_system_palettes()
        ensure_starter_sandbox_workflow(session)
    app.dependency_overrides.pop(get_current_user, None)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        SQLModel.metadata.drop_all(engine)
        app_db.engine.dispose(close=True)
        engine.dispose(close=True)
