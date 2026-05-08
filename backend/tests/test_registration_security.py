"""SE-008, SE-009, SE-013 — registration policy and password policy."""

from unittest.mock import patch

from fastapi.testclient import TestClient

import app.core.config as app_config


def test_weak_password_rejected_on_register(client: TestClient):
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "weakuser", "password": "short1"},
    )
    assert r.status_code == 422


def test_register_rejected_when_closed(client: TestClient):
    with patch.object(app_config.settings, "OPEN_REGISTRATION", False):
        r = client.post(
            "/api/v1/auth/register",
            json={"username": "closed_reg_user", "password": "Validpass12345"},
        )
    assert r.status_code == 403


def test_register_generic_error_on_duplicate(client: TestClient):
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "password": "Validpass12345"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "Unable to complete registration"


def test_login_generic_invalid_credentials(client: TestClient):
    from sqlmodel import Session, select

    from app.core.security import get_password_hash
    from app.persistence.tables import User
    from tests.conftest import engine

    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == "testuser")).first()
        user.password_hash = get_password_hash("Realpassword123")
        session.add(user)
        session.commit()

    r = client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "Wrongpassword123"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid credentials"
