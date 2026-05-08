"""Defaults applied before Workspace capability validation/execution."""

from __future__ import annotations

import uuid

import pytest
from sqlmodel import Session

from app.domain.services.workspace_runtime_service import (
    _apply_email_list_default_for_gmail_workflow,
    _graph_has_gmail_list_messages_deep,
)
from app.persistence.tables import User, WorkflowDefinition


@pytest.fixture
def scan_user_id(db_session: Session) -> uuid.UUID:
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"scan_{uid.hex[:8]}", password_hash="h", is_admin=False))
    db_session.commit()
    return uid


def test_graph_has_gmail_list_messages_deep_top_level(db_session: Session, scan_user_id: uuid.UUID):
    g = {
        "nodes": [
            {"id": "s", "kind": "start", "label": "S", "data": {"text": ""}, "position": {}},
            {"id": "g", "kind": "skill", "label": "G", "data": {"skill_type": "gmail_list_messages"}, "position": {}},
        ]
    }
    assert _graph_has_gmail_list_messages_deep(db_session, scan_user_id, g) is True
    assert _graph_has_gmail_list_messages_deep(db_session, scan_user_id, {"nodes": []}) is False


def test_graph_has_gmail_list_messages_deep_skillType_alias(db_session: Session, scan_user_id: uuid.UUID):
    g = {
        "nodes": [
            {
                "id": "g",
                "kind": "skill",
                "label": "G",
                "data": {"skillType": "gmail_list_messages"},
                "position": {},
            },
        ]
    }
    assert _graph_has_gmail_list_messages_deep(db_session, scan_user_id, g) is True


def test_graph_has_gmail_list_messages_deep_nested_workflow(db_session: Session, scan_user_id: uuid.UUID):
    inner_id = uuid.uuid4()
    inner = WorkflowDefinition(
        id=inner_id,
        user_id=scan_user_id,
        name="Inner Gmail",
        graph={
            "nodes": [
                {"id": "g", "kind": "skill", "data": {"skill_type": "gmail_list_messages"}},
            ],
            "edges": [],
        },
    )
    db_session.add(inner)
    db_session.commit()

    outer = {
        "nodes": [
            {
                "id": "w",
                "kind": "workflow",
                "label": "Run inner",
                "data": {"workflow_id": str(inner_id)},
                "position": {},
            },
        ],
        "edges": [],
    }
    assert _graph_has_gmail_list_messages_deep(db_session, scan_user_id, outer) is True


def test_apply_email_list_default_inserts_empty_list_when_gmail_and_slot_required(
    db_session: Session, scan_user_id: uuid.UUID
):
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {
                    "required_inputs": [
                        {"key": "email_list", "type": "list", "value": None},
                    ]
                },
                "position": {},
            },
            {"id": "g", "kind": "skill", "label": "G", "data": {"skill_type": "gmail_list_messages"}, "position": {}},
        ]
    }
    out = _apply_email_list_default_for_gmail_workflow(db_session, scan_user_id, graph, {"other": 1})
    assert out["email_list"] == []
    assert out["other"] == 1


def test_apply_email_list_default_for_gmail_typed_slot(db_session: Session, scan_user_id: uuid.UUID):
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {"required_inputs": [{"key": "email_list", "type": "gmail", "value": None}]},
                "position": {},
            },
            {"id": "g", "kind": "skill", "label": "G", "data": {"skill_type": "gmail_list_messages"}, "position": {}},
        ]
    }
    out = _apply_email_list_default_for_gmail_workflow(db_session, scan_user_id, graph, {})
    assert out["email_list"] == []


def test_apply_email_list_default_for_string_typed_slot(db_session: Session, scan_user_id: uuid.UUID):
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {"required_inputs": [{"key": "email_list", "type": "string", "value": None}]},
                "position": {},
            },
            {"id": "g", "kind": "skill", "label": "G", "data": {"skill_type": "gmail_list_messages"}, "position": {}},
        ]
    }
    out = _apply_email_list_default_for_gmail_workflow(db_session, scan_user_id, graph, {})
    assert out["email_list"] == []


def test_apply_email_list_default_for_any_type_slot(db_session: Session, scan_user_id: uuid.UUID):
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {"required_inputs": [{"key": "email_list", "type": "any", "value": None}]},
                "position": {},
            },
            {"id": "g", "kind": "skill", "label": "G", "data": {"skill_type": "gmail_list_messages"}, "position": {}},
        ]
    }
    out = _apply_email_list_default_for_gmail_workflow(db_session, scan_user_id, graph, {})
    assert out["email_list"] == []


def test_apply_email_list_default_nested_gmail_triggers(db_session: Session, scan_user_id: uuid.UUID):
    inner_id = uuid.uuid4()
    inner = WorkflowDefinition(
        id=inner_id,
        user_id=scan_user_id,
        name="Inner Gmail",
        graph={
            "nodes": [
                {"id": "g", "kind": "skill", "data": {"skill_type": "gmail_list_messages"}},
            ],
            "edges": [],
        },
    )
    db_session.add(inner)
    db_session.commit()

    outer_graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {"required_inputs": [{"key": "email_list", "type": "list", "value": None}]},
                "position": {},
            },
            {
                "id": "w",
                "kind": "workflow",
                "label": "W",
                "data": {"workflow_id": str(inner_id)},
                "position": {},
            },
        ],
        "edges": [],
    }
    out = _apply_email_list_default_for_gmail_workflow(db_session, scan_user_id, outer_graph, {})
    assert out["email_list"] == []


def test_apply_email_list_default_noop_without_gmail_skill(db_session: Session, scan_user_id: uuid.UUID):
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {"required_inputs": [{"key": "email_list", "type": "list", "value": None}]},
                "position": {},
            },
        ]
    }
    out = _apply_email_list_default_for_gmail_workflow(db_session, scan_user_id, graph, {})
    assert "email_list" not in out


def test_apply_email_list_default_respects_existing_binding(db_session: Session, scan_user_id: uuid.UUID):
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {"required_inputs": [{"key": "email_list", "type": "list", "value": None}]},
                "position": {},
            },
            {"id": "g", "kind": "skill", "label": "G", "data": {"skill_type": "gmail_list_messages"}, "position": {}},
        ]
    }
    out = _apply_email_list_default_for_gmail_workflow(db_session, scan_user_id, graph, {"email_list": ["a"]})
    assert out["email_list"] == ["a"]
