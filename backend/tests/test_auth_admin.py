"""
Tests for admin user management endpoints.
PUT /auth/users/{user_id} - admin update user.
"""

import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.security import get_password_hash, verify_password
from app.persistence.tables import User
from tests.conftest import engine


def test_admin_update_user_username(client: TestClient):
    """PUT /auth/users/{user_id} (admin) can update username."""
    with Session(engine) as session:
        admin_user = session.exec(select(User).where(User.username == "testuser")).first()
        admin_user.is_admin = True
        session.add(admin_user)

        target = User(
            username="targetuser",
            password_hash=get_password_hash("Targetpass12345"),
            is_admin=False,
        )
        session.add(target)
        session.commit()
        session.refresh(target)
        target_id = target.id

    response = client.put(
        f"/api/v1/auth/users/{target_id}",
        json={"username": "newname"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "newname"
    assert data["is_admin"] is False

    with Session(engine) as session:
        user = session.get(User, target_id)
        assert user.username == "newname"


def test_admin_update_user_password(client: TestClient):
    """PUT /auth/users/{user_id} (admin) can update password."""
    with Session(engine) as session:
        admin_user = session.exec(select(User).where(User.username == "testuser")).first()
        admin_user.is_admin = True
        session.add(admin_user)

        target = User(
            username="targetuser",
            password_hash=get_password_hash("Oldpassword12"),
            is_admin=False,
        )
        session.add(target)
        session.commit()
        session.refresh(target)
        target_id = target.id

    response = client.put(
        f"/api/v1/auth/users/{target_id}",
        json={"password": "Newpassword123"},
    )
    assert response.status_code == 200

    with Session(engine) as session:
        user = session.get(User, target_id)
    assert verify_password("Newpassword123", user.password_hash)
    assert not verify_password("Oldpassword12", user.password_hash)


def test_admin_update_user_is_admin(client: TestClient):
    """PUT /auth/users/{user_id} (admin) can update is_admin."""
    with Session(engine) as session:
        admin_user = session.exec(select(User).where(User.username == "testuser")).first()
        admin_user.is_admin = True
        session.add(admin_user)

        target = User(
            username="targetuser",
            password_hash="fakehash",
            is_admin=False,
        )
        session.add(target)
        session.commit()
        session.refresh(target)
        target_id = target.id

    response = client.put(
        f"/api/v1/auth/users/{target_id}",
        json={"is_admin": True},
    )
    assert response.status_code == 200
    assert response.json()["is_admin"] is True

    with Session(engine) as session:
        user = session.get(User, target_id)
        assert user.is_admin is True


def test_admin_update_user_403_non_admin(client: TestClient):
    """PUT /auth/users/{user_id} returns 403 when non-admin."""
    with Session(engine) as session:
        target = User(
            username="targetuser",
            password_hash="fakehash",
            is_admin=False,
        )
        session.add(target)
        session.commit()
        session.refresh(target)
        target_id = target.id

    # testuser is not admin by default
    response = client.put(
        f"/api/v1/auth/users/{target_id}",
        json={"username": "newname"},
    )
    assert response.status_code == 403
    assert "authorized" in response.json()["detail"].lower() or "forbidden" in response.json()["detail"].lower()


def test_admin_update_user_404_not_found(client: TestClient):
    """PUT /auth/users/{user_id} returns 404 when user not found."""
    with Session(engine) as session:
        admin_user = session.exec(select(User).where(User.username == "testuser")).first()
        admin_user.is_admin = True
        session.add(admin_user)
        session.commit()

    fake_id = uuid.uuid4()
    response = client.put(
        f"/api/v1/auth/users/{fake_id}",
        json={"username": "newname"},
    )
    assert response.status_code == 404


def test_admin_update_user_username_taken(client: TestClient):
    """PUT /auth/users/{user_id} returns 400 with generic detail when username conflicts (SE-009)."""
    with Session(engine) as session:
        admin_user = session.exec(select(User).where(User.username == "testuser")).first()
        admin_user.is_admin = True
        session.add(admin_user)

        target = User(
            username="targetuser",
            password_hash="fakehash",
            is_admin=False,
        )
        session.add(target)
        session.commit()
        session.refresh(target)
        target_id = target.id

    # Try to change targetuser's username to testuser (already exists)
    response = client.put(
        f"/api/v1/auth/users/{target_id}",
        json={"username": "testuser"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Unable to update user"


def test_admin_update_user_multiple_fields(client: TestClient):
    """PUT /auth/users/{user_id} can update username, password, and is_admin together."""
    with Session(engine) as session:
        admin_user = session.exec(select(User).where(User.username == "testuser")).first()
        admin_user.is_admin = True
        session.add(admin_user)

        target = User(
            username="targetuser",
            password_hash=get_password_hash("Oldpassword12"),
            is_admin=False,
        )
        session.add(target)
        session.commit()
        session.refresh(target)
        target_id = target.id

    response = client.put(
        f"/api/v1/auth/users/{target_id}",
        json={
            "username": "updateduser",
            "password": "Newpassword123",
            "is_admin": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "updateduser"
    assert data["is_admin"] is True

    with Session(engine) as session:
        user = session.get(User, target_id)
        assert user.username == "updateduser"
        assert user.is_admin is True
        assert verify_password("Newpassword123", user.password_hash)


def test_admin_create_user(client: TestClient):
    """POST /auth/users creates a user (admin only)."""
    with Session(engine) as session:
        admin = session.exec(select(User).where(User.username == "testuser")).first()
        admin.is_admin = True
        session.add(admin)
        session.commit()

    username = f"created_{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/api/v1/auth/users",
        json={"username": username, "password": "NewUserPass12", "is_admin": False},
    )
    assert response.status_code == 200
    with Session(engine) as session:
        u = session.exec(select(User).where(User.username == username)).first()
        assert u is not None
        assert u.is_admin is False
        assert verify_password("NewUserPass12", u.password_hash)


def test_admin_cannot_remove_last_admin(client: TestClient):
    """PUT cannot strip is_admin when this user is the only admin."""
    with Session(engine) as session:
        admin_user = session.exec(select(User).where(User.username == "testuser")).first()
        admin_user.is_admin = True
        session.add(admin_user)
        session.commit()
        admin_id = admin_user.id

    response = client.put(
        f"/api/v1/auth/users/{admin_id}",
        json={"is_admin": False},
    )
    assert response.status_code == 400
    assert "last admin" in response.json()["detail"].lower()

    with Session(engine) as session:
        user = session.get(User, admin_id)
        assert user.is_admin is True


def test_admin_delete_user(client: TestClient):
    """DELETE /auth/users/{id} removes user; cannot delete self."""
    with Session(engine) as session:
        admin = session.exec(select(User).where(User.username == "testuser")).first()
        admin_id = admin.id
        admin.is_admin = True
        session.add(admin)

        victim = User(
            username=f"victim_{uuid.uuid4().hex[:8]}",
            password_hash=get_password_hash("VictimPass123"),
            is_admin=False,
        )
        session.add(victim)
        session.commit()
        session.refresh(victim)
        victim_id = victim.id

    del_resp = client.delete(f"/api/v1/auth/users/{victim_id}")
    assert del_resp.status_code == 204
    with Session(engine) as session:
        assert session.get(User, victim_id) is None

    self_del = client.delete(f"/api/v1/auth/users/{admin_id}")
    assert self_del.status_code == 400
    assert "yourself" in self_del.json()["detail"].lower()
