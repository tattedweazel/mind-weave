"""Workflow run logs API — prompt-like field redaction (SE-016)."""

import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.persistence.tables import NodeRunLog, User, WorkflowDefinition, WorkflowRun
from tests.conftest import engine


def test_get_run_logs_redacts_prompt_like_fields(client: TestClient):
    wf_id = uuid.uuid4()
    run_id = uuid.uuid4()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == "testuser")).first()
        session.add(
            WorkflowDefinition(
                id=wf_id,
                user_id=user.id,
                name="Log redaction test",
                graph={"nodes": [], "edges": []},
            )
        )
        session.add(
            WorkflowRun(
                id=run_id,
                workflow_id=wf_id,
                started_by_user_id=user.id,
                status="ok",
            )
        )
        session.add(
            NodeRunLog(
                run_id=run_id,
                node_id="n1",
                status="ok",
                output_data={"text": "visible"},
                details={
                    "user_prompt": "secret user text",
                    "system_prompt": "secret system",
                    "resolved_inputs": {
                        "user_prompt": "resolved secret user",
                        "system_prompt": "resolved secret system",
                        "user_role_message": "resolved secret user role",
                    },
                    "note": "kept",
                    "nested": {"inner_user_prompt": "nested secret"},
                },
                error='boom https://internal.example:1234/v1/secret "x"',
            )
        )
        session.commit()

    response = client.get(f"/api/v1/workflow-definitions/{wf_id}/runs/{run_id}/logs")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    row = body[0]
    assert row["output_data"]["text"] == "visible"
    assert row["details"]["user_prompt"] == "[redacted]"
    assert row["details"]["system_prompt"] == "[redacted]"
    assert row["details"]["resolved_inputs"]["user_prompt"] == "[redacted]"
    assert row["details"]["resolved_inputs"]["system_prompt"] == "[redacted]"
    assert row["details"]["resolved_inputs"]["user_role_message"] == "[redacted]"
    assert row["details"]["note"] == "kept"
    assert row["details"]["nested"]["inner_user_prompt"] == "[redacted]"
    assert "internal.example" not in row["error"]
    assert "[url]" in row["error"]


def test_get_run_logs_preserves_output_explorer_summary(client: TestClient):
    """Nested `summary` under output_explorer must not be redacted (unlike user content keys named summary)."""
    wf_id = uuid.uuid4()
    run_id = uuid.uuid4()
    output_explorer = {
        "version": 1,
        "kind": "string_primitive",
        "summary": {"line": "String output", "detail_lines": ["hello"]},
        "items": [],
    }
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == "testuser")).first()
        session.add(
            WorkflowDefinition(
                id=wf_id,
                user_id=user.id,
                name="Explorer preservation test",
                graph={"nodes": [], "edges": []},
            )
        )
        session.add(
            WorkflowRun(
                id=run_id,
                workflow_id=wf_id,
                started_by_user_id=user.id,
                status="ok",
            )
        )
        session.add(
            NodeRunLog(
                run_id=run_id,
                node_id="n1",
                status="ok",
                output_data={"kind": "string", "text": "hello"},
                details={
                    "user_prompt": "secret",
                    "output_explorer": output_explorer,
                },
            )
        )
        session.commit()

    response = client.get(f"/api/v1/workflow-definitions/{wf_id}/runs/{run_id}/logs")
    assert response.status_code == 200
    row = response.json()[0]
    assert row["details"]["user_prompt"] == "[redacted]"
    ex = row["details"]["output_explorer"]
    assert ex["version"] == 1
    assert isinstance(ex["summary"], dict)
    assert ex["summary"]["line"] == "String output"
    assert ex["summary"]["detail_lines"] == ["hello"]
    assert ex["items"] == []
