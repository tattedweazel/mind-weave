"""WorkflowDefinition REST lifecycle, list runs, and async ``POST …/runs`` + SSE (no LLM)."""

import json
import time
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.sse_helpers import parse_sse
_MINIMAL_GRAPH = {
    "nodes": [
        {
            "id": "n_str",
            "kind": "primitive",
            "primitive_type": "string",
            "label": "S",
            "data": {"text": "stream-test"},
            "position": {"x": 0, "y": 0},
        },
        {
            "id": "n_stop",
            "kind": "stop",
            "label": "Stop",
            "data": {"required_outputs": [{"key": "output", "type": "string"}]},
            "position": {"x": 100, "y": 0},
        },
    ],
    "edges": [{"source": "n_str", "target": "n_stop"}],
}


def test_workflow_definitions_crud_run_runs_delete(client: TestClient):
    create = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Lifecycle API", "graph": _MINIMAL_GRAPH},
    )
    assert create.status_code == 201
    wf_id = create.json()["id"]

    listed = client.get("/api/v1/workflow-definitions/")
    assert listed.status_code == 200
    ids = {row["id"] for row in listed.json()}
    assert wf_id in ids

    got = client.get(f"/api/v1/workflow-definitions/{wf_id}")
    assert got.status_code == 200
    assert got.json()["name"] == "Lifecycle API"
    assert got.json()["graph"].get("schema_version") == 1

    renamed = client.put(
        f"/api/v1/workflow-definitions/{wf_id}",
        json={"name": "Renamed Lifecycle"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed Lifecycle"

    run = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run.status_code == 200
    assert run.json()["status"] == "ok"

    # Persisted runs come from POST …/runs + background execution.
    enq = client.post(f"/api/v1/workflow-definitions/{wf_id}/runs", json={})
    assert enq.status_code == 200
    run_id = enq.json()["run_id"]

    time.sleep(0.05)
    with client.stream(
        "GET",
        f"/api/v1/workflow-runs/{run_id}/events",
    ) as stream_resp:
        assert stream_resp.status_code == 200
        _ = b"".join(stream_resp.iter_bytes())

    runs = client.get(f"/api/v1/workflow-definitions/{wf_id}/runs")
    assert runs.status_code == 200
    run_rows = runs.json()
    assert len(run_rows) >= 1
    run_id = run_rows[0]["id"]

    logs = client.get(f"/api/v1/workflow-definitions/{wf_id}/runs/{run_id}/logs")
    assert logs.status_code == 200
    assert isinstance(logs.json(), list)

    deleted = client.delete(f"/api/v1/workflow-definitions/{wf_id}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/v1/workflow-definitions/{wf_id}")
    assert missing.status_code == 404


def test_workflow_run_rejects_unknown_input_override(client: TestClient):
    create = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Override guard", "graph": _MINIMAL_GRAPH},
    )
    assert create.status_code == 201
    wf_id = create.json()["id"]
    bad = client.post(
        f"/api/v1/workflow-definitions/{wf_id}/run",
        json={"input_overrides": {"not_a_valid_run_key": "x"}},
    )
    assert bad.status_code == 422
    assert "not allowed" in bad.json()["detail"].lower()


def test_workflow_enqueue_run_streams_sse_lifecycle(client: TestClient):
    create = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Stream API", "graph": _MINIMAL_GRAPH},
    )
    assert create.status_code == 201
    wf_id = create.json()["id"]

    enq = client.post(f"/api/v1/workflow-definitions/{wf_id}/runs", json={})
    assert enq.status_code == 200
    run_id = enq.json()["run_id"]

    time.sleep(0.05)
    with client.stream(
        "GET",
        f"/api/v1/workflow-runs/{run_id}/events",
    ) as response:
        assert response.status_code == 200
        raw = b"".join(response.iter_bytes())

    events = parse_sse(raw)
    kinds = [ev for ev, _ in events]
    assert "workflow.started" in kinds
    payload0 = next(pl for ev, pl in events if ev == "workflow.started")
    assert payload0.get("workflow_id") == str(wf_id)
    assert payload0.get("run_id") == run_id
    assert "workflow.completed" in kinds


def test_workflow_enqueue_run_setup_failure_streams_workflow_failed_event(client: TestClient):
    """Unhandled failures during DAG setup emit ``workflow.failed`` on SSE and persist ``failed``."""
    create = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Stream topo boom", "graph": _MINIMAL_GRAPH},
    )
    assert create.status_code == 201
    wf_id = create.json()["id"]

    with patch(
        "app.domain.workflow_executor.executor._topological_order",
        side_effect=RuntimeError("boom"),
    ):
        enq = client.post(f"/api/v1/workflow-definitions/{wf_id}/runs", json={})
        assert enq.status_code == 200
        run_id = enq.json()["run_id"]
        time.sleep(0.25)

    with client.stream(
        "GET",
        f"/api/v1/workflow-runs/{run_id}/events",
    ) as response:
        assert response.status_code == 200
        raw = b"".join(response.iter_bytes())

    events = parse_sse(raw)
    kinds = [ev for ev, _ in events]
    assert "workflow.started" in kinds
    assert any(ev == "workflow.failed" for ev in kinds)

    runs = client.get(f"/api/v1/workflow-definitions/{wf_id}/runs")
    assert runs.status_code == 200
    assert runs.json()[0]["status"] == "failed"


def test_workflow_update_coerces_invalid_project_id_to_shared(client: TestClient):
    """PUT with a non-existent project_id assigns the workflow to Shared (orphan / stale folder)."""
    create = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Coerce project id", "graph": _MINIMAL_GRAPH},
    )
    assert create.status_code == 201
    wf_id = create.json()["id"]
    bad_pid = str(uuid.uuid4())
    r = client.put(
        f"/api/v1/workflow-definitions/{wf_id}",
        json={"project_id": bad_pid},
    )
    assert r.status_code == 200
    projs = client.get("/api/v1/workflow-projects/")
    assert projs.status_code == 200
    shared = next(p for p in projs.json() if p["name"] == "Shared")
    assert r.json()["project_id"] == shared["id"]
    assert r.json()["project_id"] != bad_pid


def test_workflow_run_rejects_unknown_output_override_node(client: TestClient):
    create = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Output override guard", "graph": _MINIMAL_GRAPH},
    )
    assert create.status_code == 201
    wf_id = create.json()["id"]
    bad = client.post(
        f"/api/v1/workflow-definitions/{wf_id}/run",
        json={"output_overrides": {"unknown_node": "x"}},
    )
    assert bad.status_code == 422
    assert "unknown" in bad.json()["detail"].lower()


def test_workflow_run_applies_string_primitive_output_override(client: TestClient):
    create = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Output override run", "graph": _MINIMAL_GRAPH},
    )
    assert create.status_code == 201
    wf_id = create.json()["id"]
    run = client.post(
        f"/api/v1/workflow-definitions/{wf_id}/run",
        json={"output_overrides": {"n_str": "forced-text"}},
    )
    assert run.status_code == 200
    by_id = {r["node_id"]: r for r in run.json()["node_results"]}
    assert by_id["n_str"]["details"].get("forced_output") is True
    assert by_id["n_str"]["output"]["kind"] == "string"
    assert by_id["n_str"]["output"]["text"] == "forced-text"
