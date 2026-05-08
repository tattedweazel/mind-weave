"""Tests for DocumentService.upsert_document (replace, append, merge_json)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.domain.services.document_service import DocumentService
from app.persistence.tables import User


@pytest.fixture
def user_id(db_session: Session) -> uuid.UUID:
    user = db_session.exec(select(User)).first()
    assert user is not None
    return user.id


def test_upsert_replace_creates_and_updates(db_session: Session, user_id: uuid.UUID):
    name = f"upsert_rep_{uuid.uuid4().hex[:8]}"
    svc = DocumentService(db_session, user_id=user_id)
    d1 = svc.upsert_document(name=name, content="first", write_mode="replace")
    assert d1.body == "first"
    d2 = svc.upsert_document(name=name, content="second", write_mode="replace")
    assert d2.id == d1.id
    assert d2.body == "second"


def test_upsert_append_joins_with_blank_line(db_session: Session, user_id: uuid.UUID):
    name = f"ups_app_{uuid.uuid4().hex[:8]}"
    svc = DocumentService(db_session, user_id=user_id)
    svc.upsert_document(name=name, content="a", write_mode="replace")
    d2 = svc.upsert_document(name=name, content="b", write_mode="append")
    assert d2.body == "a\n\nb"


def test_upsert_merge_json_by_name_merges(db_session: Session, user_id: uuid.UUID):
    name = f"ups_mj_{uuid.uuid4().hex[:8]}"
    svc = DocumentService(db_session, user_id=user_id)
    svc.upsert_document(name=name, content='{"a":1}', write_mode="replace")
    d2 = svc.upsert_document(name=name, content='{"b":2}', write_mode="merge_json")
    assert d2.body == '{"a":1,"b":2}'


def test_upsert_merge_json_new_document_stores_incoming_only(db_session: Session, user_id: uuid.UUID):
    name = f"ups_mj_new_{uuid.uuid4().hex[:8]}"
    svc = DocumentService(db_session, user_id=user_id)
    d = svc.upsert_document(name=name, content='{"z":9}', write_mode="merge_json")
    assert d.body == '{"z":9}'


def test_upsert_merge_json_fails_on_invalid_existing_body(db_session: Session, user_id: uuid.UUID):
    name = f"ups_mj_bad_{uuid.uuid4().hex[:8]}"
    svc = DocumentService(db_session, user_id=user_id)
    svc.upsert_document(name=name, content="not-json", write_mode="replace")
    with pytest.raises(ValueError, match="Existing document body"):
        svc.upsert_document(name=name, content="{}", write_mode="merge_json")


def test_upsert_by_existing_id_merge_json(client: TestClient, db_session: Session, user_id: uuid.UUID):
    doc_res = client.post(
        "/api/v1/documents/",
        json={"name": f"id_mj_{uuid.uuid4().hex[:8]}", "description": "", "body": '{"x":1}'},
    )
    assert doc_res.status_code == 201
    did = uuid.UUID(doc_res.json()["id"])
    svc = DocumentService(db_session, user_id=user_id)
    d = svc.upsert_document(
        name="ignored",
        content='{"x":2,"y":3}',
        existing_document_id=did,
        write_mode="merge_json",
    )
    assert d.body == '{"x":2,"y":3}'
