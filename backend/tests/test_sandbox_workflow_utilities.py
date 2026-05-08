"""Workflow executor coverage for sandbox_* utility nodes (no LLM)."""

from fastapi.testclient import TestClient

from app.domain.sandbox.engine import initial_sandbox_state_clean
from app.domain.schemas.sandbox import GridCell, SandboxItem, SandboxTickInput


def _tick_dict():
    st = initial_sandbox_state_clean()
    return SandboxTickInput(tick=1, pet=st.pet, world=st.world, recent_actions=[]).model_dump(mode="json")


def test_sandbox_available_cells_excludes_pet_and_items(client: TestClient):
    """List output length matches empty cells; occupied coordinates are absent."""
    d_id = "n_dict"
    u_id = "n_avail"
    stop_id = "n_stop"
    tick = {
        "tick": 1,
        "pet": {
            "hunger": 50,
            "energy": 50,
            "mood": 50,
            "position": {"x": 0, "y": 0},
            "intent": None,
        },
        "world": {
            "grid": {"width": 2, "height": 2},
            "items": [{"id": "i1", "type": "food", "position": {"x": 1, "y": 1}}],
        },
        "recent_actions": [],
    }
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox available cells",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_available_cells",
                        "label": "available",
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "list"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "input"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["kind"] == "list"
    cells = u_res["output"]["data"]
    assert len(cells) == 2
    pairs = {(c["x"], c["y"]) for c in cells}
    assert pairs == {(1, 0), (0, 1)}
    assert (0, 0) not in pairs and (1, 1) not in pairs
    assert u_res.get("details", {}).get("resolved_inputs", {}).get("cell_count") == 2


def test_sandbox_tick_items_then_len(client: TestClient):
    d_id = "n_dict"
    u_id = "n_tick_items"
    len_id = "n_len"
    stop_id = "n_stop"
    tick = _tick_dict()
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox tick items",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_tick_items",
                        "label": "items",
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": len_id,
                        "kind": "utility",
                        "utility_type": "len_from_list",
                        "label": "len",
                        "data": {},
                        "position": {"x": 400, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 600, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "input"},
                    {"source": u_id, "target": len_id, "source_handle": "output", "target_handle": "list"},
                    {"source": len_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["kind"] == "list"
    assert len(u_res["output"]["data"]) == len(tick["world"]["items"])
    assert u_res.get("details", {}).get("resolved_inputs", {}).get("item_type") == "all"


def test_sandbox_tick_items_item_type_food_matches_all_when_only_food(client: TestClient):
    d_id = "n_dict"
    u_id = "n_tick_items"
    stop_id = "n_stop"
    tick = _tick_dict()
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox tick items food filter",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_tick_items",
                        "label": "items",
                        "data": {"item_type": "food"},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "list"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "input"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["kind"] == "list"
    assert len(u_res["output"]["data"]) == len(tick["world"]["items"])
    assert u_res.get("details", {}).get("resolved_inputs", {}).get("item_type") == "food"


def test_sandbox_tick_items_invalid_item_type_errors(client: TestClient):
    d_id = "n_dict"
    u_id = "n_tick_items"
    stop_id = "n_stop"
    tick = _tick_dict()
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox tick items bad type",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_tick_items",
                        "label": "items",
                        "data": {"item_type": "widget"},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "list"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "input"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] in ("partial", "error")
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["status"] == "error"
    assert "unsupported item type" in (u_res.get("error") or "")
    ri = u_res.get("details", {}).get("resolved_inputs") or {}
    assert "sandbox_tick" in ri
    assert ri.get("item_type") == "widget"


def test_sandbox_decision_intent_error_includes_resolved_inputs(client: TestClient):
    """Failed steps attach details.resolved_inputs so Run Logs can show Inputs alongside the error."""
    u_id = "n_dec_err"
    stop_id = "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox decision intent invalid combo",
            "graph": {
                "nodes": [
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_decision_intent",
                        "label": "dec",
                        "data": {
                            "required_inputs": [
                                {"key": "action", "type": "string", "value": "wander"},
                                {"key": "target_item_id", "type": "string", "value": "food-1"},
                                {"key": "target_cell", "type": "dictionary", "value": None},
                                {"key": "reason", "type": "string", "value": None},
                            ]
                        },
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] in ("partial", "error")
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["status"] == "error"
    assert "wander" in (u_res.get("error") or "")
    ri = u_res.get("details", {}).get("resolved_inputs") or {}
    assert ri.get("action") == "wander"
    assert ri.get("target_item_id") == "food-1"


def test_sandbox_filter_items_by_type(client: TestClient):
    d_id = "n_dict"
    u_id = "n_filt"
    len_id = "n_len"
    stop_id = "n_stop"
    items = [
        {"id": "a", "type": "food", "position": {"x": 0, "y": 0}},
        {"id": "b", "type": "food", "position": {"x": 1, "y": 1}},
    ]
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox filter",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "items",
                        "data": items,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_filter_items_by_type",
                        "label": "filter",
                        "data": {
                            "required_inputs": [
                                {"key": "items", "type": "list", "value": None},
                                {"key": "item_type", "type": "string", "value": "food"},
                            ]
                        },
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": len_id,
                        "kind": "utility",
                        "utility_type": "len_from_list",
                        "label": "len",
                        "data": {},
                        "position": {"x": 400, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 600, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "items"},
                    {"source": u_id, "target": len_id, "source_handle": "output", "target_handle": "list"},
                    {"source": len_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["kind"] == "list"
    assert len(u_res["output"]["data"]) == 2


def test_sandbox_decision_intent_dictionary(client: TestClient):
    u_id = "n_dec"
    stop_id = "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox decision intent",
            "graph": {
                "nodes": [
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_decision_intent",
                        "label": "dec",
                        "data": {
                            "required_inputs": [
                                {"key": "action", "type": "string", "value": "wander"},
                                {"key": "target_item_id", "type": "string", "value": None},
                                {"key": "target_cell", "type": "dictionary", "value": None},
                                {"key": "reason", "type": "string", "value": "test"},
                            ]
                        },
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["kind"] == "dictionary"
    assert u_res["output"]["data"]["action"] == "wander"
    assert u_res["output"]["data"]["reason"] == "test"


def test_sandbox_starter_decision_matches_starter_policy(client: TestClient):
    d_id = "n_dict"
    u_id = "n_starter"
    stop_id = "n_stop"
    tick = _tick_dict()
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox starter decision",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_starter_decision",
                        "label": "brain",
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "input"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["data"]["action"] == "wander"


def test_sandbox_pet_hunger(client: TestClient):
    d_id = "n_dict"
    u_id = "n_h"
    stop_id = "n_stop"
    tick = _tick_dict()
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox pet hunger",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_pet_hunger",
                        "label": "hunger",
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "input"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["kind"] == "int"
    assert u_res["output"]["value"] == tick["pet"]["hunger"]


def test_sandbox_pet_cell(client: TestClient):
    d_id = "n_dict"
    u_id = "n_cell"
    stop_id = "n_stop"
    tick = _tick_dict()
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox pet cell",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_pet_cell",
                        "label": "cell",
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "input"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["kind"] == "dictionary"
    assert u_res["output"]["data"] == tick["pet"]["position"]


def test_sandbox_is_nearby8_adjacent(client: TestClient):
    a_id = "n_a"
    b_id = "n_b"
    u_id = "n_near"
    stop_id = "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox is nearby8",
            "graph": {
                "nodes": [
                    {
                        "id": a_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "a",
                        "data": {"x": 1, "y": 1},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": b_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "b",
                        "data": {"x": 1, "y": 0},
                        "position": {"x": 0, "y": 80},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_is_nearby8",
                        "label": "near",
                        "data": {
                            "required_inputs": [
                                {"key": "cell_a", "type": "dictionary", "value": None},
                                {"key": "cell_b", "type": "dictionary", "value": None},
                            ]
                        },
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "boolean"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": a_id, "target": u_id, "source_handle": "output", "target_handle": "cell_a"},
                    {"source": b_id, "target": u_id, "source_handle": "output", "target_handle": "cell_b"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["kind"] == "boolean"
    assert u_res["output"]["value"] is True


def test_sandbox_is_nearby8_implicit_target_handle_null_second_wire_to_cell_b(client: TestClient):
    """Persisted edges may omit target_handle; second data wire must still bind to cell_b."""
    a_id = "n_a"
    b_id = "n_b"
    u_id = "n_near"
    stop_id = "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox is nearby8 null handle cell_b",
            "graph": {
                "nodes": [
                    {
                        "id": a_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "a",
                        "data": {"x": 1, "y": 1},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": b_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "b",
                        "data": {"x": 1, "y": 0},
                        "position": {"x": 0, "y": 80},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_is_nearby8",
                        "label": "near",
                        "data": {
                            "required_inputs": [
                                {"key": "cell_a", "type": "dictionary", "value": None},
                                {"key": "cell_b", "type": "dictionary", "value": None},
                            ]
                        },
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "boolean"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": a_id, "target": u_id, "source_handle": "output", "target_handle": "cell_a"},
                    {"source": b_id, "target": u_id, "source_handle": "output", "target_handle": None},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["kind"] == "boolean"
    assert u_res["output"]["value"] is True


def test_sandbox_first_nearby_food(client: TestClient):
    d_id = "n_dict"
    u_id = "n_food"
    len_id = "n_len"
    stop_id = "n_stop"
    st = initial_sandbox_state_clean()
    px, py = st.pet.position.x, st.pet.position.y
    tick = SandboxTickInput(
        tick=1,
        pet=st.pet,
        world=st.world.model_copy(
            update={
                "items": [
                    SandboxItem(id="f1", type="food", position=GridCell(x=px, y=py - 1)),
                ],
            }
        ),
        recent_actions=[],
    ).model_dump(mode="json")
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox first nearby food",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_first_nearby_food",
                        "label": "food",
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": len_id,
                        "kind": "utility",
                        "utility_type": "len_from_list",
                        "label": "len",
                        "data": {},
                        "position": {"x": 400, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 600, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "input"},
                    {"source": u_id, "target": len_id, "source_handle": "output", "target_handle": "list"},
                    {"source": len_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["kind"] == "list"
    assert len(u_res["output"]["data"]) == 1
    assert u_res["output"]["data"][0]["id"] == "f1"


def test_sandbox_first_food_world_order(client: TestClient):
    d_id = "n_dict"
    u_id = "n_seek"
    len_id = "n_len"
    stop_id = "n_stop"
    st = initial_sandbox_state_clean()
    tick = SandboxTickInput(
        tick=1,
        pet=st.pet,
        world=st.world.model_copy(
            update={
                "items": [
                    SandboxItem(id="a", type="food", position=GridCell(x=0, y=0)),
                    SandboxItem(id="b", type="food", position=GridCell(x=1, y=1)),
                ],
            }
        ),
        recent_actions=[],
    ).model_dump(mode="json")
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox first food world order",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_first_food_world_order",
                        "label": "seek",
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": len_id,
                        "kind": "utility",
                        "utility_type": "len_from_list",
                        "label": "len",
                        "data": {},
                        "position": {"x": 400, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 600, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "input"},
                    {"source": u_id, "target": len_id, "source_handle": "output", "target_handle": "list"},
                    {"source": len_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["kind"] == "list"
    assert len(u_res["output"]["data"]) == 1
    assert u_res["output"]["data"][0]["id"] == "a"


def test_sandbox_world_grid(client: TestClient):
    d_id = "n_dict"
    u_id = "n_grid"
    stop_id = "n_stop"
    tick = _tick_dict()
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox world grid",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_world_grid",
                        "label": "grid",
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "input"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["data"]["width"] == tick["world"]["grid"]["width"]
    assert u_res["output"]["data"]["height"] == tick["world"]["grid"]["height"]


def test_sandbox_tick_pet(client: TestClient):
    d_id = "n_dict"
    u_id = "n_pet"
    stop_id = "n_stop"
    tick = _tick_dict()
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox tick pet",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_tick_pet",
                        "label": "pet",
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "input"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["data"]["hunger"] == tick["pet"]["hunger"]


def test_sandbox_nearest_item_by_type(client: TestClient):
    d_id = "n_dict"
    s_id = "n_str"
    u_id = "n_near"
    stop_id = "n_stop"
    st = initial_sandbox_state_clean()
    tick = SandboxTickInput(
        tick=1,
        pet=st.pet,
        world=st.world.model_copy(
            update={
                "items": [
                    SandboxItem(id="far", type="food", position=GridCell(x=7, y=7)),
                    SandboxItem(id="win", type="food", position=GridCell(x=st.pet.position.x + 1, y=st.pet.position.y)),
                ],
            }
        ),
        recent_actions=[],
    ).model_dump(mode="json")
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox nearest item",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": s_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "type",
                        "data": {"text": "food"},
                        "position": {"x": 0, "y": 80},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_nearest_item_by_type",
                        "label": "nearest",
                        "data": {
                            "required_inputs": [
                                {"key": "sandbox_tick", "type": "dictionary", "value": None},
                                {"key": "item_type", "type": "string", "value": "food"},
                            ]
                        },
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "sandbox_tick"},
                    {"source": s_id, "target": u_id, "source_handle": "output", "target_handle": "item_type"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["data"]["id"] == "win"


def test_sandbox_closest_item_returns_nearest_as_dictionary(client: TestClient):
    d_id = "n_dict"
    s_id = "n_str"
    u_id = "n_close"
    stop_id = "n_stop"
    st = initial_sandbox_state_clean()
    tick = SandboxTickInput(
        tick=1,
        pet=st.pet,
        world=st.world.model_copy(
            update={
                "items": [
                    SandboxItem(id="far", type="food", position=GridCell(x=7, y=7)),
                    SandboxItem(id="win", type="food", position=GridCell(x=st.pet.position.x + 1, y=st.pet.position.y)),
                ],
            }
        ),
        recent_actions=[],
    ).model_dump(mode="json")
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox closest item dict",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": s_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "type",
                        "data": {"text": "food"},
                        "position": {"x": 0, "y": 80},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_closest_item",
                        "label": "closest",
                        "data": {
                            "required_inputs": [
                                {"key": "sandbox_tick", "type": "dictionary", "value": None},
                                {"key": "item_type", "type": "string", "value": "food"},
                            ]
                        },
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "sandbox_tick"},
                    {"source": s_id, "target": u_id, "source_handle": "output", "target_handle": "item_type"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["data"]["id"] == "win"


def test_sandbox_closest_item_empty_object_when_no_items(client: TestClient):
    d_id = "n_dict"
    u_id = "n_close"
    stop_id = "n_stop"
    st = initial_sandbox_state_clean()
    tick = SandboxTickInput(
        tick=1,
        pet=st.pet,
        world=st.world.model_copy(update={"items": []}),
        recent_actions=[],
    ).model_dump(mode="json")
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox closest item empty",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_closest_item",
                        "label": "closest",
                        "data": {
                            "required_inputs": [
                                {"key": "sandbox_tick", "type": "dictionary", "value": None},
                                {"key": "item_type", "type": "string", "value": "food"},
                            ]
                        },
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "sandbox_tick"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["data"] == {}


def test_sandbox_decision_move_to(client: TestClient):
    cell_id = "n_cell"
    u_id = "n_mv"
    stop_id = "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox move to",
            "graph": {
                "nodes": [
                    {
                        "id": cell_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "cell",
                        "data": {"x": 3, "y": 4},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_decision_move_to",
                        "label": "mv",
                        "data": {
                            "required_inputs": [
                                {"key": "target_item_id", "type": "string", "value": None},
                                {"key": "target_cell", "type": "dictionary", "value": None},
                                {"key": "reason", "type": "string", "value": "go"},
                            ]
                        },
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": cell_id, "target": u_id, "source_handle": "output", "target_handle": "target_cell"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next((r for r in result["node_results"] if r["node_id"] == u_id), None)
    assert u_res is not None
    assert u_res["output"]["data"]["action"] == "move_to"
    assert u_res["output"]["data"]["target_cell"] == {"x": 3, "y": 4}
    assert u_res["output"]["data"]["reason"] == "go"
