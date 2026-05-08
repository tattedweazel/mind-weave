"""Tests for strict Workspace interpret JSON Schema (per-capability input_bindings)."""

from __future__ import annotations

import uuid

import pytest
from sqlmodel import Session

from app.domain.workspace.capability_resolution import workflow_capability_key
from app.domain.workspace.interpret_json_schema import (
    _json_schema_property_for_start_slot,
    build_strict_candidate_capability_oneof_branches,
    interpret_json_schema_with_strict_candidate_bindings,
)
from app.domain.workspace.start_inputs import StartInputSlot
from app.persistence.tables import User, WorkflowDefinition


@pytest.fixture
def bind_user(db_session: Session) -> uuid.UUID:
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"i_{uid.hex[:8]}", password_hash="h", is_admin=False))
    db_session.commit()
    return uid


def _wf(uid: uuid.UUID, graph: dict) -> WorkflowDefinition:
    return WorkflowDefinition(
        id=uuid.uuid4(),
        user_id=uid,
        name="Test WF",
        graph=graph,
    )


def test_oneof_requires_gmail_like_start_keys(db_session: Session, bind_user: uuid.UUID):
    wf = _wf(
        bind_user,
        {
            "nodes": [
                {
                    "id": "st",
                    "kind": "start",
                    "label": "S",
                    "data": {
                        "required_inputs": [
                            {"key": "after", "type": "datetime", "value": None},
                            {"key": "before", "type": "datetime", "value": None},
                            {"key": "unread_only", "type": "boolean", "value": None},
                            {"key": "max_results", "type": "int", "value": None},
                        ]
                    },
                    "position": {},
                },
            ],
            "edges": [],
        },
    )
    db_session.add(wf)
    db_session.commit()
    key = workflow_capability_key(wf.id)
    branches = build_strict_candidate_capability_oneof_branches(db_session, bind_user, {key})
    assert branches is not None and len(branches) == 1
    ib = branches[0]["properties"]["input_bindings"]
    assert set(ib["required"]) == {"after", "before", "unread_only", "max_results"}
    assert ib["properties"]["after"]["type"] == "string"
    assert ib["properties"]["unread_only"]["type"] == "boolean"
    assert ib["properties"]["max_results"]["type"] == "integer"
    assert ib["additionalProperties"] is False


def test_static_default_slot_not_required(db_session: Session, bind_user: uuid.UUID):
    wf = _wf(
        bind_user,
        {
            "nodes": [
                {
                    "id": "st",
                    "kind": "start",
                    "label": "S",
                    "data": {
                        "required_inputs": [
                            {"key": "after", "type": "datetime", "value": None},
                            {"key": "before", "type": "string", "value": "2026-01-01T00:00:00Z"},
                        ]
                    },
                    "position": {},
                },
            ],
            "edges": [],
        },
    )
    db_session.add(wf)
    db_session.commit()
    key = workflow_capability_key(wf.id)
    branches = build_strict_candidate_capability_oneof_branches(db_session, bind_user, {key})
    assert branches is not None
    assert branches[0]["properties"]["input_bindings"]["required"] == ["after"]
    assert "before" in branches[0]["properties"]["input_bindings"]["properties"]


def test_over_max_branches_returns_none(db_session: Session, bind_user: uuid.UUID):
    wfs: list[WorkflowDefinition] = []
    for _ in range(3):
        w = _wf(
            bind_user,
            {
                "nodes": [
                    {
                        "id": "st",
                        "kind": "start",
                        "label": "S",
                        "data": {"text": ""},
                        "position": {},
                    },
                ],
                "edges": [],
            },
        )
        db_session.add(w)
        wfs.append(w)
    db_session.commit()
    keys = {workflow_capability_key(w.id) for w in wfs}
    assert build_strict_candidate_capability_oneof_branches(db_session, bind_user, keys, max_branches=2) is None


def test_interpret_schema_fallback_uses_ref_when_no_branches(db_session: Session, bind_user: uuid.UUID):
    schema = interpret_json_schema_with_strict_candidate_bindings(db_session, bind_user, set())
    items = schema["properties"]["candidate_capabilities"]["items"]
    assert "$ref" in items


def test_interpret_schema_oneof_when_two_workflows(db_session: Session, bind_user: uuid.UUID):
    wf1 = _wf(
        bind_user,
        {
            "nodes": [
                {
                    "id": "st",
                    "kind": "start",
                    "label": "S",
                    "data": {"required_inputs": [{"key": "q", "type": "string", "value": None}]},
                    "position": {},
                },
            ],
            "edges": [],
        },
    )
    wf2 = _wf(
        bind_user,
        {
            "nodes": [
                {
                    "id": "st",
                    "kind": "start",
                    "label": "S",
                    "data": {"required_inputs": [{"key": "x", "type": "int", "value": None}]},
                    "position": {},
                },
            ],
            "edges": [],
        },
    )
    db_session.add(wf1)
    db_session.add(wf2)
    db_session.commit()
    keys = {workflow_capability_key(wf1.id), workflow_capability_key(wf2.id)}
    schema = interpret_json_schema_with_strict_candidate_bindings(db_session, bind_user, keys)
    items = schema["properties"]["candidate_capabilities"]["items"]
    assert "oneOf" in items
    assert len(items["oneOf"]) == 2
    consts = {b["properties"]["capability_key"]["const"] for b in items["oneOf"]}
    assert consts == keys


def test_json_schema_property_for_start_slot_any_type():
    p = _json_schema_property_for_start_slot(
        StartInputSlot(key="a", input_type="any", has_static_default=False),
    )
    assert p["type"] == "object" and p.get("additionalProperties") is True
