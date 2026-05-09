"""Unit tests for Workspace default Google connection graph injection."""

from __future__ import annotations

import copy
import uuid

import pytest
from sqlmodel import Session

from app.domain.workspace.workspace_google_graph import (
    normalize_workflow_graph_skill_aliases_inplace,
    skill_node_skill_type,
    workflow_graph_with_default_google_connection,
)
from app.persistence.tables import GoogleWorkflowConnection, User


@pytest.fixture
def graph_with_gmail_skill() -> dict:
    return {
        "nodes": [
            {
                "id": "g1",
                "kind": "skill",
                "data": {"skill_type": "gmail_list_messages"},
            },
            {
                "id": "c1",
                "kind": "skill",
                "data": {"skill_type": "calendar_list_events"},
            },
        ]
    }


def _add_user_and_connection(session: Session) -> tuple[uuid.UUID, uuid.UUID]:
    uid = uuid.uuid4()
    session.add(User(id=uid, username=f"u_{uid.hex[:8]}", password_hash="h", is_admin=False))
    cid = uuid.uuid4()
    session.add(
        GoogleWorkflowConnection(
            id=cid,
            user_id=uid,
            google_sub=f"sub_{cid.hex[:8]}",
            refresh_token_encrypted="encrypted-test-token",
            scopes="https://www.googleapis.com/auth/gmail.readonly",
        )
    )
    session.commit()
    return uid, cid


def test_returns_empty_dict_for_none_graph(db_session: Session):
    uid, cid = _add_user_and_connection(db_session)
    out = workflow_graph_with_default_google_connection(db_session, user_id=uid, graph=None, default_connection_id=cid)
    assert out == {}


def test_no_injection_when_default_is_none(db_session: Session, graph_with_gmail_skill: dict):
    uid, _ = _add_user_and_connection(db_session)
    original = copy.deepcopy(graph_with_gmail_skill)
    out = workflow_graph_with_default_google_connection(
        db_session, user_id=uid, graph=graph_with_gmail_skill, default_connection_id=None
    )
    assert out == original


def test_no_injection_when_connection_wrong_user(db_session: Session, graph_with_gmail_skill: dict):
    owner_uid, cid = _add_user_and_connection(db_session)
    other = uuid.uuid4()
    db_session.add(User(id=other, username=f"other_{other.hex[:8]}", password_hash="h", is_admin=False))
    db_session.commit()
    out = workflow_graph_with_default_google_connection(
        db_session, user_id=other, graph=graph_with_gmail_skill, default_connection_id=cid
    )
    assert "google_connection_id" not in (out["nodes"][0].get("data") or {})


def test_replaces_other_users_connection_id_when_default_owned_by_runner(
    db_session: Session, graph_with_gmail_skill: dict
):
    owner_uid, cid_owner = _add_user_and_connection(db_session)
    other_uid = uuid.uuid4()
    db_session.add(User(id=other_uid, username=f"other_g_{other_uid.hex[:8]}", password_hash="h", is_admin=False))
    cid_other = uuid.uuid4()
    db_session.add(
        GoogleWorkflowConnection(
            id=cid_other,
            user_id=other_uid,
            google_sub="sub_other",
            refresh_token_encrypted="encrypted-other",
            scopes="https://www.googleapis.com/auth/gmail.readonly",
        )
    )
    db_session.commit()
    graph_with_gmail_skill["nodes"][0]["data"]["google_connection_id"] = str(cid_other)
    out = workflow_graph_with_default_google_connection(
        db_session, user_id=owner_uid, graph=graph_with_gmail_skill, default_connection_id=cid_owner
    )
    assert out["nodes"][0]["data"]["google_connection_id"] == str(cid_owner)


def test_injects_when_skill_type_only_on_node(db_session: Session):
    uid, cid = _add_user_and_connection(db_session)
    graph = {
        "nodes": [
            {"id": "g1", "kind": "skill", "skill_type": "gmail_list_messages", "data": {}},
        ]
    }
    out = workflow_graph_with_default_google_connection(db_session, user_id=uid, graph=graph, default_connection_id=cid)
    assert out["nodes"][0]["data"]["google_connection_id"] == str(cid)


def test_injects_for_owned_connection(db_session: Session, graph_with_gmail_skill: dict):
    uid, cid = _add_user_and_connection(db_session)
    out = workflow_graph_with_default_google_connection(
        db_session, user_id=uid, graph=graph_with_gmail_skill, default_connection_id=cid
    )
    assert out["nodes"][0]["data"]["google_connection_id"] == str(cid)
    assert out["nodes"][1]["data"]["google_connection_id"] == str(cid)


def test_injects_when_google_connection_id_is_whitespace_only(db_session: Session, graph_with_gmail_skill: dict):
    uid, cid = _add_user_and_connection(db_session)
    graph_with_gmail_skill["nodes"][0]["data"]["google_connection_id"] = "   \t"
    out = workflow_graph_with_default_google_connection(
        db_session, user_id=uid, graph=graph_with_gmail_skill, default_connection_id=cid
    )
    assert out["nodes"][0]["data"]["google_connection_id"] == str(cid)


def test_preserves_valid_owned_google_connection_id(db_session: Session, graph_with_gmail_skill: dict):
    uid, cid_default = _add_user_and_connection(db_session)
    cid_owned = uuid.uuid4()
    db_session.add(
        GoogleWorkflowConnection(
            id=cid_owned,
            user_id=uid,
            google_sub=f"sub_owned_{cid_owned.hex[:8]}",
            refresh_token_encrypted="encrypted-test-token-2",
            scopes="https://www.googleapis.com/auth/gmail.readonly",
        )
    )
    db_session.commit()
    graph_with_gmail_skill["nodes"][0]["data"]["google_connection_id"] = str(cid_owned)
    out = workflow_graph_with_default_google_connection(
        db_session, user_id=uid, graph=graph_with_gmail_skill, default_connection_id=cid_default
    )
    assert out["nodes"][0]["data"]["google_connection_id"] == str(cid_owned)
    assert out["nodes"][1]["data"]["google_connection_id"] == str(cid_default)


def test_replaces_invalid_google_connection_id_with_workspace_default(
    db_session: Session, graph_with_gmail_skill: dict
):
    uid, cid = _add_user_and_connection(db_session)
    stale = str(uuid.uuid4())
    graph_with_gmail_skill["nodes"][0]["data"]["google_connection_id"] = stale
    out = workflow_graph_with_default_google_connection(
        db_session, user_id=uid, graph=graph_with_gmail_skill, default_connection_id=cid
    )
    assert out["nodes"][0]["data"]["google_connection_id"] == str(cid)
    assert out["nodes"][1]["data"]["google_connection_id"] == str(cid)


def test_unknown_connection_id_no_injection(db_session: Session, graph_with_gmail_skill: dict):
    uid, _ = _add_user_and_connection(db_session)
    fake_cid = uuid.uuid4()
    out = workflow_graph_with_default_google_connection(
        db_session, user_id=uid, graph=graph_with_gmail_skill, default_connection_id=fake_cid
    )
    for n in out["nodes"]:
        assert "google_connection_id" not in (n.get("data") or {})


def test_non_google_skill_unchanged(db_session: Session):
    uid, cid = _add_user_and_connection(db_session)
    graph = {
        "nodes": [
            {"id": "x", "kind": "skill", "data": {"skill_type": "other_skill"}},
        ]
    }
    out = workflow_graph_with_default_google_connection(db_session, user_id=uid, graph=graph, default_connection_id=cid)
    assert "google_connection_id" not in (out["nodes"][0].get("data") or {})


def test_deep_copy_does_not_mutate_original(db_session: Session, graph_with_gmail_skill: dict):
    uid, cid = _add_user_and_connection(db_session)
    original = copy.deepcopy(graph_with_gmail_skill)
    workflow_graph_with_default_google_connection(
        db_session, user_id=uid, graph=graph_with_gmail_skill, default_connection_id=cid
    )
    assert graph_with_gmail_skill == original


def test_nodes_not_list_returns_graph_unchanged_for_injection(db_session: Session):
    uid, cid = _add_user_and_connection(db_session)
    graph = {"nodes": {"not": "a-list"}}
    out = workflow_graph_with_default_google_connection(db_session, user_id=uid, graph=graph, default_connection_id=cid)
    assert out["nodes"] == {"not": "a-list"}


def test_skips_non_dict_nodes(db_session: Session):
    uid, cid = _add_user_and_connection(db_session)
    graph = {"nodes": ["bad", {"kind": "skill", "data": {"skill_type": "gmail_list_messages"}}]}
    out = workflow_graph_with_default_google_connection(db_session, user_id=uid, graph=graph, default_connection_id=cid)
    assert out["nodes"][1]["data"]["google_connection_id"] == str(cid)


def test_skill_node_skill_type_reads_camelCase_aliases():
    n = {"kind": "skill", "data": {"skillType": "gmail_list_messages"}}
    assert skill_node_skill_type(n) == "gmail_list_messages"
    n2 = {"kind": "skill", "skillType": "calendar_list_events", "data": {}}
    assert skill_node_skill_type(n2) == "calendar_list_events"


def test_normalizes_camelCase_and_injects_google_connection_id(db_session: Session):
    uid, cid = _add_user_and_connection(db_session)
    graph = {
        "nodes": [
            {
                "id": "g1",
                "kind": "skill",
                "data": {"skillType": "gmail_list_messages", "googleConnectionId": str(cid)},
            },
        ]
    }
    out = workflow_graph_with_default_google_connection(db_session, user_id=uid, graph=graph, default_connection_id=cid)
    assert out["nodes"][0]["data"]["skill_type"] == "gmail_list_messages"
    assert out["nodes"][0]["data"]["google_connection_id"] == str(cid)


def test_normalizes_inplace_copies_blank_snake_when_camel_present():
    g = {
        "nodes": [
            {
                "kind": "skill",
                "data": {
                    "skill_type": "gmail_list_messages",
                    "google_connection_id": "  ",
                    "googleConnectionId": "550e8400-e29b-41d4-a716-446655440000",
                },
            },
        ]
    }
    normalize_workflow_graph_skill_aliases_inplace(g)
    assert g["nodes"][0]["data"]["google_connection_id"] == "550e8400-e29b-41d4-a716-446655440000"


def test_normalizes_non_dict_skill_data(db_session: Session):
    uid, cid = _add_user_and_connection(db_session)
    graph = {"nodes": [{"id": "g1", "kind": "skill", "data": None}]}
    out = workflow_graph_with_default_google_connection(db_session, user_id=uid, graph=graph, default_connection_id=cid)
    assert out["nodes"][0]["data"] == {}
