"""Nested workflow refs resolve the user's Google workflow connection."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session

from app.domain.services.workflow_executor import WorkflowExecutor
from app.persistence.tables import GoogleWorkflowConnection, User, WorkflowDefinition


def _inner_graph() -> dict:
    return {
        "nodes": [
            {
                "id": "ns",
                "kind": "start",
                "label": "S",
                "data": {"text": ""},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "ng",
                "kind": "skill",
                "skill_type": "gmail_list_messages",
                "label": "Gmail",
                "data": {},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "nst",
                "kind": "stop",
                "label": "Stop",
                "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                "position": {"x": 0, "y": 0},
            },
        ],
        "edges": [
            {"source": "ns", "target": "ng"},
            {"source": "ng", "target": "nst"},
        ],
    }


def _outer_graph(inner_id: uuid.UUID) -> dict:
    return {
        "nodes": [
            {
                "id": "os",
                "kind": "start",
                "label": "S",
                "data": {"text": ""},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "ow",
                "kind": "workflow",
                "label": "Inner",
                "data": {"workflow_id": str(inner_id)},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "osp",
                "kind": "stop",
                "label": "Stop",
                "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                "position": {"x": 0, "y": 0},
            },
        ],
        "edges": [
            {"source": "os", "target": "ow"},
            {"source": "ow", "target": "osp"},
        ],
    }


@pytest.mark.asyncio
async def test_nested_subworkflow_uses_user_google_connection_without_node_id(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"nest_{uid.hex[:8]}", password_hash="h", is_admin=False))
    cid = uuid.uuid4()
    db_session.add(
        GoogleWorkflowConnection(
            id=cid,
            user_id=uid,
            google_sub=f"sub_{cid.hex[:8]}",
            refresh_token_encrypted="x" * 32,
            scopes="https://www.googleapis.com/auth/gmail.readonly",
        )
    )
    inner_id = uuid.uuid4()
    outer_id = uuid.uuid4()
    inner = WorkflowDefinition(
        id=inner_id,
        user_id=uid,
        name="Inner Gmail WF",
        graph=_inner_graph(),
    )
    outer = WorkflowDefinition(
        id=outer_id,
        user_id=uid,
        name="Outer Wrapper",
        graph=_outer_graph(inner_id),
    )
    db_session.add(inner)
    db_session.add(outer)
    db_session.commit()

    token_mock = AsyncMock(return_value="access-token")
    gmail_mock = AsyncMock(return_value={"messages": []})
    monkeypatch.setattr(
        "app.integrations.google_workspace.ensure_workflow_google_access_token",
        token_mock,
    )
    monkeypatch.setattr(
        "app.integrations.google_workspace.gmail_list_messages",
        gmail_mock,
    )

    ex = WorkflowExecutor(db_session, uid)
    result = await ex.run(outer)

    token_mock.assert_awaited()
    assert token_mock.await_args.args[1] == cid
    assert result.status in ("ok", "partial", "error")
