"""GET /api/v1/me/workflow-runs and DELETE workflow run."""

import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.persistence.tables import NodeRunLog, User, WorkflowDefinition, WorkflowRun
from tests.conftest import engine


def test_me_workflow_runs_lists_only_owner_started_runs(client: TestClient):
    wf_id = uuid.uuid4()
    run_id = uuid.uuid4()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == "testuser")).first()
        assert user is not None
        session.add(
            WorkflowDefinition(
                id=wf_id,
                user_id=user.id,
                name="WF explore",
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
        session.commit()

    response = client.get("/api/v1/me/workflow-runs")
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 1
    assert any(r["id"] == str(run_id) and r["workflow_name"] == "WF explore" for r in body)


def test_delete_workflow_run_removes_logs(client: TestClient):
    wf_id = uuid.uuid4()
    run_id = uuid.uuid4()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == "testuser")).first()
        assert user is not None
        session.add(
            WorkflowDefinition(
                id=wf_id,
                user_id=user.id,
                name="WF delete",
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
        session.commit()

    with Session(engine) as session:
        session.add(
            NodeRunLog(
                run_id=run_id,
                node_id="n1",
                status="ok",
                output_data={"text": "x"},
            )
        )
        session.commit()

    response = client.delete(f"/api/v1/workflow-definitions/{wf_id}/runs/{run_id}")
    assert response.status_code == 204

    with Session(engine) as session:
        assert session.get(WorkflowRun, run_id) is None
        logs = session.exec(select(NodeRunLog).where(NodeRunLog.run_id == run_id)).all()
        assert len(logs) == 0


def test_delete_workflow_run_404_other_starter(client: TestClient):
    wf_id = uuid.uuid4()
    run_id = uuid.uuid4()
    with Session(engine) as session:
        owner = session.exec(select(User).where(User.username == "testuser")).first()
        assert owner is not None
        other = User(
            id=uuid.uuid4(),
            username="other_runner",
            password_hash="fakehash",
            is_admin=False,
        )
        session.add(other)
        session.add(
            WorkflowDefinition(
                id=wf_id,
                user_id=owner.id,
                name="WF other",
                graph={"nodes": [], "edges": []},
            )
        )
        session.add(
            WorkflowRun(
                id=run_id,
                workflow_id=wf_id,
                started_by_user_id=other.id,
                status="ok",
            )
        )
        session.commit()

    response = client.delete(f"/api/v1/workflow-definitions/{wf_id}/runs/{run_id}")
    assert response.status_code == 404
