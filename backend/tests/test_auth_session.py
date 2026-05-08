"""Password auth session: HttpOnly cookies, refresh, logout, register success."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt
from sqlmodel import Session, SQLModel

from app.api.deps import get_current_user
from app.core.auth_cookies import COOKIE_ACCESS, COOKIE_REFRESH
from app.core.config import settings
from app.core.security import ALGORITHM, get_password_hash
from app.domain.services.palette_service import PaletteService
from app.domain.services.persona_service import PersonaService
from app.main import app
from app.persistence import db as app_db
from app.persistence.tables import User
from tests.conftest import engine

_SESSION_PASSWORD = "SessionTestPass1"


@pytest.fixture(name="client_auth_session")
def client_auth_session_fixture():
    """Real JWT + cookie auth; no get_current_user override."""
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        PersonaService(session).initialize_default_personas()
        PaletteService(session).initialize_default_palette()
        session.add(
            User(
                username="sessionuser",
                password_hash=get_password_hash(_SESSION_PASSWORD),
                is_admin=False,
            )
        )
        session.commit()

    app.dependency_overrides.pop(get_current_user, None)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        SQLModel.metadata.drop_all(engine)
        app_db.engine.dispose(close=True)
        engine.dispose(close=True)


def _login_form(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        data={
            "username": "sessionuser",
            "password": _SESSION_PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["token_type"] == "bearer"
    assert response.json().get("access_token") is None
    assert response.cookies.get(COOKIE_ACCESS) is not None
    assert response.cookies.get(COOKIE_REFRESH) is not None


def test_password_login_sets_cookies_and_me_with_cookie_only(client_auth_session: TestClient):
    _login_form(client_auth_session)
    me = client_auth_session.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "sessionuser"


def test_refresh_rotates_session(client_auth_session: TestClient):
    _login_form(client_auth_session)
    access_before = client_auth_session.cookies.get(COOKIE_ACCESS)
    refresh = client_auth_session.cookies.get(COOKIE_REFRESH)
    assert access_before and refresh

    response = client_auth_session.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    assert response.cookies.get(COOKIE_ACCESS) is not None
    assert response.cookies.get(COOKIE_REFRESH) is not None

    me = client_auth_session.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "sessionuser"


def test_refresh_rejects_reused_refresh_after_rotation(client_auth_session: TestClient):
    """Old refresh JWT is revoked after successful rotation (SE-010)."""
    _login_form(client_auth_session)
    old_refresh = client_auth_session.cookies.get(COOKIE_REFRESH)
    assert old_refresh
    assert client_auth_session.post("/api/v1/auth/refresh").status_code == 200
    reuse = client_auth_session.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"{COOKIE_REFRESH}={old_refresh}"},
    )
    assert reuse.status_code == 401


def test_refresh_rejects_token_without_jti(client_auth_session: TestClient):
    """Refresh JWTs must include jti (SE-031)."""
    exp = datetime.now(timezone.utc) + timedelta(days=1)
    bad = jose_jwt.encode(
        {"sub": "sessionuser", "typ": "refresh", "exp": exp},
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )
    r = client_auth_session.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"{COOKIE_REFRESH}={bad}"},
    )
    assert r.status_code == 401


def test_me_rejects_bearer_access_token_without_typ(client_auth_session: TestClient):
    """Access JWTs must declare typ=access (SE-032)."""
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    tok = jose_jwt.encode(
        {"sub": "sessionuser", "exp": exp},
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )
    r = client_auth_session.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 401


def test_me_rejects_refresh_token_as_bearer(client_auth_session: TestClient):
    exp = datetime.now(timezone.utc) + timedelta(days=1)
    tok = jose_jwt.encode(
        {
            "sub": "sessionuser",
            "typ": "refresh",
            "exp": exp,
            "jti": "x" * 10,
        },
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )
    r = client_auth_session.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 401


def test_refresh_rejected_after_logout(client_auth_session: TestClient):
    _login_form(client_auth_session)
    refresh = client_auth_session.cookies.get(COOKIE_REFRESH)
    assert refresh
    assert client_auth_session.post("/api/v1/auth/logout").status_code == 204
    again = client_auth_session.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"{COOKIE_REFRESH}={refresh}"},
    )
    assert again.status_code == 401


def test_logout_clears_session(client_auth_session: TestClient):
    _login_form(client_auth_session)
    out = client_auth_session.post("/api/v1/auth/logout")
    assert out.status_code == 204

    me = client_auth_session.get("/api/v1/auth/me")
    assert me.status_code == 401


def test_register_success_sets_cookies_and_me(client_auth_session: TestClient):
    username = f"reguser_{uuid.uuid4().hex[:10]}"
    password = "RegisterOkPass12"
    response = client_auth_session.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    assert response.cookies.get(COOKIE_ACCESS) is not None
    assert response.cookies.get(COOKIE_REFRESH) is not None

    me = client_auth_session.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == username
