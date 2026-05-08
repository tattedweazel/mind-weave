"""CLI create-admin."""

import uuid

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.cli.__main__ import cmd_create_admin
from app.persistence.tables import User


@pytest.fixture
def cli_engine(monkeypatch):
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr("app.cli.__main__.engine", eng)
    yield eng
    SQLModel.metadata.drop_all(eng)
    eng.dispose(close=True)


def test_create_admin_adds_user(cli_engine):
    ns = argparse_namespace(
        username=f"cliuser_{uuid.uuid4().hex[:8]}",
        password="CliUserSecret!1",
        admin=True,
    )
    assert cmd_create_admin(ns) == 0
    with Session(cli_engine) as session:
        u = session.exec(select(User).where(User.username == ns.username)).first()
        assert u is not None
        assert u.is_admin is True


def test_create_admin_duplicate_returns_1(cli_engine):
    username = f"dup_{uuid.uuid4().hex[:8]}"
    ns = argparse_namespace(username=username, password="pw", admin=False)
    assert cmd_create_admin(ns) == 0
    assert cmd_create_admin(ns) == 1


def argparse_namespace(**kwargs):
    return type("Args", (), kwargs)()
