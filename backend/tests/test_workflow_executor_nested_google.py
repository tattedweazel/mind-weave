"""Workspace default Google id is injected for nested workflow refs."""

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
                "label": "Gmail",
                "data": {"skill_type": "gmail_list_messages"},
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
async def test_nested_subworkflow_receives_workspace_google_injection(
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

    injection_calls: list[int] = []

    import app.domain.workflow_executor.executor as executor_mod

    real_inj = executor_mod.workflow_graph_with_default_google_connection

    def spy_inject(session, *, user_id, graph, default_connection_id):
        injection_calls.append(len((graph or {}).get("nodes") or []))
        return real_inj(session, user_id=user_id, graph=graph, default_connection_id=default_connection_id)

    monkeypatch.setattr(executor_mod, "workflow_graph_with_default_google_connection", spy_inject)

    monkeypatch.setattr(
        "app.integrations.google_workspace.ensure_workflow_google_access_token",
        AsyncMock(return_value="access-token"),
    )
    monkeypatch.setattr(
        "app.integrations.google_workspace.gmail_list_messages",
        AsyncMock(return_value={"messages": []}),
    )

    ex = WorkflowExecutor(db_session, uid, default_google_workflow_connection_id=cid)
    result = await ex.run(outer)

    assert len(injection_calls) >= 2
    assert any(n == 3 for n in injection_calls)
    assert result.status in ("ok", "partial", "error")
