"""Executor integration tests for document runtime utilities (no LLM / network)."""

import json
import uuid

from fastapi.testclient import TestClient


def _load_document_node(node_id: str, *, document_id: str | None = None, document_name: str | None = None):
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "load_document",
        "label": "Load Document",
        "data": {
            "required_inputs": [
                {"key": "document_id", "type": "string", "value": document_id},
                {"key": "document_name", "type": "string", "value": document_name},
            ],
        },
        "position": {"x": 200, "y": 100},
    }


def _upsert_document_node(
    node_id: str,
    *,
    name: str,
    content: str,
    write_mode: str = "replace",
    existing_document_id: str | None = None,
):
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "upsert_document",
        "label": "Upsert",
        "data": {
            "required_inputs": [
                {"key": "name", "type": "string", "value": name},
                {"key": "content", "type": "string", "value": content},
                {"key": "existing_document_id", "type": "string", "value": existing_document_id},
                {"key": "write_mode", "type": "string", "value": write_mode},
            ],
        },
        "position": {"x": 200, "y": 100},
    }


def _parse_document_body_node(node_id: str):
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "parse_document_body",
        "label": "Parse",
        "data": {
            "required_inputs": [
                {"key": "document", "type": "document", "value": None},
            ],
        },
        "position": {"x": 300, "y": 100},
    }


def _write_object_node(node_id: str):
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "write_object_to_document_body",
        "label": "Write",
        "data": {
            "required_inputs": [
                {"key": "value", "type": "any", "value": None},
            ],
        },
        "position": {"x": 200, "y": 100},
    }


def _append_value_node(node_id: str):
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "append_value_to_document",
        "label": "Append",
        "data": {
            "required_inputs": [
                {"key": "document", "type": "document", "value": None},
                {"key": "value", "type": "any", "value": None},
            ],
        },
        "position": {"x": 300, "y": 100},
    }


def _validate_structure_node(node_id: str, structure_id: str):
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "validate_against_structure",
        "label": "Validate",
        "data": {
            "structure_id": structure_id,
            "required_inputs": [
                {"key": "value", "type": "any", "value": {"x": "ok"}},
                {"key": "structure", "type": "structure", "value": None},
            ],
        },
        "position": {"x": 200, "y": 100},
    }


def _list_to_string_util_node(node_id: str):
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "list_to_string",
        "label": "List to String",
        "data": {},
        "position": {"x": 150, "y": 100},
    }


def test_upsert_document_wires_content_via_implicit_null_target_handle(client: TestClient):
    """list_to_string -> upsert with missing ``target_handle`` still persists body (regression #legacy export)."""
    list_id = "n_list_implicit"
    l2s_id = "n_l2s_implicit"
    up_id = "n_up_implicit"
    doc_name = f"iw_{uuid.uuid4().hex[:8]}"
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "upsert implicit content wire",
            "graph": {
                "nodes": [
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "L",
                        "data": ["alpha", "beta"],
                        "position": {"x": 50, "y": 100},
                    },
                    _list_to_string_util_node(l2s_id),
                    _upsert_document_node(up_id, name=doc_name, content=""),
                ],
                "edges": [
                    {"source": list_id, "target": l2s_id, "target_handle": "input"},
                    {"source": l2s_id, "target": up_id},
                ],
            },
        },
    )
    assert wf.status_code == 201
    run = client.post(f"/api/v1/workflow-definitions/{wf.json()['id']}/run")
    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "ok"
    step = next(r for r in body["node_results"] if r["node_id"] == up_id)
    assert step["status"] == "ok"
    markdown = step["output"]["markdown"]
    assert markdown
    assert "alpha" in markdown
    assert "beta" in markdown
    did = step["output"]["document_id"]
    get_doc = client.get(f"/api/v1/documents/{did}")
    assert get_doc.status_code == 200
    assert get_doc.json()["body"] == markdown


def test_upsert_document_recover_body_when_mis_saved_as_name_wire(client: TestClient):
    """Old editor default put body wires on ``target_handle: name``; explorer title + body still works."""
    src = "n_str_rec"
    up_id = "n_up_rec"
    doc_name = f"rec_{uuid.uuid4().hex[:8]}"
    body_text = "e" * 30
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "upsert recover miswired name handle",
            "graph": {
                "nodes": [
                    {
                        "id": src,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Body",
                        "data": {"text": body_text},
                        "position": {"x": 50, "y": 100},
                    },
                    {
                        "id": up_id,
                        "kind": "utility",
                        "utility_type": "upsert_document",
                        "label": "Save",
                        "data": {
                            "required_inputs": [
                                {"key": "name", "type": "string", "value": doc_name},
                                {"key": "content", "type": "string", "value": ""},
                            ],
                        },
                        "position": {"x": 250, "y": 100},
                    },
                ],
                "edges": [{"source": src, "target": up_id, "target_handle": "name"}],
            },
        },
    )
    assert wf.status_code == 201
    run = client.post(f"/api/v1/workflow-definitions/{wf.json()['id']}/run")
    assert run.status_code == 200
    payload = run.json()
    assert payload["status"] == "ok"
    step = next(r for r in payload["node_results"] if r["node_id"] == up_id)
    assert step["status"] == "ok"
    assert step["output"]["markdown"] == body_text
    assert step["output"]["name"] == doc_name
    did = step["output"]["document_id"]
    get_doc = client.get(f"/api/v1/documents/{did}")
    assert get_doc.status_code == 200
    assert get_doc.json()["name"] == doc_name
    assert get_doc.json()["body"] == body_text


def test_upsert_document_wires_body_via_target_handle_alias_output(client: TestClient):
    """Non-null wrong handle ``output`` maps to ``content`` at execute time."""
    src = "n_str_alias"
    up_id = "n_up_alias"
    doc_name = f"alias_{uuid.uuid4().hex[:8]}"
    body_text = "saved via output handle alias"
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "upsert target_handle alias output",
            "graph": {
                "nodes": [
                    {
                        "id": src,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Body",
                        "data": {"text": body_text},
                        "position": {"x": 50, "y": 100},
                    },
                    {
                        "id": up_id,
                        "kind": "utility",
                        "utility_type": "upsert_document",
                        "label": "Save",
                        "data": {
                            "required_inputs": [
                                {"key": "name", "type": "string", "value": doc_name},
                                {"key": "content", "type": "string", "value": ""},
                            ],
                        },
                        "position": {"x": 250, "y": 100},
                    },
                ],
                "edges": [{"source": src, "target": up_id, "target_handle": "output"}],
            },
        },
    )
    assert wf.status_code == 201
    run = client.post(f"/api/v1/workflow-definitions/{wf.json()['id']}/run")
    assert run.status_code == 200
    payload = run.json()
    assert payload["status"] == "ok"
    step = next(r for r in payload["node_results"] if r["node_id"] == up_id)
    assert step["status"] == "ok"
    assert step["output"]["markdown"] == body_text
    assert step["output"]["name"] == doc_name


def test_upsert_document_recover_short_body_miswired_to_name(client: TestClient):
    """Recovery no longer skips short transcripts on mis-saved ``name`` wire."""
    src = "n_str_short"
    up_id = "n_up_short"
    doc_name = f"short_{uuid.uuid4().hex[:8]}"
    body_text = "hi"
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "upsert recover short miswired name",
            "graph": {
                "nodes": [
                    {
                        "id": src,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Body",
                        "data": {"text": body_text},
                        "position": {"x": 50, "y": 100},
                    },
                    {
                        "id": up_id,
                        "kind": "utility",
                        "utility_type": "upsert_document",
                        "label": "Save",
                        "data": {
                            "required_inputs": [
                                {"key": "name", "type": "string", "value": doc_name},
                                {"key": "content", "type": "string", "value": ""},
                            ],
                        },
                        "position": {"x": 250, "y": 100},
                    },
                ],
                "edges": [{"source": src, "target": up_id, "target_handle": "name"}],
            },
        },
    )
    assert wf.status_code == 201
    run = client.post(f"/api/v1/workflow-definitions/{wf.json()['id']}/run")
    assert run.status_code == 200
    step = next(r for r in run.json()["node_results"] if r["node_id"] == up_id)
    assert step["status"] == "ok"
    assert step["output"]["markdown"] == body_text
    assert step["output"]["name"] == doc_name


def test_load_document_by_id(client: TestClient):
    doc_res = client.post(
        "/api/v1/documents/",
        json={"name": f"ld_{uuid.uuid4().hex[:8]}", "description": "", "body": "hello"},
    )
    assert doc_res.status_code == 201
    did = doc_res.json()["id"]
    util_id = "n_load"
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "load doc",
            "graph": {"nodes": [_load_document_node(util_id, document_id=did)], "edges": []},
        },
    )
    assert wf.status_code == 201
    run = client.post(f"/api/v1/workflow-definitions/{wf.json()['id']}/run")
    assert run.status_code == 200
    step = next(r for r in run.json()["node_results"] if r["node_id"] == util_id)
    assert step["status"] == "ok"
    assert step["output"]["kind"] == "document"
    assert step["output"]["markdown"] == "hello"


def test_upsert_merge_json_round_trip(client: TestClient):
    uid = "n_up"
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "upsert merge",
            "graph": {
                "nodes": [
                    _upsert_document_node(uid, name=f"mj_{uuid.uuid4().hex[:8]}", content="{}", write_mode="merge_json")
                ],
                "edges": [],
            },
        },
    )
    assert wf.status_code == 201
    run = client.post(f"/api/v1/workflow-definitions/{wf.json()['id']}/run")
    assert run.status_code == 200
    step = next(r for r in run.json()["node_results"] if r["node_id"] == uid)
    assert step["status"] == "ok"
    body = step["output"]["markdown"]
    assert json.loads(body) == {}


def test_parse_document_body_object(client: TestClient):
    prim = "n_doc"
    util = "n_parse"
    doc_res = client.post(
        "/api/v1/documents/",
        json={"name": f"parse_{uuid.uuid4().hex[:8]}", "description": "", "body": '{"a":1}'},
    )
    assert doc_res.status_code == 201
    did = doc_res.json()["id"]
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "parse body",
            "graph": {
                "nodes": [
                    {
                        "id": prim,
                        "kind": "primitive",
                        "primitive_type": "document",
                        "label": "D",
                        "data": {"document_id": did},
                        "position": {"x": 0, "y": 0},
                    },
                    _parse_document_body_node(util),
                ],
                "edges": [{"source": prim, "target": util, "target_handle": "document"}],
            },
        },
    )
    assert wf.status_code == 201
    run = client.post(f"/api/v1/workflow-definitions/{wf.json()['id']}/run")
    assert run.status_code == 200
    step = next(r for r in run.json()["node_results"] if r["node_id"] == util)
    assert step["status"] == "ok"
    assert step["output"]["kind"] == "dictionary"
    assert step["output"]["data"] == {"a": 1}


def test_write_object_to_document_body(client: TestClient):
    uid = "n_w"
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "write obj",
            "graph": {
                "nodes": [
                    {
                        "id": uid,
                        "kind": "utility",
                        "utility_type": "write_object_to_document_body",
                        "label": "W",
                        "data": {
                            "required_inputs": [
                                {"key": "value", "type": "any", "value": {"b": 2}},
                            ],
                        },
                        "position": {"x": 0, "y": 0},
                    },
                ],
                "edges": [],
            },
        },
    )
    assert wf.status_code == 201
    run = client.post(f"/api/v1/workflow-definitions/{wf.json()['id']}/run")
    assert run.status_code == 200
    step = next(r for r in run.json()["node_results"] if r["node_id"] == uid)
    assert step["status"] == "ok"
    assert step["output"]["kind"] == "string"
    assert json.loads(step["output"]["text"]) == {"b": 2}


def test_append_value_to_document(client: TestClient):
    prim = "n_doc"
    util = "n_app"
    doc_res = client.post(
        "/api/v1/documents/",
        json={"name": f"app_{uuid.uuid4().hex[:8]}", "description": "", "body": "base"},
    )
    assert doc_res.status_code == 201
    did = doc_res.json()["id"]
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "append",
            "graph": {
                "nodes": [
                    {
                        "id": prim,
                        "kind": "primitive",
                        "primitive_type": "document",
                        "label": "D",
                        "data": {"document_id": did},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": util,
                        "kind": "utility",
                        "utility_type": "append_value_to_document",
                        "label": "A",
                        "data": {
                            "required_inputs": [
                                {"key": "document", "type": "document", "value": None},
                                {"key": "value", "type": "any", "value": {"k": 1}},
                            ],
                        },
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [{"source": prim, "target": util, "target_handle": "document"}],
            },
        },
    )
    assert wf.status_code == 201
    run = client.post(f"/api/v1/workflow-definitions/{wf.json()['id']}/run")
    assert run.status_code == 200
    step = next(r for r in run.json()["node_results"] if r["node_id"] == util)
    assert step["status"] == "ok"
    assert "base" in step["output"]["text"]
    assert '{"k":1}' in step["output"]["text"]


def test_validate_against_structure_by_id(client: TestClient):
    schema = '{"type":"object","properties":{"x":{"type":"string"}},"required":["x"]}'
    st = client.post(
        "/api/v1/structures/",
        json={"name": f"v_{uuid.uuid4().hex[:8]}", "description": "", "json_schema": schema},
    )
    assert st.status_code == 201
    sid = st.json()["id"]
    uid = "n_val"
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "validate",
            "graph": {"nodes": [_validate_structure_node(uid, sid)], "edges": []},
        },
    )
    assert wf.status_code == 201
    run = client.post(f"/api/v1/workflow-definitions/{wf.json()['id']}/run")
    assert run.status_code == 200
    step = next(r for r in run.json()["node_results"] if r["node_id"] == uid)
    assert step["status"] == "ok"
    assert step["output"]["kind"] == "dictionary"
    assert step["output"]["data"] == {"x": "ok"}
