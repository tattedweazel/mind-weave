"""Tests for built-in starter sandbox workflow seeding."""

import json
import uuid
from pathlib import Path

from sqlmodel import Session

from app.domain.sandbox.builtins import STARTER_SANDBOX_WORKFLOW_ID
from app.domain.sandbox.starter_workflow_seed import (
    STARTER_BUILTIN_SLUG,
    STARTER_SANDBOX_NAME,
    STARTER_SANDBOX_WORKFLOW_GRAPH,
    ensure_starter_sandbox_workflow,
    graphs_equivalent,
)
from app.persistence.tables import WorkflowDefinition

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
