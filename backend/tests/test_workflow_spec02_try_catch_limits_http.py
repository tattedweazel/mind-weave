"""Spec 02: Try/Catch, execution limits overlays — HTTP executor tests (no real LLM / external APIs)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _try_catch_node(node_id: str, label: str = "Try / Catch") -> dict:
    return {
        "id": node_id,
        "kind": "control",
        "control_type": "try_catch",
        "label": label,
        "data": {},
        "position": {"x": 220, "y": 100},
    }


def _binary_int_utility_node(node_id: str, utility_type: str, input_a: int, input_b: int, label: str) -> dict:
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": utility_type,
        "label": label,
        "data": {
            "required_inputs": [
                {"key": "input_a", "type": "int", "value": input_a},
                {"key": "input_b", "type": "int", "value": input_b},
            ]
        },
        "position": {"x": 360, "y": 100},
    }


def test_get_workflow_execution_limits_endpoint(client: TestClient):
    res = client.get("/api/v1/workflow-execution-limits/")
    assert res.status_code == 200
    body = res.json()
    assert "defaults" in body and "ceilings" in body
    assert {"workflow_ttl_seconds", "max_node_executions", "max_loop_iterations", "max_nested_depth"} <= set(
        body["defaults"]
    )
    assert {"workflow_ttl_seconds", "max_loop_batch_size", "max_nested_depth"} <= set(body["ceilings"])


def test_post_run_execution_limits_above_ceiling_422(client: TestClient):
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Limits smoke",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [{"source": "n_start", "target": "n_stop"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]

    ceilings = client.get("/api/v1/workflow-execution-limits/").json()["ceilings"]
    bad_ttl = ceilings["workflow_ttl_seconds"] + 9999
    run_res = client.post(
        f"/api/v1/workflow-definitions/{wf_id}/run",
        json={"execution_limits": {"workflow_ttl_seconds": bad_ttl}},
    )
    assert run_res.status_code == 422
    assert "exceeds server maximum" in run_res.json()["detail"].lower()


def test_graph_execution_limits_caps_for_loop_iterations_error(client: TestClient):
    """Merged max_loop_iterations from graph.execution_limits must reject long lists."""
    start_id = "n_start"
    list_id = "n_list"
    fl_id = "n_fl"
    str_id = "n_str"
    stop_id = "n_stop"

    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Loop cap",
            "graph": {
                "execution_limits": {"max_loop_iterations": 2},
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": [1, 2, 3],
                        "position": {"x": 80, "y": 0},
                    },
                    {
                        "id": fl_id,
                        "kind": "control",
                        "control_type": "for_loop",
                        "label": "Loop",
                        "data": {"required_inputs": [{"key": "input", "type": "list", "value": None}]},
                        "position": {"x": 220, "y": 0},
                    },
                    {
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Echo",
                        "data": {"text": ""},
                        "position": {"x": 380, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 520, "y": 0},
                    },
                ],
                "edges": [
                    {"source": start_id, "target": list_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": list_id, "target": fl_id, "source_handle": "output", "target_handle": "input"},
                    {"source": list_id, "target": fl_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": fl_id, "target": str_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": fl_id, "target": str_id, "source_handle": "item", "target_handle": "input"},
                    {"source": str_id, "target": stop_id, "source_handle": "output"},
                    {"source": str_id, "target": stop_id, "source_handle": "signal_out", "target_handle": "trigger"},
                ],
            },
        },
    )
    assert wf.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{wf.json()['id']}/run")
    assert run_res.status_code == 200
    payload = run_res.json()
    assert payload["status"] == "partial"
    fl_step = next(r for r in payload["node_results"] if r["node_id"] == fl_id)
    assert fl_step["status"] == "error"
    assert "maximum iterations" in (fl_step.get("error") or "").lower()


def test_try_catch_missing_try_wire_422(client: TestClient):
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "TC bad",
            "graph": {
                "nodes": [
                    {"id": "n_start", "kind": "start", "label": "S", "data": {"required_inputs": []}, "position": {}},
                    _try_catch_node("n_tc"),
                    {"id": "n_stop", "kind": "stop", "label": "T", "data": {"required_outputs": [{"key": "o", "type": "string"}]}, "position": {}},
                ],
                "edges": [
                    {"source": "n_start", "target": "n_tc", "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": "n_tc", "target": "n_stop", "source_handle": "signal_out", "target_handle": "trigger"},
                ],
            },
        },
    )
    assert wf.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{wf.json()['id']}/run")
    assert run_res.status_code == 422
    assert "try" in run_res.json()["detail"].lower()


def test_try_catch_try_success_dictionary_envelope_ok(client: TestClient):
    start_id = "n_start"
    tc_id = "n_tc"
    add_id = "n_add"
    stop_id = "n_stop"

    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "TC OK",
            "graph": {
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 10, "y": 10},
                    },
                    _try_catch_node(tc_id),
                    _binary_int_utility_node(add_id, "add_ints", 40, 2, "Add"),
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "out", "type": "dictionary"}]},
                        "position": {"x": 700, "y": 10},
                    },
                ],
                "edges": [
                    {"source": start_id, "target": tc_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": tc_id, "target": add_id, "source_handle": "try", "target_handle": "trigger"},
                    {"source": add_id, "target": tc_id, "target_handle": "value"},
                    {"source": tc_id, "target": stop_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": tc_id, "target": stop_id, "source_handle": "output", "target_handle": "out"},
                ],
            },
        },
    )
    assert wf.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{wf.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    tc_r = next(r for r in result["node_results"] if r["node_id"] == tc_id)
    assert tc_r["status"] == "ok"
    blob = tc_r["output"]
    assert blob["kind"] == "dictionary"
    assert blob["data"]["ok"] is True
    assert blob["data"]["value"] == 42


def test_try_catch_catch_runs_when_try_fails_and_marks_inner_failure_handled(client: TestClient):
    start_id = "n_start"
    tc_id = "n_tc"
    div_id = "n_div"
    catch_str_id = "n_catch_s"
    stop_id = "n_stop"

    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "TC catch",
            "graph": {
                "nodes": [
                    {"id": start_id, "kind": "start", "label": "S", "data": {"required_inputs": []}, "position": {}},
                    _try_catch_node(tc_id),
                    _binary_int_utility_node(div_id, "divide_ints", 1, 0, "Div0"),
                    {
                        "id": catch_str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Catch echo",
                        "data": {"text": "recover"},
                        "position": {},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "T",
                        "data": {"required_outputs": [{"key": "out", "type": "string"}]},
                        "position": {},
                    },
                ],
                "edges": [
                    {"source": start_id, "target": tc_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": tc_id, "target": div_id, "source_handle": "try", "target_handle": "trigger"},
                    {"source": tc_id, "target": catch_str_id, "source_handle": "catch", "target_handle": "trigger"},
                    {"source": catch_str_id, "target": stop_id, "source_handle": "output", "target_handle": "out"},
                    {"source": catch_str_id, "target": stop_id, "source_handle": "signal_out", "target_handle": "trigger"},
                ],
            },
        },
    )
    assert wf.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{wf.json()['id']}/run")
    assert run_res.status_code == 200
    body = run_res.json()
    assert body["status"] == "partial"

    div_r = next(r for r in body["node_results"] if r["node_id"] == div_id)
    assert div_r["status"] == "error"
    assert div_r["details"].get("handled_by_try_catch") == tc_id

    tc_r = next(r for r in body["node_results"] if r["node_id"] == tc_id)
    assert tc_r["status"] == "ok"
    assert tc_r["output"]["data"]["ok"] is False
    assert "error" in tc_r["output"]["data"]

    stop_r = next(r for r in body["node_results"] if r["node_id"] == stop_id)
    assert stop_r["status"] == "ok"

    catch_steps = [r for r in body["node_results"] if r["node_id"] == catch_str_id]
    assert catch_steps and all(r["status"] == "ok" for r in catch_steps)
