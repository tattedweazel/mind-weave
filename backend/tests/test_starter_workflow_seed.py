"""Tests for built-in starter sandbox workflow seeding."""

import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.domain.sandbox.builtins import STARTER_SANDBOX_WORKFLOW_ID
from app.domain.sandbox.engine import initial_sandbox_state_clean
from app.domain.sandbox.starter_workflow_seed import (
    STARTER_BUILTIN_SLUG,
    STARTER_SANDBOX_NAME,
    STARTER_SANDBOX_WORKFLOW_GRAPH,
    ensure_starter_sandbox_workflow,
    graphs_equivalent,
)
from app.domain.schemas.sandbox import CreatureState, GridCell, SandboxItem, SandboxTickInput
from app.persistence.tables import User, WorkflowDefinition

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXPORT_GRAPH_PATH = _REPO_ROOT / "sandbox-behavior-imported.json"


def test_ensure_starter_sandbox_workflow_updates_stale_graph(db_session: Session):
    """When the starter row exists with an older graph shape, ensure re-syncs to canonical."""
    wf = db_session.get(WorkflowDefinition, STARTER_SANDBOX_WORKFLOW_ID)
    assert wf is not None
    wf.graph = {**STARTER_SANDBOX_WORKFLOW_GRAPH, "schema_version": 1}
    db_session.add(wf)
    db_session.commit()

    ensure_starter_sandbox_workflow(db_session)

    wf2 = db_session.get(WorkflowDefinition, STARTER_SANDBOX_WORKFLOW_ID)
    assert wf2 is not None
    assert graphs_equivalent(wf2.graph, STARTER_SANDBOX_WORKFLOW_GRAPH)
    assert "schema_version" not in (wf2.graph or {})


def test_ensure_starter_sandbox_workflow_replaces_slug_row_with_wrong_id(db_session: Session):
    """If the slug points at a non-canonical id, delete the orphan row and insert the canonical starter."""
    wf = db_session.get(WorkflowDefinition, STARTER_SANDBOX_WORKFLOW_ID)
    assert wf is not None
    db_session.delete(wf)
    db_session.commit()

    wrong_id = uuid.uuid4()
    db_session.add(
        WorkflowDefinition(
            id=wrong_id,
            user_id=None,
            name="wrong starter",
            description=None,
            palette_id=None,
            project_id=None,
            expose_as_custom_skill=False,
            is_system=True,
            builtin_slug=STARTER_BUILTIN_SLUG,
            graph=dict(STARTER_SANDBOX_WORKFLOW_GRAPH),
        )
    )
    db_session.commit()

    ensure_starter_sandbox_workflow(db_session)

    good = db_session.get(WorkflowDefinition, STARTER_SANDBOX_WORKFLOW_ID)
    assert good is not None
    assert good.name == STARTER_SANDBOX_NAME
    assert db_session.get(WorkflowDefinition, wrong_id) is None


def test_starter_sandbox_workflow_graph_matches_export_fixture():
    """Regression: built-in graph stays aligned with repo-root sandbox-behavior-imported.json."""
    assert _EXPORT_GRAPH_PATH.is_file(), f"missing {_EXPORT_GRAPH_PATH}"
    payload = json.loads(_EXPORT_GRAPH_PATH.read_text(encoding="utf-8"))
    export_graph = payload["definition"]["graph"]
    assert graphs_equivalent(STARTER_SANDBOX_WORKFLOW_GRAPH, export_graph)


def test_graphs_equivalent_semantic_normalization():
    """Coerces SQLite-style floats, skips bad edge entries, and treats non-dict graph as empty."""
    base = json.loads(json.dumps(STARTER_SANDBOX_WORKFLOW_GRAPH))
    base["nodes"][0]["position"]["x"] = 0.0
    base["nodes"][0]["position"]["y"] = 0.0
    assert graphs_equivalent(base, STARTER_SANDBOX_WORKFLOW_GRAPH)

    canonical_edges = STARTER_SANDBOX_WORKFLOW_GRAPH["edges"]
    noisy = json.loads(json.dumps(STARTER_SANDBOX_WORKFLOW_GRAPH))
    noisy["edges"] = [
        None,
        {"source": "sandbox_start"},
        *canonical_edges,
    ]
    assert graphs_equivalent(noisy, STARTER_SANDBOX_WORKFLOW_GRAPH)

    rev = json.loads(json.dumps(STARTER_SANDBOX_WORKFLOW_GRAPH))
    rev["edges"] = list(reversed(rev["edges"]))
    assert graphs_equivalent(rev, STARTER_SANDBOX_WORKFLOW_GRAPH)

    assert not graphs_equivalent("nope", STARTER_SANDBOX_WORKFLOW_GRAPH)  # type: ignore[arg-type]

    bad_nodes = json.loads(json.dumps(STARTER_SANDBOX_WORKFLOW_GRAPH))
    bad_nodes["nodes"] = "not-a-list"  # type: ignore[assignment]
    assert not graphs_equivalent(bad_nodes, STARTER_SANDBOX_WORKFLOW_GRAPH)

    bad_edges = json.loads(json.dumps(STARTER_SANDBOX_WORKFLOW_GRAPH))
    bad_edges["edges"] = "not-a-list"  # type: ignore[assignment]
    assert not graphs_equivalent(bad_edges, STARTER_SANDBOX_WORKFLOW_GRAPH)


def _tick_dict(*, x: int = 2, y: int = 2, facing: str = "N", items: list | None = None) -> dict:
    st = initial_sandbox_state_clean()
    st.world.grid.width = 8
    st.world.grid.height = 8
    c = CreatureState(
        id="c1",
        workflow_id=str(STARTER_SANDBOX_WORKFLOW_ID),
        position=GridCell(x=x, y=y),
        facing=facing,  # type: ignore[arg-type]
    )
    if items:
        for it in items:
            st.world.items.append(SandboxItem.model_validate(it))
    return SandboxTickInput(
        tick=1, creature=c, creatures=[c], world=st.world, recent_actions=[]
    ).model_dump(mode="json")


def test_starter_sandbox_workflow_runs_move_forward_on_empty_ahead(client: TestClient):
    """Open cell ahead → Is false branch → Move forward → Stop dictionary intent."""
    run = client.post(
        f"/api/v1/workflow-definitions/{STARTER_SANDBOX_WORKFLOW_ID}/run",
        json={"input_overrides": {"sandbox_tick": _tick_dict(x=4, y=4)}},
    )
    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "ok"
    stop = next(r for r in body["node_results"] if r["node_id"] == "stop")
    assert stop["status"] == "ok"
    assert stop["output"]["data"]["action"] == "move_forward"


def test_starter_sandbox_workflow_runs_turn_left_when_wall_ahead(client: TestClient):
    """Wall in forward cell → not empty → Turn left."""
    run = client.post(
        f"/api/v1/workflow-definitions/{STARTER_SANDBOX_WORKFLOW_ID}/run",
        json={
            "input_overrides": {
                "sandbox_tick": _tick_dict(
                    x=2,
                    y=2,
                    items=[{"id": "w1", "type": "wall", "position": {"x": 2, "y": 1}}],
                )
            }
        },
    )
    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "ok"
    stop = next(r for r in body["node_results"] if r["node_id"] == "stop")
    assert stop["output"]["data"]["action"] == "turn_left"


def test_starter_sandbox_workflow_runs_turn_left_when_out_of_bounds_ahead(client: TestClient):
    """Canvas edge ahead → out_of_bounds → not empty → Turn left."""
    run = client.post(
        f"/api/v1/workflow-definitions/{STARTER_SANDBOX_WORKFLOW_ID}/run",
        json={"input_overrides": {"sandbox_tick": _tick_dict(x=0, y=0, facing="N")}},
    )
    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "ok"
    stop = next(r for r in body["node_results"] if r["node_id"] == "stop")
    assert stop["output"]["data"]["action"] == "turn_left"


def test_starter_graph_has_no_basic_conditional_branch_node():
    node_ids = {n["id"] for n in STARTER_SANDBOX_WORKFLOW_GRAPH["nodes"]}
    assert "branch" not in node_ids


def test_system_workflow_get_visible_to_non_admin(client: TestClient):
    r = client.get(f"/api/v1/workflow-definitions/{STARTER_SANDBOX_WORKFLOW_ID}")
    assert r.status_code == 200
    assert r.json()["is_system"] is True


def test_system_workflow_update_forbidden_non_admin(client: TestClient):
    r = client.put(
        f"/api/v1/workflow-definitions/{STARTER_SANDBOX_WORKFLOW_ID}",
        json={"description": "attempted override"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "System workflows are read-only"


def test_system_workflow_update_allowed_admin(client: TestClient, db_session: Session):
    user = db_session.exec(select(User)).first()
    assert user is not None
    user.is_admin = True
    db_session.add(user)
    db_session.commit()

    new_desc = "admin patched starter description"
    r = client.put(
        f"/api/v1/workflow-definitions/{STARTER_SANDBOX_WORKFLOW_ID}",
        json={"description": new_desc},
    )
    assert r.status_code == 200
    assert r.json()["description"] == new_desc

    wf = db_session.get(WorkflowDefinition, STARTER_SANDBOX_WORKFLOW_ID)
    assert wf is not None
    assert wf.description == new_desc


def test_system_workflow_delete_still_forbidden_admin(client: TestClient, db_session: Session):
    user = db_session.exec(select(User)).first()
    assert user is not None
    user.is_admin = True
    db_session.add(user)
    db_session.commit()

    r = client.delete(f"/api/v1/workflow-definitions/{STARTER_SANDBOX_WORKFLOW_ID}")
    assert r.status_code == 404
    assert db_session.get(WorkflowDefinition, STARTER_SANDBOX_WORKFLOW_ID) is not None
