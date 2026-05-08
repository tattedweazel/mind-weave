"""
Tests for Google OAuth account association and login.
All external HTTP calls (Google token/userinfo) are mocked - no real requests.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.persistence.tables import User
from tests.conftest import engine


@patch("app.api.v1.auth.settings")
def test_google_login_redirects_to_google(mock_settings, client: TestClient):
    """GET /auth/google/login redirects to Google when configured."""
    mock_settings.GOOGLE_CLIENT_ID = "test"
    mock_settings.GOOGLE_CLIENT_SECRET = "test"
    mock_settings.FRONTEND_URL = "http://localhost:5173"

    response = client.get("/api/v1/auth/google/login", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "accounts.google.com" in response.headers["location"]
    assert "state=" in response.headers["location"]


@patch("app.api.v1.auth.settings")
def test_google_login_head_redirects_to_google(mock_settings, client: TestClient):
    """HEAD /auth/google/login matches GET redirect (for `curl -I`)."""
    mock_settings.GOOGLE_CLIENT_ID = "test"
    mock_settings.GOOGLE_CLIENT_SECRET = "test"
    mock_settings.FRONTEND_URL = "http://localhost:5173"

    response = client.head("/api/v1/auth/google/login", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "accounts.google.com" in response.headers["location"]
    assert "state=" in response.headers["location"]


@patch("app.api.v1.auth.settings")
def test_google_login_not_configured(mock_settings, client: TestClient):
    """GET /auth/google/login redirects to frontend with error when not configured."""
    mock_settings.GOOGLE_CLIENT_ID = ""
    mock_settings.GOOGLE_CLIENT_SECRET = ""
    mock_settings.FRONTEND_URL = "http://localhost:5173"

    response = client.get("/api/v1/auth/google/login", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "google_error=not_configured" in response.headers["location"]


@patch("app.api.v1.auth.exchange_code_for_user_info")
@patch("app.api.v1.auth.settings")
def test_google_callback_login_flow(
    mock_settings,
    mock_exchange,
    client: TestClient,
):
    """GET /auth/google/callback with login state finds user, redirects with one-time google_session code."""
    mock_settings.GOOGLE_CLIENT_ID = "test"
    mock_settings.GOOGLE_CLIENT_SECRET = "test"
    mock_settings.FRONTEND_URL = "http://localhost:5173"
    mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 1440
    mock_exchange.return_value = {"sub": "google-login-123", "email": "login@gmail.com"}

    # Give testuser a Google association
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == "testuser")).first()
        user.google_user_id = "google-login-123"
        user.google_email = "login@gmail.com"
        session.add(user)
        session.commit()

    # Get login state
    login_resp = client.get("/api/v1/auth/google/login", follow_redirects=False)
    assert login_resp.status_code in (302, 307)
    redirect_url = login_resp.headers["location"]
    state = redirect_url.split("state=")[1].split("&")[0]

    # Callback
    callback_resp = client.get(
        f"/api/v1/auth/google/callback?code=fakecode&state={state}",
        follow_redirects=False,
    )
    assert callback_resp.status_code in (302, 307)
    loc = callback_resp.headers["location"]
    assert "#google_session=" in loc
    assert loc.startswith("http://localhost:5173/#google_session=")

    code = loc.split("google_session=")[1].split("&")[0]
    complete = client.post(
        "/api/v1/auth/google/session",
        json={"code": code},
    )
    assert complete.status_code == 200
    assert complete.json()["token_type"] == "bearer"
    assert "mw_access_token" in complete.cookies


@patch("app.api.v1.auth.exchange_code_for_user_info")
@patch("app.api.v1.auth.settings")
def test_google_callback_login_no_account(
    mock_settings,
    mock_exchange,
    client: TestClient,
):
    """GET /auth/google/callback with login state when no user has google_user_id redirects with no_account."""
    mock_settings.GOOGLE_CLIENT_ID = "test"
    mock_settings.GOOGLE_CLIENT_SECRET = "test"
    mock_settings.FRONTEND_URL = "http://localhost:5173"
    mock_exchange.return_value = {"sub": "google-unknown", "email": "unknown@gmail.com"}

    login_resp = client.get("/api/v1/auth/google/login", follow_redirects=False)
    state = login_resp.headers["location"].split("state=")[1].split("&")[0]

    callback_resp = client.get(
        f"/api/v1/auth/google/callback?code=fakecode&state={state}",
        follow_redirects=False,
    )
    assert callback_resp.status_code in (302, 307)
    assert "google_error=no_account" in callback_resp.headers["location"]


def test_login_rejects_user_with_google(client: TestClient):
    """POST /login returns 400 use_google_login when user has google_user_id."""
    from app.core.security import get_password_hash

    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == "testuser")).first()
        user.password_hash = get_password_hash("Testpass123456")
        user.google_user_id = "google-123"
        user.google_email = "test@gmail.com"
        session.add(user)
        session.commit()

    response = client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "Testpass123456"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "use_google_login"


@patch("app.api.v1.auth.settings")
def test_google_authorize_returns_redirect_url(mock_settings, client: TestClient):
    """POST /auth/google/authorize returns redirect_url when Google OAuth is configured."""
    mock_settings.GOOGLE_CLIENT_ID = "test-client-id"
    mock_settings.GOOGLE_CLIENT_SECRET = "test-client-secret"
    mock_settings.GOOGLE_REDIRECT_URI = "http://localhost:8000/api/v1/auth/google/callback"

    response = client.post("/api/v1/auth/google/authorize")
    assert response.status_code == 200
    data = response.json()
    assert "redirect_url" in data
    assert "accounts.google.com" in data["redirect_url"]
    assert "state=" in data["redirect_url"]


@patch("app.api.v1.auth.settings")
def test_google_authorize_not_configured(mock_settings, client: TestClient):
    """POST /auth/google/authorize returns 503 when Google OAuth is not configured."""
    mock_settings.GOOGLE_CLIENT_ID = ""
    mock_settings.GOOGLE_CLIENT_SECRET = ""

    response = client.post("/api/v1/auth/google/authorize")
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


@patch("app.api.v1.auth.exchange_code_for_user_info")
@patch("app.api.v1.auth.settings")
def test_google_callback_associates_user(
    mock_settings,
    mock_exchange,
    client: TestClient,
):
    """GET /auth/google/callback with valid code/state associates Google account with user."""
    mock_settings.GOOGLE_CLIENT_ID = "test"
    mock_settings.GOOGLE_CLIENT_SECRET = "test"
    mock_settings.FRONTEND_URL = "http://localhost:5173"
    mock_exchange.return_value = {"sub": "google-123", "email": "user@gmail.com"}

    # First get state by calling authorize
    auth_resp = client.post("/api/v1/auth/google/authorize")
    assert auth_resp.status_code == 200
    redirect_url = auth_resp.json()["redirect_url"]
    state = redirect_url.split("state=")[1].split("&")[0]

    # Call callback (follow_redirects=False to get redirect response)
    callback_resp = client.get(
        f"/api/v1/auth/google/callback?code=fakecode&state={state}",
        follow_redirects=False,
    )
    assert callback_resp.status_code in (302, 307)
    assert "google_associated=1" in callback_resp.headers["location"]

    # Verify user was updated
    me_resp = client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["google_email"] == "user@gmail.com"


@patch("app.api.v1.auth.settings")
def test_google_callback_expired_state(mock_settings, client: TestClient):
    """GET /auth/google/callback with invalid/expired state redirects with error."""
    mock_settings.FRONTEND_URL = "http://localhost:5173"

    response = client.get(
        "/api/v1/auth/google/callback?code=fakecode&state=invalid-state",
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "google_error=expired" in response.headers["location"]


@patch("app.api.v1.auth.exchange_code_for_user_info")
@patch("app.api.v1.auth.settings")
def test_google_callback_already_linked(
    mock_settings,
    mock_exchange,
    client: TestClient,
):
    """GET /auth/google/callback when Google account is linked to another user redirects with error."""
    mock_settings.GOOGLE_CLIENT_ID = "test"
    mock_settings.GOOGLE_CLIENT_SECRET = "test"
    mock_settings.FRONTEND_URL = "http://localhost:5173"
    mock_exchange.return_value = {"sub": "google-456", "email": "other@gmail.com"}

    # Create another user with this Google account already linked
    with Session(engine) as session:
        other_user = User(
            username="otheruser",
            password_hash="fakehash",
            google_user_id="google-456",
            google_email="other@gmail.com",
        )
        session.add(other_user)
        session.commit()

    # Get state for testuser
    auth_resp = client.post("/api/v1/auth/google/authorize")
    assert auth_resp.status_code == 200
    redirect_url = auth_resp.json()["redirect_url"]
    state = redirect_url.split("state=")[1].split("&")[0]

    # Callback should fail - Google account already linked to otheruser
    callback_resp = client.get(
        f"/api/v1/auth/google/callback?code=fakecode&state={state}",
        follow_redirects=False,
    )
    assert callback_resp.status_code in (302, 307)
    assert "google_error=already_linked" in callback_resp.headers["location"]


@patch("app.api.v1.auth.settings")
def test_google_callback_missing_params(mock_settings, client: TestClient):
    """GET /auth/google/callback without code or state redirects with error."""
    mock_settings.FRONTEND_URL = "http://localhost:5173"

    response = client.get(
        "/api/v1/auth/google/callback",
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "google_error=missing_params" in response.headers["location"]


@patch("app.api.v1.auth.settings")
def test_google_callback_denied(mock_settings, client: TestClient):
    """GET /auth/google/callback with error param (user denied) redirects with error."""
    mock_settings.FRONTEND_URL = "http://localhost:5173"

    response = client.get(
        "/api/v1/auth/google/callback?error=access_denied",
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "google_error=denied" in response.headers["location"]


@patch("app.api.v1.auth.exchange_code_for_user_info")
@patch("app.api.v1.auth.settings")
def test_google_disassociate(
    mock_settings,
    mock_exchange,
    client: TestClient,
):
    """POST /auth/google/disassociate clears Google fields from current user."""
    mock_settings.GOOGLE_CLIENT_ID = "test"
    mock_settings.GOOGLE_CLIENT_SECRET = "test"
    mock_settings.FRONTEND_URL = "http://localhost:5173"
    mock_exchange.return_value = {"sub": "google-789", "email": "disassoc@gmail.com"}

    # Associate first
    auth_resp = client.post("/api/v1/auth/google/authorize")
    state = auth_resp.json()["redirect_url"].split("state=")[1].split("&")[0]
    client.get(f"/api/v1/auth/google/callback?code=fake&state={state}", follow_redirects=False)

    me_before = client.get("/api/v1/auth/me").json()
    assert me_before["google_email"] == "disassoc@gmail.com"

    # Disassociate
    dis_resp = client.post("/api/v1/auth/google/disassociate")
    assert dis_resp.status_code == 204

    me_after = client.get("/api/v1/auth/me").json()
    assert me_after["google_email"] is None


def test_me_includes_google_email(client: TestClient):
    """GET /auth/me includes google_email in response."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert "google_email" in data
    assert data["google_email"] is None


def test_admin_disassociate_google_for_user(client: TestClient):
    """POST /auth/users/{user_id}/google/disassociate (admin) clears Google for target user."""
    with Session(engine) as session:
        admin_user = session.exec(select(User).where(User.username == "testuser")).first()
        admin_user.is_admin = True
        session.add(admin_user)

        other_user = User(
            username="otheruser",
            password_hash="fakehash",
            google_user_id="google-other",
            google_email="other@gmail.com",
        )
        session.add(other_user)
        session.commit()
        session.refresh(other_user)
        other_user_id = other_user.id

    # Client uses testuser who is now admin
    response = client.post(f"/api/v1/auth/users/{other_user_id}/google/disassociate")
    assert response.status_code == 204

    with Session(engine) as session:
        user = session.get(User, other_user_id)
        assert user.google_user_id is None
        assert user.google_email is None


def test_list_users_includes_google_email(client: TestClient):
    """GET /auth/users includes google_email for admin."""
    with Session(engine) as session:
        admin_user = session.exec(select(User).where(User.username == "testuser")).first()
        admin_user.is_admin = True
        session.add(admin_user)
        session.commit()

    response = client.get("/api/v1/auth/users")
    assert response.status_code == 200
    users = response.json()
    assert len(users) >= 1
    for u in users:
        assert "google_email" in u
