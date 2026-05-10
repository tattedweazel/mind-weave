"""
Tests for WorkflowExecutor — Simple LLM Call skill node.

Ensures that when a String node is connected to a Simple LLM Call node, the LLM call
receives the correct system_prompt and user_prompt from required_inputs, upstream,
and input_overrides.
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.persistence.tables import UrlSnapshotArtifact, User
from app.providers.base import ProviderResponse
from app.providers.lmstudio import LMStudioModelNotMultimodalError
from tests.sse_helpers import sse_response_body_to_legacy_workflow_events


def _resolved_inputs(details: dict | None) -> dict:
    ri = (details or {}).get("resolved_inputs")
    return ri if isinstance(ri, dict) else {}


def _simple_llm_node(
    node_id: str,
    persona_id: str,
    user_prompt: str | None = None,
    additional_context: str | None = None,
    label: str = "LLM Call",
):
    """Simple LLM Call node; requires persona_id. Model and creativity come from Persona."""
    data = {
        "required_inputs": [{"key": "user_prompt", "type": "string", "value": user_prompt}],
        "persona_id": persona_id,
        "additional_system_prompt_context": additional_context,
    }
    return {
        "id": node_id,
        "kind": "skill",
        "skill_type": "simple_llm_call",
        "label": label,
        "data": data,
        "position": {"x": 400, "y": 100},
    }


def _get_persona_id(client: TestClient) -> str:
    """Get first persona ID from API (tests have default personas)."""
    res = client.get("/api/v1/personas/")
    assert res.status_code == 200
    personas = res.json()
    assert len(personas) >= 1
    return personas[0]["id"]


def _basic_conditional_node(
    node_id: str,
    condition_value: str | None = None,
    label: str = "Conditional",
) -> dict:
    """Basic Conditional control node. condition_value in required_inputs or data.condition."""
    data: dict = {"required_inputs": [{"key": "condition", "type": "string", "value": condition_value}]}
    if condition_value is not None:
        data["condition"] = condition_value
    return {
        "id": node_id,
        "kind": "control",
        "control_type": "basic_conditional",
        "label": label,
        "data": data,
        "position": {"x": 200, "y": 100},
    }


def _is_node(
    node_id: str,
    input_a: str | list | dict | None = None,
    input_b: str | list | dict | None = None,
    label: str = "Is?",
) -> dict:
    """Is? control node. input_a and input_b in required_inputs."""
    required_inputs = [
        {"key": "input_a", "type": "string", "value": input_a},
        {"key": "input_b", "type": "string", "value": input_b},
    ]
    return {
        "id": node_id,
        "kind": "control",
        "control_type": "is",
        "label": label,
        "data": {"required_inputs": required_inputs},
        "position": {"x": 200, "y": 100},
    }


def _is_empty_node(node_id: str, value: Any | None = None, label: str = "Is Empty?") -> dict:
    """Is Empty? control: value must be a list or dict at runtime."""
    return {
        "id": node_id,
        "kind": "control",
        "control_type": "is_empty",
        "label": label,
        "data": {"required_inputs": [{"key": "value", "type": "any", "value": value}]},
        "position": {"x": 200, "y": 100},
    }


def _comparison_node(node_id: str, control_type: str, input_a: Any, input_b: Any, label: str) -> dict:
    """Gt?, Lt?, Gte?, Lte? control node."""
    return {
        "id": node_id,
        "kind": "control",
        "control_type": control_type,
        "label": label,
        "data": {
            "required_inputs": [
                {"key": "input_a", "type": "string", "value": input_a},
                {"key": "input_b", "type": "string", "value": input_b},
            ]
        },
        "position": {"x": 200, "y": 100},
    }


def _logical_node(node_id: str, control_type: str, input_a: Any, input_b: Any, label: str) -> dict:
    """And, Or, Xor control node."""
    return {
        "id": node_id,
        "kind": "control",
        "control_type": control_type,
        "label": label,
        "data": {
            "required_inputs": [
                {"key": "input_a", "type": "boolean", "value": input_a},
                {"key": "input_b", "type": "boolean", "value": input_b},
            ]
        },
        "position": {"x": 200, "y": 100},
    }


def _binary_int_utility_node(node_id: str, utility_type: str, input_a: int, input_b: int, label: str) -> dict:
    """Binary int utility (add, subtract, multiply, divide, modulo, min, max)."""
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
        "position": {"x": 200, "y": 100},
    }


def _not_control_node(node_id: str, input_val: Any, label: str = "Not") -> dict:
    return {
        "id": node_id,
        "kind": "control",
        "control_type": "not",
        "label": label,
        "data": {"required_inputs": [{"key": "input", "type": "boolean", "value": input_val}]},
        "position": {"x": 200, "y": 100},
    }


def _between_control_node(node_id: str, low: int, value: int, high: int, label: str = "Between") -> dict:
    return {
        "id": node_id,
        "kind": "control",
        "control_type": "between",
        "label": label,
        "data": {
            "required_inputs": [
                {"key": "low", "type": "int", "value": low},
                {"key": "value", "type": "int", "value": value},
                {"key": "high", "type": "int", "value": high},
            ]
        },
        "position": {"x": 200, "y": 100},
    }


def test_string_node_value_reaches_simple_llm_as_user_prompt(client: TestClient):
    """
    When a String node with text is connected to a SimpleLLMCall node, the LLM call
    should receive that text as the User Prompt (via target_handle).
    """
    persona_id = _get_persona_id(client)
    string_node_id = "n_string_001"
    llm_node_id = "n_llm_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "String to SimpleLLMCall Test",
            "graph": {
                "nodes": [
                    {
                        "id": string_node_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "String Input",
                        "data": {"text": "Hello from String"},
                        "position": {"x": 100, "y": 100},
                    },
                    _simple_llm_node(llm_node_id, persona_id),
                ],
                "edges": [
                    {"source": string_node_id, "target": llm_node_id, "target_handle": "user_prompt"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="Mock LLM response",
        parsed=None,
        provider_name="lmstudio",
        usage=None,
    )

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    assert "node_results" in result

    llm_result = next(
        (r for r in result["node_results"] if r["node_id"] == llm_node_id),
        None,
    )
    assert llm_result is not None, "SimpleLLMCall node result should exist"
    assert llm_result["status"] == "ok"

    details = llm_result.get("details", {})
    user_prompt = _resolved_inputs(details).get("user_prompt", "")
    assert "Hello from String" in user_prompt, f"User prompt should contain String node text. Got: {user_prompt!r}"


def test_string_node_with_upstream_includes_own_text(client: TestClient):
    """
    When Start (empty) -> String (has text) -> SimpleLLMCall, the String node's own text
    should reach the SimpleLLMCall.
    """
    persona_id = _get_persona_id(client)
    start_id = "n_start_001"
    string_id = "n_string_001"
    llm_node_id = "n_llm_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Start-String-SimpleLLMCall",
            "graph": {
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {"text": ""},
                        "position": {"x": 50, "y": 100},
                    },
                    {
                        "id": string_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "String",
                        "data": {"text": "User-provided context"},
                        "position": {"x": 200, "y": 100},
                    },
                    _simple_llm_node(llm_node_id, persona_id),
                ],
                "edges": [
                    {"source": start_id, "target": string_id},
                    {"source": string_id, "target": llm_node_id, "target_handle": "user_prompt"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="OK",
        parsed=None,
        provider_name="lmstudio",
        usage=None,
    )

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    llm_result = next(
        (r for r in result["node_results"] if r["node_id"] == llm_node_id),
        None,
    )
    assert llm_result is not None
    assert llm_result["status"] == "ok"

    user_prompt = _resolved_inputs(llm_result.get("details")).get("user_prompt", "")
    assert "User-provided context" in user_prompt, (
        f"String node's own text should reach SimpleLLMCall. Got: {user_prompt!r}"
    )


def test_start_required_inputs_direct_to_simple_llm(client: TestClient):
    """
    When Start has required_inputs and connects directly to SimpleLLMCall,
    the SimpleLLMCall should receive the Start output via source_handle/target_handle.
    """
    persona_id = _get_persona_id(client)
    start_id = "n_start_001"
    llm_node_id = "n_llm_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Start Direct to SimpleLLMCall",
            "graph": {
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {
                            "required_inputs": [{"key": "user_input", "type": "string", "value": "Hello from Start"}]
                        },
                        "position": {"x": 50, "y": 100},
                    },
                    _simple_llm_node(llm_node_id, persona_id),
                ],
                "edges": [
                    {
                        "source": start_id,
                        "target": llm_node_id,
                        "source_handle": "user_input",
                        "target_handle": "user_prompt",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="OK",
        parsed=None,
        provider_name="lmstudio",
        usage=None,
    )

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    llm_result = next(
        (r for r in result["node_results"] if r["node_id"] == llm_node_id),
        None,
    )
    assert llm_result is not None
    assert llm_result["status"] == "ok"
    user_prompt = _resolved_inputs(llm_result.get("details")).get("user_prompt", "")
    assert "Hello from Start" in user_prompt, f"SimpleLLMCall should receive Start's user_input. Got: {user_prompt!r}"


def test_start_empty_required_inputs_runs_without_override(client: TestClient):
    """
    When Start has required_inputs: [] (no inputs), workflow runs without input_overrides.
    SimpleLLMCall receives empty string from Start's 'output' handle, defaults to 'Please proceed.'
    """
    persona_id = _get_persona_id(client)
    start_id = "n_start_001"
    llm_node_id = "n_llm_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Start Empty to SimpleLLMCall",
            "graph": {
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _simple_llm_node(llm_node_id, persona_id),
                ],
                "edges": [
                    {
                        "source": start_id,
                        "target": llm_node_id,
                        "source_handle": "output",
                        "target_handle": "user_prompt",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="OK",
        parsed=None,
        provider_name="lmstudio",
        usage=None,
    )

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    llm_result = next(
        (r for r in result["node_results"] if r["node_id"] == llm_node_id),
        None,
    )
    assert llm_result is not None
    assert llm_result["status"] == "ok"
    user_prompt = _resolved_inputs(llm_result.get("details")).get("user_prompt", "")
    assert "Please proceed." in user_prompt or user_prompt == "Please proceed.", (
        f"SimpleLLMCall should get default prompt when Start has no inputs. Got: {user_prompt!r}"
    )


def test_start_empty_required_inputs_output_handle(client: TestClient):
    """
    When Start has required_inputs: [], it has single output handle 'output' with empty string.
    Downstream String node receives that value.
    """
    persona_id = _get_persona_id(client)
    start_id = "n_start_001"
    string_id = "n_string_001"
    llm_node_id = "n_llm_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Start Empty Output Handle",
            "graph": {
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    {
                        "id": string_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "String",
                        "data": {"text": ""},
                        "position": {"x": 200, "y": 100},
                    },
                    _simple_llm_node(llm_node_id, persona_id),
                ],
                "edges": [
                    {"source": start_id, "target": string_id, "source_handle": "output"},
                    {"source": string_id, "target": llm_node_id, "target_handle": "user_prompt"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="OK",
        parsed=None,
        provider_name="lmstudio",
        usage=None,
    )

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    llm_result = next(
        (r for r in result["node_results"] if r["node_id"] == llm_node_id),
        None,
    )
    assert llm_result is not None
    assert llm_result["status"] == "ok"
    user_prompt = _resolved_inputs(llm_result.get("details")).get("user_prompt", "")
    assert user_prompt == "" or "Please proceed." in user_prompt, (
        f"String should receive empty from Start output handle. Got user_prompt: {user_prompt!r}"
    )


def test_start_required_inputs_with_overrides(client: TestClient):
    """
    When Start has required_inputs with null value, run with input_overrides
    should supply the value to SimpleLLMCall.
    """
    persona_id = _get_persona_id(client)
    start_id = "n_start_001"
    llm_node_id = "n_llm_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Start With Override",
            "graph": {
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "user_input", "type": "string", "value": None}]},
                        "position": {"x": 50, "y": 100},
                    },
                    _simple_llm_node(llm_node_id, persona_id),
                ],
                "edges": [
                    {
                        "source": start_id,
                        "target": llm_node_id,
                        "source_handle": "user_input",
                        "target_handle": "user_prompt",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="OK",
        parsed=None,
        provider_name="lmstudio",
        usage=None,
    )

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(
            f"/api/v1/workflow-definitions/{workflow_id}/run",
            json={"input_overrides": {"user_input": "Override value"}},
        )
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    llm_result = next(
        (r for r in result["node_results"] if r["node_id"] == llm_node_id),
        None,
    )
    assert llm_result is not None
    assert llm_result["status"] == "ok"
    user_prompt = _resolved_inputs(llm_result.get("details")).get("user_prompt", "")
    assert "Override value" in user_prompt, f"SimpleLLMCall should receive override. Got: {user_prompt!r}"


def test_simple_llm_required_inputs_with_overrides(client: TestClient):
    """
    SimpleLLMCall with null user_prompt; input_overrides for user_prompt should supply value.
    System prompt comes from Persona.
    """
    persona_id = _get_persona_id(client)
    llm_node_id = "n_llm_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "SimpleLLMCall Override",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start_001",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "user_input", "type": "string", "value": "ignored"}]},
                        "position": {"x": 50, "y": 100},
                    },
                    _simple_llm_node(llm_node_id, persona_id),
                ],
                "edges": [
                    {
                        "source": "n_start_001",
                        "target": llm_node_id,
                        "source_handle": "user_input",
                        "target_handle": "user_prompt",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="OK",
        parsed=None,
        provider_name="lmstudio",
        usage=None,
    )

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(
            f"/api/v1/workflow-definitions/{workflow_id}/run",
            json={"input_overrides": {"user_prompt": "Say hello."}},
        )
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    llm_result = next(
        (r for r in result["node_results"] if r["node_id"] == llm_node_id),
        None,
    )
    assert llm_result is not None
    assert llm_result["status"] == "ok"
    details = llm_result.get("details", {})
    assert "Say hello." in (_resolved_inputs(details).get("user_prompt") or "")


def test_simple_llm_model_and_creativity_from_persona(client: TestClient):
    """
    SimpleLLMCall with persona_id should pass Persona's model and creativity to LMStudioProvider.
    """
    personas_res = client.get("/api/v1/personas/")
    assert personas_res.status_code == 200
    personas = personas_res.json()
    assert len(personas) >= 1
    persona = personas[0]
    persona_id = persona["id"]
    persona_creativity = persona.get("creativity", 0.2)

    llm_node_id = "n_llm_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "SimpleLLMCall Model Creativity",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start_001",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "user_input", "type": "string", "value": "Hi"}]},
                        "position": {"x": 50, "y": 100},
                    },
                    _simple_llm_node(llm_node_id, persona_id),
                ],
                "edges": [
                    {
                        "source": "n_start_001",
                        "target": llm_node_id,
                        "source_handle": "user_input",
                        "target_handle": "user_prompt",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="OK",
        parsed=None,
        provider_name="lmstudio",
        usage=None,
    )

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    mock_instance.chat.assert_called_once()
    call_args = mock_instance.chat.call_args
    options = call_args[1].get("options", {})
    assert options.get("temperature") == persona_creativity
    assert "reasoning_effort" not in options


def test_simple_llm_passes_reasoning_effort_when_persona_suppresses_thinking(client: TestClient):
    """SimpleLLMCall should pass reasoning_effort none when Persona has suppress_lm_thinking."""
    create = client.post(
        "/api/v1/personas/",
        json={
            "name": "Suppress For Workflow",
            "description": "d",
            "system_prompt": "You are a test assistant.",
            "suppress_lm_thinking": True,
        },
    )
    assert create.status_code == 201
    persona_id = create.json()["id"]

    llm_node_id = "n_llm_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "SimpleLLMCall Suppress Thinking",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start_001",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "user_input", "type": "string", "value": "Hi"}]},
                        "position": {"x": 50, "y": 100},
                    },
                    _simple_llm_node(llm_node_id, persona_id),
                ],
                "edges": [
                    {
                        "source": "n_start_001",
                        "target": llm_node_id,
                        "source_handle": "user_input",
                        "target_handle": "user_prompt",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="OK",
        parsed=None,
        provider_name="lmstudio",
        usage=None,
    )

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    mock_instance.chat.assert_called_once()
    options = mock_instance.chat.call_args[1].get("options", {})
    assert options.get("reasoning_effort") == "none"


def test_simple_llm_without_persona_fails(client: TestClient):
    """
    SimpleLLMCall without persona_id should fail with a helpful error message.
    """
    llm_node_id = "n_llm_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "SimpleLLMCall No Persona",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start_001",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "user_input", "type": "string", "value": "Hi"}]},
                        "position": {"x": 50, "y": 100},
                    },
                    {
                        "id": llm_node_id,
                        "kind": "skill",
                        "skill_type": "simple_llm_call",
                        "label": "LLM",
                        "data": {
                            "required_inputs": [{"key": "user_prompt", "type": "string", "value": None}],
                            "persona_id": None,
                        },
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start_001",
                        "target": llm_node_id,
                        "source_handle": "user_input",
                        "target_handle": "user_prompt",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] in ("partial", "error")
    llm_result = next((r for r in result["node_results"] if r["node_id"] == llm_node_id), None)
    assert llm_result is not None
    assert llm_result["status"] == "error"
    assert "Persona" in (llm_result.get("error") or "")


def test_simple_llm_with_persona_uses_persona_values(client: TestClient):
    """
    SimpleLLMCall with persona_id should use Persona's system_prompt, model, creativity.
    """
    personas_res = client.get("/api/v1/personas/")
    assert personas_res.status_code == 200
    personas = personas_res.json()
    assert len(personas) >= 1
    persona_id = personas[0]["id"]
    persona_detail = client.get(f"/api/v1/personas/{persona_id}").json()
    persona_system_prompt = persona_detail["system_prompt"]
    persona_creativity = persona_detail.get("creativity", 0.2)

    llm_node_id = "n_llm_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "SimpleLLMCall With Persona",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start_001",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "user_input", "type": "string", "value": None}]},
                        "position": {"x": 50, "y": 100},
                    },
                    _simple_llm_node(llm_node_id, persona_id),
                ],
                "edges": [
                    {
                        "source": "n_start_001",
                        "target": llm_node_id,
                        "source_handle": "user_input",
                        "target_handle": "user_prompt",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="OK",
        parsed=None,
        provider_name="lmstudio",
        usage=None,
    )

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(
            f"/api/v1/workflow-definitions/{workflow_id}/run",
            json={"input_overrides": {"user_input": "Hello"}},
        )
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    llm_result = next(
        (r for r in result["node_results"] if r["node_id"] == llm_node_id),
        None,
    )
    assert llm_result is not None
    assert llm_result["status"] == "ok"
    details = llm_result.get("details", {})
    ri = _resolved_inputs(details)
    assert ri.get("persona_system_prompt") == persona_system_prompt
    full_sys = ri.get("system_prompt") or ""
    assert persona_system_prompt in full_sys
    assert "Hello" in (ri.get("user_prompt") or "")
    assert "Hello" in (ri.get("user_role_message") or "")

    mock_instance.chat.assert_called_once()
    call_args = mock_instance.chat.call_args
    messages = call_args[0][0]
    options = call_args[1].get("options", {})
    assert any(m.get("role") == "system" and persona_system_prompt in (m.get("content") or "") for m in messages)
    assert options.get("temperature") == persona_creativity


def test_simple_llm_persona_with_additional_context(client: TestClient):
    """
    Persona selected + additional_system_prompt_context in node data;
    additional context is appended to the system message after the Persona text.
    """
    persona_id = _get_persona_id(client)
    persona_system_prompt = client.get(f"/api/v1/personas/{persona_id}").json()["system_prompt"]
    additional = "Extra context for this specific task."

    llm_node_id = "n_llm_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Persona With Additional",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start_001",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "user_input", "type": "string", "value": "Hi"}]},
                        "position": {"x": 50, "y": 100},
                    },
                    _simple_llm_node(llm_node_id, persona_id, "Hi", additional),
                ],
                "edges": [
                    {
                        "source": "n_start_001",
                        "target": llm_node_id,
                        "source_handle": "user_input",
                        "target_handle": "user_prompt",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(raw_text="OK", parsed=None, provider_name="lmstudio", usage=None)
    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    llm_result = next((r for r in result["node_results"] if r["node_id"] == llm_node_id), None)
    assert llm_result is not None
    details = llm_result.get("details", {})
    ri = _resolved_inputs(details)
    sys_prompt = ri.get("system_prompt") or ""
    assert persona_system_prompt in sys_prompt
    assert additional in sys_prompt
    assert ri.get("additional_context") == additional
    assert ri.get("persona_system_prompt") == persona_system_prompt
    mock_instance.chat.assert_called_once()
    messages = mock_instance.chat.call_args[0][0]
    user_content = next(m.get("content") or "" for m in messages if m.get("role") == "user")
    assert additional not in user_content
    assert "Hi" in user_content


def test_simple_llm_persona_additional_context_from_upstream(client: TestClient):
    """
    Persona selected + String node wired to additional_context handle;
    wired text is appended to the system message after the Persona text.
    """
    persona_id = _get_persona_id(client)
    persona_system_prompt = client.get(f"/api/v1/personas/{persona_id}").json()["system_prompt"]
    wired_text = "Context from wired String node."

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Persona With Wired Additional",
            "graph": {
                "nodes": [
                    {
                        "id": "n_string_001",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "String",
                        "data": {"text": wired_text},
                        "position": {"x": 100, "y": 100},
                    },
                    _simple_llm_node("n_llm_001", persona_id, "Hello"),
                ],
                "edges": [
                    {"source": "n_string_001", "target": "n_llm_001", "target_handle": "additional_context"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(raw_text="OK", parsed=None, provider_name="lmstudio", usage=None)
    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    llm_result = next((r for r in result["node_results"] if r["node_id"] == "n_llm_001"), None)
    assert llm_result is not None
    details = llm_result.get("details", {})
    sys_prompt = _resolved_inputs(details).get("system_prompt") or ""
    assert persona_system_prompt in sys_prompt
    assert wired_text in sys_prompt
    assert wired_text in (_resolved_inputs(details).get("additional_context") or "")
    mock_instance.chat.assert_called_once()
    messages = mock_instance.chat.call_args[0][0]
    user_content = next(m.get("content") or "" for m in messages if m.get("role") == "user")
    assert wired_text not in user_content
    assert "Hello" in user_content


def test_workflow_node_executes_subworkflow(client: TestClient):
    """
    When a workflow node references a sub-workflow, running the parent executes
    the sub-workflow and passes its Stop output to the parent.
    """
    persona_id = _get_persona_id(client)
    sub_llm_id = "n_llm_sub"
    sub_wf_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Sub Workflow",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start_sub",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "user_input", "type": "string", "value": "From parent"}]},
                        "position": {"x": 50, "y": 100},
                    },
                    _simple_llm_node(sub_llm_id, persona_id),
                    {
                        "id": "n_stop_sub",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start_sub",
                        "target": sub_llm_id,
                        "source_handle": "user_input",
                        "target_handle": "user_prompt",
                    },
                    {"source": sub_llm_id, "target": "n_stop_sub"},
                ],
            },
        },
    )
    assert sub_wf_res.status_code == 201
    sub_wf_id = sub_wf_res.json()["id"]

    parent_wf_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Parent With Workflow Node",
            "graph": {
                "nodes": [
                    {
                        "id": "n_wf_001",
                        "kind": "workflow",
                        "label": "Sub Workflow",
                        "data": {"workflow_id": sub_wf_id},
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": "n_stop_parent",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_wf_001", "target": "n_stop_parent", "source_handle": "output"},
                ],
            },
        },
    )
    assert parent_wf_res.status_code == 201
    parent_wf_id = parent_wf_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="Sub workflow output",
        parsed=None,
        provider_name="lmstudio",
        usage=None,
    )

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{parent_wf_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    stop_result = next(
        (r for r in result["node_results"] if r["node_id"] == "n_stop_parent"),
        None,
    )
    assert stop_result is not None
    assert stop_result["status"] == "ok"
    assert "Sub workflow output" in (stop_result.get("output", {}).get("text", ""))


def test_workflow_node_chains_list_output_as_list_in_input_overrides(client: TestClient):
    """List Stop output wired into a downstream Workflow node must not stringify for Start overrides."""
    sub_list = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Sub List Out",
            "graph": {
                "nodes": [
                    {
                        "id": "n_list",
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": [1, 2, 3],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "list"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [{"source": "n_list", "target": "n_stop"}],
            },
        },
    )
    assert sub_list.status_code == 201
    sub_list_id = sub_list.json()["id"]

    sub_consume = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Sub Consume List",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {
                            "required_inputs": [{"key": "items", "type": "list", "value": None}],
                        },
                        "position": {"x": 50, "y": 100},
                    },
                    {
                        "id": "n_len",
                        "kind": "utility",
                        "utility_type": "len_from_list",
                        "label": "Len",
                        "data": {},
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 500, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": "n_len", "source_handle": "items", "target_handle": "list"},
                    {"source": "n_len", "target": "n_stop"},
                ],
            },
        },
    )
    assert sub_consume.status_code == 201
    sub_consume_id = sub_consume.json()["id"]

    parent = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Parent Chain List WF",
            "graph": {
                "nodes": [
                    {
                        "id": "wf1",
                        "kind": "workflow",
                        "label": "List producer",
                        "data": {"workflow_id": str(sub_list_id)},
                        "position": {"x": 200, "y": 100},
                    },
                    {
                        "id": "wf2",
                        "kind": "workflow",
                        "label": "Consumer",
                        "data": {"workflow_id": str(sub_consume_id)},
                        "position": {"x": 450, "y": 100},
                    },
                    {
                        "id": "n_stop_p",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 700, "y": 100},
                    },
                ],
                "edges": [
                    {
                        "source": "wf1",
                        "target": "wf2",
                        "source_handle": "output",
                        "target_handle": "items",
                    },
                    {"source": "wf2", "target": "n_stop_p", "source_handle": "output"},
                ],
            },
        },
    )
    assert parent.status_code == 201
    parent_id = parent.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{parent_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"

    wf2_result = next((r for r in result["node_results"] if r["node_id"] == "wf2"), None)
    assert wf2_result is not None
    ov = (wf2_result.get("details") or {}).get("resolved_inputs", {}).get("input_overrides", {})
    assert ov.get("items") == [1, 2, 3]
    assert isinstance(ov.get("items"), list)

    stop_p = next((r for r in result["node_results"] if r["node_id"] == "n_stop_p"), None)
    assert stop_p is not None
    assert stop_p["output"]["kind"] == "int"
    assert stop_p["output"]["value"] == 3


def test_workflow_node_self_reference_fails(client: TestClient):
    """
    Workflow node that references the same workflow (self) should fail.
    """
    wf_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Self Ref",
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
                        "id": "n_wf",
                        "kind": "workflow",
                        "label": "Self",
                        "data": {"workflow_id": "PLACEHOLDER"},
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": "n_wf", "source_handle": "output"},
                    {"source": "n_wf", "target": "n_stop", "source_handle": "output"},
                ],
            },
        },
    )
    assert wf_res.status_code == 201
    wf_id = wf_res.json()["id"]

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        MockProvider.return_value = AsyncMock()

        run_res = client.put(
            f"/api/v1/workflow-definitions/{wf_id}",
            json={
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
                            "id": "n_wf",
                            "kind": "workflow",
                            "label": "Self",
                            "data": {"workflow_id": wf_id},
                            "position": {"x": 300, "y": 100},
                        },
                        {
                            "id": "n_stop",
                            "kind": "stop",
                            "label": "Stop",
                            "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                            "position": {"x": 600, "y": 100},
                        },
                    ],
                    "edges": [
                        {"source": "n_start", "target": "n_wf", "source_handle": "output"},
                        {"source": "n_wf", "target": "n_stop", "source_handle": "output"},
                    ],
                },
            },
        )
        assert run_res.status_code == 200

        run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] in ("partial", "error")
    wf_node_result = next((r for r in result["node_results"] if r["node_id"] == "n_wf"), None)
    assert wf_node_result is not None
    assert wf_node_result["status"] == "error"
    assert "self-reference" in (wf_node_result.get("error") or "").lower()


def test_workflow_node_cycle_fails(client: TestClient):
    """
    Workflow A references B, B references A — should fail with cycle error.
    """
    wf_a_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Workflow A",
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
                        "id": "n_wf",
                        "kind": "workflow",
                        "label": "B",
                        "data": {"workflow_id": "PLACEHOLDER_B"},
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": "n_wf", "source_handle": "output"},
                    {"source": "n_wf", "target": "n_stop", "source_handle": "output"},
                ],
            },
        },
    )
    assert wf_a_res.status_code == 201
    wf_a_id = wf_a_res.json()["id"]

    wf_b_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Workflow B",
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
                        "id": "n_wf",
                        "kind": "workflow",
                        "label": "A",
                        "data": {"workflow_id": wf_a_id},
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": "n_wf", "source_handle": "output"},
                    {"source": "n_wf", "target": "n_stop", "source_handle": "output"},
                ],
            },
        },
    )
    assert wf_b_res.status_code == 201
    wf_b_id = wf_b_res.json()["id"]

    client.put(
        f"/api/v1/workflow-definitions/{wf_a_id}",
        json={
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
                        "id": "n_wf",
                        "kind": "workflow",
                        "label": "B",
                        "data": {"workflow_id": wf_b_id},
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": "n_wf", "source_handle": "output"},
                    {"source": "n_wf", "target": "n_stop", "source_handle": "output"},
                ],
            },
        },
    )

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        MockProvider.return_value = AsyncMock()

        run_res = client.post(f"/api/v1/workflow-definitions/{wf_a_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] in ("partial", "error")
    wf_node_result = next((r for r in result["node_results"] if r["node_id"] == "n_wf"), None)
    assert wf_node_result is not None
    assert wf_node_result["status"] == "error"
    assert "cycle" in (wf_node_result.get("error") or "").lower()


def test_simple_llm_persona_additional_context_from_both(client: TestClient):
    """
    Persona + node additional_system_prompt_context field + upstream wire;
    combined additional context is appended to the system message after the Persona text.
    """
    persona_id = _get_persona_id(client)
    persona_system_prompt = client.get(f"/api/v1/personas/{persona_id}").json()["system_prompt"]
    node_additional = "From inspector field."
    wired_additional = "From wired String."

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Persona With Both",
            "graph": {
                "nodes": [
                    {
                        "id": "n_string_001",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "String",
                        "data": {"text": wired_additional},
                        "position": {"x": 100, "y": 100},
                    },
                    _simple_llm_node("n_llm_001", persona_id, "Hi", node_additional),
                ],
                "edges": [
                    {"source": "n_string_001", "target": "n_llm_001", "target_handle": "additional_context"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(raw_text="OK", parsed=None, provider_name="lmstudio", usage=None)
    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    llm_result = next((r for r in result["node_results"] if r["node_id"] == "n_llm_001"), None)
    assert llm_result is not None
    details = llm_result.get("details", {})
    sys_prompt = _resolved_inputs(details).get("system_prompt") or ""
    assert persona_system_prompt in sys_prompt
    assert node_additional in sys_prompt
    assert wired_additional in sys_prompt
    combined_ctx = _resolved_inputs(details).get("additional_context") or ""
    assert node_additional in combined_ctx
    assert wired_additional in combined_ctx
    mock_instance.chat.assert_called_once()
    messages = mock_instance.chat.call_args[0][0]
    user_content = next(m.get("content") or "" for m in messages if m.get("role") == "user")
    assert node_additional not in user_content
    assert wired_additional not in user_content
    assert "Hi" in user_content


def test_simple_llm_with_structure_returns_dictionary_output(client: TestClient):
    """
    SimpleLLMCall with structure_id and parsed JSON response returns DictionaryNodeOutput.
    """
    persona_id = _get_persona_id(client)
    schema = '{"type":"object","properties":{"joke":{"type":"string"}},"required":["joke"]}'
    struct_res = client.post(
        "/api/v1/structures/", json={"name": "Joke", "description": "Joke schema", "json_schema": schema}
    )
    assert struct_res.status_code == 201
    structure_id = struct_res.json()["id"]

    llm_node_id = "n_llm_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Structured Output Test",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start_001",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "user_input", "type": "string", "value": "Tell a joke"}]},
                        "position": {"x": 50, "y": 100},
                    },
                    {
                        "id": llm_node_id,
                        "kind": "skill",
                        "skill_type": "simple_llm_call",
                        "label": "LLM",
                        "data": {
                            "required_inputs": [{"key": "user_prompt", "type": "string", "value": None}],
                            "persona_id": persona_id,
                            "structure_id": structure_id,
                        },
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start_001",
                        "target": llm_node_id,
                        "source_handle": "user_input",
                        "target_handle": "user_prompt",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text='{"joke":"Why did the chicken cross the road?"}',
        parsed={"joke": "Why did the chicken cross the road?"},
        provider_name="lmstudio",
        usage=None,
    )
    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    llm_result = next((r for r in result["node_results"] if r["node_id"] == llm_node_id), None)
    assert llm_result is not None
    assert llm_result["status"] == "ok"
    output = llm_result.get("output", {})
    assert output.get("kind") == "dictionary"
    assert output.get("data") == {"joke": "Why did the chicken cross the road?"}

    mock_instance.chat.assert_called_once()
    call_args = mock_instance.chat.call_args
    options = call_args[1].get("options", {})
    assert "response_format" in options
    rf = options["response_format"]
    assert rf.get("type") == "json_schema"
    assert "json_schema" in rf
    assert rf["json_schema"].get("schema", {}).get("properties", {}).get("joke") is not None


def test_structure_primitive_resolves_and_wires_to_simple_llm(client: TestClient):
    """
    Structure primitive with structure_id wired to SimpleLLMCall passes schema via response_format.
    """
    persona_id = _get_persona_id(client)
    schema = '{"type":"object","properties":{"title":{"type":"string"}},"required":["title"]}'
    struct_res = client.post("/api/v1/structures/", json={"name": "Title", "description": "", "json_schema": schema})
    assert struct_res.status_code == 201
    structure_id = struct_res.json()["id"]

    struct_node_id = "n_struct_001"
    llm_node_id = "n_llm_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Structure Primitive Test",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start_001",
                        "kind": "start",
                        "label": "Start",
                        "data": {
                            "required_inputs": [{"key": "user_input", "type": "string", "value": "Generate a title"}]
                        },
                        "position": {"x": 50, "y": 100},
                    },
                    {
                        "id": struct_node_id,
                        "kind": "primitive",
                        "primitive_type": "structure",
                        "label": "Structure",
                        "data": {"structure_id": structure_id},
                        "position": {"x": 200, "y": 100},
                    },
                    {
                        "id": llm_node_id,
                        "kind": "skill",
                        "skill_type": "simple_llm_call",
                        "label": "LLM",
                        "data": {
                            "required_inputs": [{"key": "user_prompt", "type": "string", "value": None}],
                            "persona_id": persona_id,
                        },
                        "position": {"x": 450, "y": 100},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start_001",
                        "target": llm_node_id,
                        "source_handle": "user_input",
                        "target_handle": "user_prompt",
                    },
                    {"source": struct_node_id, "target": llm_node_id, "target_handle": "structure"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text='{"title":"My Generated Title"}',
        parsed={"title": "My Generated Title"},
        provider_name="lmstudio",
        usage=None,
    )
    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    llm_result = next((r for r in result["node_results"] if r["node_id"] == llm_node_id), None)
    assert llm_result is not None
    assert llm_result["status"] == "ok"
    output = llm_result.get("output", {})
    assert output.get("kind") == "dictionary"
    assert output.get("data") == {"title": "My Generated Title"}

    mock_instance.chat.assert_called_once()
    call_args = mock_instance.chat.call_args
    options = call_args[1].get("options", {})
    assert "response_format" in options
    rf = options["response_format"]
    assert rf["json_schema"]["schema"].get("properties", {}).get("title") is not None


def test_simple_llm_with_structure_type_array_normalized_for_mlx(client: TestClient):
    """
    Structure with type array (e.g. ["string","null"]) is normalized before sending to LM Studio.
    Ensures MLX/outlines compatibility: 'type' must be a string.
    """
    persona_id = _get_persona_id(client)
    schema = '{"type":"object","properties":{"summary":{"type":["string","null"]}},"required":["summary"]}'
    struct_res = client.post(
        "/api/v1/structures/", json={"name": "NullableSummary", "description": "nullable", "json_schema": schema}
    )
    assert struct_res.status_code == 201
    structure_id = struct_res.json()["id"]

    llm_node_id = "n_llm_002"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "MLX Schema Normalization Test",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start_002",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "user_input", "type": "string", "value": "Summarize"}]},
                        "position": {"x": 50, "y": 100},
                    },
                    {
                        "id": llm_node_id,
                        "kind": "skill",
                        "skill_type": "simple_llm_call",
                        "label": "LLM",
                        "data": {
                            "required_inputs": [{"key": "user_prompt", "type": "string", "value": None}],
                            "persona_id": persona_id,
                            "structure_id": structure_id,
                        },
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start_002",
                        "target": llm_node_id,
                        "source_handle": "user_input",
                        "target_handle": "user_prompt",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text='{"summary":"A brief summary."}',
        parsed={"summary": "A brief summary."},
        provider_name="lmstudio",
        usage=None,
    )
    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    mock_instance.chat.assert_called_once()
    call_args = mock_instance.chat.call_args
    options = call_args[1].get("options", {})
    assert "response_format" in options
    rf = options["response_format"]
    assert rf.get("type") == "json_schema"
    assert rf["json_schema"]["strict"] is True
    schema_sent = rf["json_schema"]["schema"]
    # type array was normalized to string
    assert schema_sent["properties"]["summary"]["type"] == "string"
    assert isinstance(schema_sent["properties"]["summary"]["type"], str)


# ---------------------------------------------------------------------------
# List to String utility tests (no LLM calls)
# ---------------------------------------------------------------------------


def _list_to_string_node(node_id: str, label: str = "List to String", data: dict | None = None):
    """List to String utility node."""
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "list_to_string",
        "label": label,
        "data": dict(data) if data is not None else {},
        "position": {"x": 300, "y": 100},
    }


def test_list_primitive_passes_through_upstream_list(client: TestClient):
    """List primitive with single list upstream passes it through (no wrapping)."""
    list_a_id = "n_list_a"
    list_b_id = "n_list_b"
    len_id = "n_len"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "List Pass Through",
            "graph": {
                "nodes": [
                    {
                        "id": list_a_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List A",
                        "data": ["x", "y", "z"],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": list_b_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List B",
                        "data": [],
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": len_id,
                        "kind": "utility",
                        "utility_type": "len_from_list",
                        "label": "Len",
                        "data": {},
                        "position": {"x": 500, "y": 100},
                    },
                ],
                "edges": [
                    {"source": list_a_id, "target": list_b_id},
                    {"source": list_b_id, "target": len_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    len_result = next((r for r in result["node_results"] if r["node_id"] == len_id), None)
    assert len_result is not None
    assert len_result["output"]["value"] == 3


def test_list_to_string_utility_converts_list_to_string(client: TestClient):
    """List primitive -> List to String -> output is JSON string."""
    list_node_id = "n_list_001"
    l2s_node_id = "n_l2s_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "List to String Test",
            "graph": {
                "nodes": [
                    {
                        "id": list_node_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List Input",
                        "data": ["a", "b", "c"],
                        "position": {"x": 100, "y": 100},
                    },
                    _list_to_string_node(l2s_node_id),
                ],
                "edges": [
                    {"source": list_node_id, "target": l2s_node_id, "target_handle": "input"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    l2s_result = next((r for r in result["node_results"] if r["node_id"] == l2s_node_id), None)
    assert l2s_result is not None
    assert l2s_result["status"] == "ok"
    output = l2s_result.get("output", {})
    assert output.get("kind") == "string"
    assert output.get("text") == '[\n  "a",\n  "b",\n  "c"\n]'


def test_list_to_string_utility_with_upstream_list(client: TestClient):
    """Start (list slot) -> List to String -> output is JSON string."""
    start_id = "n_start_001"
    l2s_node_id = "n_l2s_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Start to List to String",
            "graph": {
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "items", "type": "list", "value": [1, 2, 3]}]},
                        "position": {"x": 50, "y": 100},
                    },
                    _list_to_string_node(l2s_node_id),
                ],
                "edges": [
                    {"source": start_id, "target": l2s_node_id, "source_handle": "items", "target_handle": "input"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    l2s_result = next((r for r in result["node_results"] if r["node_id"] == l2s_node_id), None)
    assert l2s_result is not None
    assert l2s_result["status"] == "ok"
    output = l2s_result.get("output", {})
    assert output.get("kind") == "string"
    assert output.get("text") == "[\n  1,\n  2,\n  3\n]"


def test_stop_node_uses_only_last_upstream(client: TestClient):
    """Stop with multiple upstream (String + List) uses only the last, not concatenation.

    When List -> Stop and another node -> Stop, concatenating all would prepend stray
    output. Stop returns only the last upstream (the primary input).
    """
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Stop Last Upstream Test",
            "graph": {
                "nodes": [
                    {
                        "id": "n_str",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Stray",
                        "data": {"text": "stray"},
                        "position": {"x": 100, "y": 50},
                    },
                    {
                        "id": "n_list",
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": ["a", "b", "c"],
                        "position": {"x": 100, "y": 150},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "list"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_str", "target": "n_stop"},
                    {"source": "n_list", "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    stop_result = next((r for r in result["node_results"] if r["node_id"] == "n_stop"), None)
    assert stop_result is not None
    assert stop_result["status"] == "ok"
    output = stop_result.get("output", {})
    assert output.get("kind") == "list"
    assert output.get("data") == ["a", "b", "c"]
    assert "stray" not in str(output)


def test_list_to_string_utility_empty_list(client: TestClient):
    """Empty list input -> output is '[]'."""
    list_node_id = "n_list_001"
    l2s_node_id = "n_l2s_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Empty List to String",
            "graph": {
                "nodes": [
                    {
                        "id": list_node_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "Empty List",
                        "data": [],
                        "position": {"x": 100, "y": 100},
                    },
                    _list_to_string_node(l2s_node_id),
                ],
                "edges": [
                    {"source": list_node_id, "target": l2s_node_id, "target_handle": "input"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    l2s_result = next((r for r in result["node_results"] if r["node_id"] == l2s_node_id), None)
    assert l2s_result is not None
    assert l2s_result["status"] == "ok"
    output = l2s_result.get("output", {})
    assert output.get("kind") == "string"
    assert output.get("text") == "[]"


def test_list_to_string_use_text_join_with_line_breaks(client: TestClient):
    """List to String with use_text_join joins string items with newlines."""
    list_node_id = "n_list_join_nl"
    l2s_node_id = "n_l2s_join_nl"
    lines = [
        "This is the first line.",
        "This is the second line.",
        "This is the third line.",
    ]
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "List to String join newlines",
            "graph": {
                "nodes": [
                    {
                        "id": list_node_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List Input",
                        "data": lines,
                        "position": {"x": 100, "y": 100},
                    },
                    _list_to_string_node(
                        l2s_node_id,
                        data={
                            "use_text_join": True,
                            "add_line_breaks_between_items": True,
                        },
                    ),
                ],
                "edges": [
                    {"source": list_node_id, "target": l2s_node_id, "target_handle": "input"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    l2s_result = next((r for r in result["node_results"] if r["node_id"] == l2s_node_id), None)
    assert l2s_result is not None
    assert l2s_result["status"] == "ok"
    output = l2s_result.get("output", {})
    assert output.get("kind") == "string"
    assert output.get("text") == "\n".join(lines)


def test_list_to_string_use_text_join_with_spaces(client: TestClient):
    """List to String with use_text_join and no line breaks uses single spaces."""
    list_node_id = "n_list_join_sp"
    l2s_node_id = "n_l2s_join_sp"
    lines = [
        "This is the first line.",
        "This is the second line.",
        "This is the third line.",
    ]
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "List to String join spaces",
            "graph": {
                "nodes": [
                    {
                        "id": list_node_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List Input",
                        "data": lines,
                        "position": {"x": 100, "y": 100},
                    },
                    _list_to_string_node(
                        l2s_node_id,
                        data={
                            "use_text_join": True,
                            "add_line_breaks_between_items": False,
                        },
                    ),
                ],
                "edges": [
                    {"source": list_node_id, "target": l2s_node_id, "target_handle": "input"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    l2s_result = next((r for r in result["node_results"] if r["node_id"] == l2s_node_id), None)
    assert l2s_result is not None
    assert l2s_result["status"] == "ok"
    output = l2s_result.get("output", {})
    assert output.get("kind") == "string"
    assert output.get("text") == " ".join(lines)


def test_list_to_string_use_text_join_empty_list(client: TestClient):
    """Empty list with use_text_join yields empty string."""
    list_node_id = "n_list_empty_join"
    l2s_node_id = "n_l2s_empty_join"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Empty List to String join",
            "graph": {
                "nodes": [
                    {
                        "id": list_node_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "Empty List",
                        "data": [],
                        "position": {"x": 100, "y": 100},
                    },
                    _list_to_string_node(l2s_node_id, data={"use_text_join": True}),
                ],
                "edges": [
                    {"source": list_node_id, "target": l2s_node_id, "target_handle": "input"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    l2s_result = next((r for r in result["node_results"] if r["node_id"] == l2s_node_id), None)
    assert l2s_result is not None
    assert l2s_result["status"] == "ok"
    output = l2s_result.get("output", {})
    assert output.get("kind") == "string"
    assert output.get("text") == ""


# ---------------------------------------------------------------------------
# String to List utility tests (no LLM calls)
# ---------------------------------------------------------------------------


def _string_to_list_node(node_id: str, label: str = "String to List"):
    """String to List utility node."""
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "string_to_list",
        "label": label,
        "data": {},
        "position": {"x": 300, "y": 100},
    }


def test_html_parse_basic_utility_parses_string_input(client: TestClient):
    """String primitive (HTML) -> html_parse_basic -> dictionary output."""
    str_id = "n_str_html"
    hp_id = "n_html_parse"
    html = (
        "<!DOCTYPE html><html><head><title>TT</title></head>"
        '<body><p>One</p><a href="https://example.com">E</a></body></html>'
    )
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "HTML Parse Basic E2E",
            "graph": {
                "nodes": [
                    {
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "HTML",
                        "data": {"text": html},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": hp_id,
                        "kind": "utility",
                        "utility_type": "html_parse_basic",
                        "label": "HTML Parse",
                        "data": {
                            "required_inputs": [
                                {"key": "html", "type": "string", "value": None},
                            ],
                        },
                        "position": {"x": 300, "y": 100},
                    },
                ],
                "edges": [
                    {"source": str_id, "target": hp_id, "target_handle": "html"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    hp_result = next((r for r in result["node_results"] if r["node_id"] == hp_id), None)
    assert hp_result is not None
    assert hp_result["status"] == "ok"
    output = hp_result.get("output", {})
    assert output.get("kind") == "dictionary"
    data = output.get("data", {})
    assert data.get("title") == "TT"
    assert data.get("text_blocks") == [{"tag": "p", "text": "One"}]
    assert data.get("links") == [{"text": "E", "href": "https://example.com"}]


def test_html_parse_basic_errors_when_content_root_css_matches_nothing(client: TestClient):
    str_id = "n_str_hp2"
    hp_id = "n_hp2"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "HTML Parse content root miss",
            "graph": {
                "nodes": [
                    {
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "HTML",
                        "data": {"text": "<html><body><p>x</p></body></html>"},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": hp_id,
                        "kind": "utility",
                        "utility_type": "html_parse_basic",
                        "label": "HTML Parse",
                        "data": {
                            "required_inputs": [
                                {"key": "html", "type": "string", "value": None},
                            ],
                            "content_root_css": "#does-not-exist",
                        },
                        "position": {"x": 300, "y": 100},
                    },
                ],
                "edges": [
                    {"source": str_id, "target": hp_id, "target_handle": "html"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "partial" or result["status"] == "error"
    hp_result = next((r for r in result["node_results"] if r["node_id"] == hp_id), None)
    assert hp_result is not None
    assert hp_result["status"] == "error"
    assert "matched no element" in (hp_result.get("error") or "")


def test_string_to_list_round_trip_after_list_to_string(client: TestClient):
    """List -> List to String -> String to List restores list data."""
    list_node_id = "n_list_rt"
    l2s_id = "n_l2s_rt"
    s2l_id = "n_s2l_rt"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "L2S S2L round trip",
            "graph": {
                "nodes": [
                    {
                        "id": list_node_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": ["a", "b", "c"],
                        "position": {"x": 100, "y": 100},
                    },
                    _list_to_string_node(l2s_id),
                    _string_to_list_node(s2l_id),
                ],
                "edges": [
                    {"source": list_node_id, "target": l2s_id, "target_handle": "input"},
                    {"source": l2s_id, "target": s2l_id, "target_handle": "input"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    s2l_result = next((r for r in result["node_results"] if r["node_id"] == s2l_id), None)
    assert s2l_result is not None
    assert s2l_result["status"] == "ok"
    out = s2l_result.get("output", {})
    assert out.get("kind") == "list"
    assert out.get("data") == ["a", "b", "c"]


def test_string_to_list_from_string_primitive(client: TestClient):
    """String primitive with JSON array text -> String to List."""
    str_id = "n_str_s2l"
    s2l_id = "n_s2l_1"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "String to List from primitive",
            "graph": {
                "nodes": [
                    {
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "JSON text",
                        "data": {"text": "[1, 2, 3]"},
                        "position": {"x": 100, "y": 100},
                    },
                    _string_to_list_node(s2l_id),
                ],
                "edges": [
                    {"source": str_id, "target": s2l_id, "target_handle": "input"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    s2l_result = next((r for r in result["node_results"] if r["node_id"] == s2l_id), None)
    assert s2l_result is not None
    assert s2l_result["status"] == "ok"
    assert s2l_result.get("output", {}).get("data") == [1, 2, 3]


def test_string_to_list_start_string_slot(client: TestClient):
    """Start string slot -> String to List."""
    start_id = "n_start_s2l"
    s2l_id = "n_s2l_st"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Start to String to List",
            "graph": {
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "payload", "type": "string", "value": '["x"]'}]},
                        "position": {"x": 50, "y": 100},
                    },
                    _string_to_list_node(s2l_id),
                ],
                "edges": [
                    {"source": start_id, "target": s2l_id, "source_handle": "payload", "target_handle": "input"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    s2l_result = next((r for r in result["node_results"] if r["node_id"] == s2l_id), None)
    assert s2l_result is not None
    assert s2l_result["status"] == "ok"
    assert s2l_result.get("output", {}).get("data") == ["x"]


def test_string_to_list_invalid_json_errors(client: TestClient):
    """Non-JSON string -> step error."""
    str_id = "n_bad_json"
    s2l_id = "n_s2l_err"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "S2L bad JSON",
            "graph": {
                "nodes": [
                    {
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Bad",
                        "data": {"text": "not json"},
                        "position": {"x": 100, "y": 100},
                    },
                    _string_to_list_node(s2l_id),
                ],
                "edges": [{"source": str_id, "target": s2l_id, "target_handle": "input"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] in ("ok", "partial")
    s2l_result = next((r for r in result["node_results"] if r["node_id"] == s2l_id), None)
    assert s2l_result is not None
    assert s2l_result["status"] == "error"
    assert "invalid json" in (s2l_result.get("error") or "").lower()


def test_string_to_list_non_array_json_errors(client: TestClient):
    """JSON object (not array) -> step error."""
    str_id = "n_obj_json"
    s2l_id = "n_s2l_obj"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "S2L not array",
            "graph": {
                "nodes": [
                    {
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Obj",
                        "data": {"text": '{"a": 1}'},
                        "position": {"x": 100, "y": 100},
                    },
                    _string_to_list_node(s2l_id),
                ],
                "edges": [{"source": str_id, "target": s2l_id, "target_handle": "input"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    s2l_result = next((r for r in result["node_results"] if r["node_id"] == s2l_id), None)
    assert s2l_result is not None
    assert s2l_result["status"] == "error"
    assert "array" in (s2l_result.get("error") or "").lower()


def test_string_to_list_empty_input_errors(client: TestClient):
    """Empty string after strip -> step error."""
    str_id = "n_empty_s2l"
    s2l_id = "n_s2l_empty"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "S2L empty",
            "graph": {
                "nodes": [
                    {
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Empty",
                        "data": {"text": "   "},
                        "position": {"x": 100, "y": 100},
                    },
                    _string_to_list_node(s2l_id),
                ],
                "edges": [{"source": str_id, "target": s2l_id, "target_handle": "input"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    s2l_result = next((r for r in result["node_results"] if r["node_id"] == s2l_id), None)
    assert s2l_result is not None
    assert s2l_result["status"] == "error"
    assert "empty" in (s2l_result.get("error") or "").lower()


# ---------------------------------------------------------------------------
# Int to String utility tests (no LLM calls)
# ---------------------------------------------------------------------------


def _int_to_string_node(node_id: str, label: str = "Int to String"):
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "int_to_string",
        "label": label,
        "data": {},
        "position": {"x": 300, "y": 100},
    }


def test_int_to_string_from_int_primitive(client: TestClient):
    """Int primitive -> Int to String emits decimal text."""
    int_id = "n_int_its"
    its_id = "n_its_1"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Int to String from int",
            "graph": {
                "nodes": [
                    {
                        "id": int_id,
                        "kind": "primitive",
                        "primitive_type": "int",
                        "label": "Int",
                        "data": {"value": -7},
                        "position": {"x": 100, "y": 100},
                    },
                    _int_to_string_node(its_id),
                ],
                "edges": [{"source": int_id, "target": its_id, "target_handle": "input"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    its_result = next((r for r in result["node_results"] if r["node_id"] == its_id), None)
    assert its_result is not None
    assert its_result["status"] == "ok"
    assert its_result.get("output", {}).get("kind") == "string"
    assert its_result.get("output", {}).get("text") == "-7"


def test_int_to_string_from_string_primitive(client: TestClient):
    """String primitive with numeric text -> Int to String."""
    str_id = "n_str_its"
    its_id = "n_its_s"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Int to String from string",
            "graph": {
                "nodes": [
                    {
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Num",
                        "data": {"text": "  42 "},
                        "position": {"x": 100, "y": 100},
                    },
                    _int_to_string_node(its_id),
                ],
                "edges": [{"source": str_id, "target": its_id, "target_handle": "input"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    its_result = next((r for r in result["node_results"] if r["node_id"] == its_id), None)
    assert its_result is not None
    assert its_result["status"] == "ok"
    assert its_result.get("output", {}).get("text") == "42"


def test_int_to_string_start_int_slot(client: TestClient):
    """Start int slot -> Int to String."""
    start_id = "n_start_its"
    its_id = "n_its_st"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Start int to Int to String",
            "graph": {
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "n", "type": "int", "value": 100}]},
                        "position": {"x": 50, "y": 100},
                    },
                    _int_to_string_node(its_id),
                ],
                "edges": [
                    {"source": start_id, "target": its_id, "source_handle": "n", "target_handle": "input"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    its_result = next((r for r in result["node_results"] if r["node_id"] == its_id), None)
    assert its_result is not None
    assert its_result["status"] == "ok"
    assert its_result.get("output", {}).get("text") == "100"


def test_int_to_string_invalid_string_errors(client: TestClient):
    """Non-numeric string -> step error."""
    str_id = "n_bad_its"
    its_id = "n_its_err"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "ITS bad",
            "graph": {
                "nodes": [
                    {
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Bad",
                        "data": {"text": "not-a-number"},
                        "position": {"x": 100, "y": 100},
                    },
                    _int_to_string_node(its_id),
                ],
                "edges": [{"source": str_id, "target": its_id, "target_handle": "input"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    its_result = next((r for r in result["node_results"] if r["node_id"] == its_id), None)
    assert its_result is not None
    assert its_result["status"] == "error"
    assert "int to string" in (its_result.get("error") or "").lower()


def test_int_to_string_start_no_int_like_errors(client: TestClient):
    """Start with only boolean slot -> no int-like value."""
    start_id = "n_start_its_b"
    its_id = "n_its_b"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "ITS Start bool only",
            "graph": {
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "flag", "type": "boolean", "value": True}]},
                        "position": {"x": 50, "y": 100},
                    },
                    _int_to_string_node(its_id),
                ],
                "edges": [
                    {"source": start_id, "target": its_id, "source_handle": "flag", "target_handle": "input"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    its_result = next((r for r in result["node_results"] if r["node_id"] == its_id), None)
    assert its_result is not None
    assert its_result["status"] == "error"
    assert "boolean" in (its_result.get("error") or "").lower()


# ---------------------------------------------------------------------------
# Dictionary primitive — Start multi-wire merge (no LLM calls)
# ---------------------------------------------------------------------------


def test_start_int_slots_merge_into_dictionary_primitive(client: TestClient):
    """Multiple Start int handles wired to Dictionary items merge into one dict keyed by handle."""
    start_id = "n_start_sd"
    dict_id = "n_dict_sd"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Start ints to Dictionary merge",
            "graph": {
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {
                            "required_inputs": [
                                {"key": "min", "type": "int", "value": None},
                                {"key": "max", "type": "int", "value": None},
                                {"key": "quantity", "type": "int", "value": None},
                            ]
                        },
                        "position": {"x": 50, "y": 100},
                    },
                    {
                        "id": dict_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "Dict",
                        "data": {},
                        "position": {"x": 200, "y": 100},
                    },
                ],
                "edges": [
                    {"source": start_id, "target": dict_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": start_id, "target": dict_id, "source_handle": "min", "target_handle": "input"},
                    {"source": start_id, "target": dict_id, "source_handle": "max", "target_handle": "input"},
                    {"source": start_id, "target": dict_id, "source_handle": "quantity", "target_handle": "input"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(
        f"/api/v1/workflow-definitions/{workflow_id}/run",
        json={"input_overrides": {"min": 0, "max": 29, "quantity": 20}},
    )
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    step = next((r for r in result["node_results"] if r["node_id"] == dict_id), None)
    assert step is not None
    assert step["status"] == "ok"
    assert step.get("output", {}).get("kind") == "dictionary"
    assert step.get("output", {}).get("data") == {"min": 0, "max": 29, "quantity": 20}
    assert _resolved_inputs(step.get("details")).get("data") == {"min": 0, "max": 29, "quantity": 20}


def test_parallel_int_primitives_merge_into_dictionary_primitive_distinct_keys(client: TestClient):
    """Parallel Int nodes all use handle ``output``; merged dict gets one key per wire (suffix disambiguation)."""
    start_id = "n_start_pi"
    dict_id = "n_dict_pi"
    int_ids = ["n_int_pi_0", "n_int_pi_1", "n_int_pi_2", "n_int_pi_3"]
    vals = [10, 20, 30, 40]
    nodes = [
        {
            "id": start_id,
            "kind": "start",
            "label": "Start",
            "data": {"required_inputs": []},
            "position": {"x": 50, "y": 100},
        },
        {
            "id": dict_id,
            "kind": "primitive",
            "primitive_type": "dictionary",
            "label": "Dict",
            "data": {},
            "position": {"x": 200, "y": 100},
        },
    ]
    edges = [
        {"source": start_id, "target": dict_id, "source_handle": "signal_out", "target_handle": "trigger"},
    ]
    for i, nid in enumerate(int_ids):
        nodes.append(
            {
                "id": nid,
                "kind": "primitive",
                "primitive_type": "int",
                "label": f"I{i}",
                "data": {"value": vals[i]},
                "position": {"x": 120, "y": 60 + i * 40},
            },
        )
        edges.append({"source": nid, "target": dict_id, "source_handle": "output", "target_handle": "input"})

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Parallel ints to Dictionary", "graph": {"nodes": nodes, "edges": edges}},
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    step = next((r for r in result["node_results"] if r["node_id"] == dict_id), None)
    assert step is not None
    assert step["status"] == "ok"
    d = step.get("output", {}).get("data")
    assert d is not None
    assert len(d) == 4
    assert d["output"] == 10
    assert d[f"output_{int_ids[1]}"] == 20
    assert d[f"output_{int_ids[2]}"] == 30
    assert d[f"output_{int_ids[3]}"] == 40


# ---------------------------------------------------------------------------
# Dictionary value by key utility tests (no LLM calls)
# ---------------------------------------------------------------------------


_DICT_VAL_BY_KEY_FALLBACK_OMIT = object()


def _dictionary_value_by_key_node(
    node_id: str,
    *,
    output_value_type: str = "list",
    key_value: str = "",
    label: str = "Dictionary Value by Key",
    fallback_value=_DICT_VAL_BY_KEY_FALLBACK_OMIT,
):
    data = {
        "output_value_type": output_value_type,
        "required_inputs": [
            {"key": "key", "type": "string", "value": key_value},
            {"key": "dictionary", "type": "dictionary", "value": None},
            {"key": "fallback", "type": "any", "value": None},
        ],
    }
    if fallback_value is not _DICT_VAL_BY_KEY_FALLBACK_OMIT:
        data["fallback_value"] = fallback_value
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "dictionary_value_by_key",
        "label": label,
        "data": data,
        "position": {"x": 300, "y": 100},
    }


def _dictionary_set_value_by_key_node(
    node_id: str,
    *,
    key_value: str = "",
    dictionary_value=None,
    value_value=None,
    label: str = "Dictionary Set Value by Key",
):
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "dictionary_set_value_by_key",
        "label": label,
        "data": {
            "required_inputs": [
                {"key": "dictionary", "type": "dictionary", "value": dictionary_value},
                {"key": "key", "type": "string", "value": key_value},
                {"key": "value", "type": "any", "value": value_value},
            ],
        },
        "position": {"x": 300, "y": 100},
    }


def _read_document_property_node(
    node_id: str,
    *,
    output_value_type: str = "string",
    target_property: str = "body",
    label: str = "Read Document Property",
):
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "read_document_property",
        "label": label,
        "data": {
            "output_value_type": output_value_type,
            "required_inputs": [
                {"key": "target_property", "type": "string", "value": target_property},
                {"key": "document", "type": "document", "value": None},
            ],
        },
        "position": {"x": 300, "y": 100},
    }


def test_read_document_property_extracts_body(client: TestClient):
    """Document primitive wired to Read Document Property returns the body string."""
    name = f"doc_wf_{uuid.uuid4().hex[:8]}"
    body_text = "Line1\nLine2"
    doc_res = client.post(
        "/api/v1/documents/",
        json={"name": name, "description": "", "body": body_text},
    )
    assert doc_res.status_code == 201
    doc_id = doc_res.json()["id"]

    prim_id = "n_doc_prim"
    util_id = "n_read_doc"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Read document property test",
            "graph": {
                "nodes": [
                    {
                        "id": prim_id,
                        "kind": "primitive",
                        "primitive_type": "document",
                        "label": "Document",
                        "data": {"document_id": doc_id},
                        "position": {"x": 100, "y": 100},
                    },
                    _read_document_property_node(util_id, target_property="body"),
                ],
                "edges": [
                    {"source": prim_id, "target": util_id, "target_handle": "document"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    step = next((r for r in result["node_results"] if r["node_id"] == util_id), None)
    assert step is not None
    assert step["status"] == "ok"
    assert step.get("output", {}).get("kind") == "string"
    assert step.get("output", {}).get("text") == body_text


def test_document_primitive_to_simple_llm_user_prompt_sends_body_markdown(client: TestClient):
    """Document primitive wired to Simple LLM user_prompt passes document body (markdown) to the chat user message."""
    name = f"doc_llm_{uuid.uuid4().hex[:8]}"
    body_text = "## Body\n\nHello doc→LLM"
    doc_res = client.post(
        "/api/v1/documents/",
        json={"name": name, "description": "", "body": body_text},
    )
    assert doc_res.status_code == 201
    doc_id = doc_res.json()["id"]

    persona_id = _get_persona_id(client)
    prim_id = "n_doc_prim_llm"
    llm_node_id = "n_llm_doc"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Document primitive to SimpleLLM user_prompt",
            "graph": {
                "nodes": [
                    {
                        "id": prim_id,
                        "kind": "primitive",
                        "primitive_type": "document",
                        "label": "Document",
                        "data": {"document_id": doc_id},
                        "position": {"x": 100, "y": 100},
                    },
                    _simple_llm_node(llm_node_id, persona_id, user_prompt=None),
                ],
                "edges": [
                    {"source": prim_id, "target": llm_node_id, "target_handle": "user_prompt"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="ok",
        parsed=None,
        provider_name="lmstudio",
        usage=None,
    )

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    llm_result = next((r for r in result["node_results"] if r["node_id"] == llm_node_id), None)
    assert llm_result is not None
    assert llm_result["status"] == "ok"

    mock_instance.chat.assert_awaited()
    call_kw = mock_instance.chat.await_args
    messages = call_kw[0][0]
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == body_text

    details = llm_result.get("details", {})
    assert _resolved_inputs(details).get("user_prompt") == body_text


def test_dictionary_value_by_key_extracts_list(client: TestClient):
    """Dictionary primitive with key -> list output."""
    dict_id = "n_dict_dvbk"
    util_id = "n_dvbk_ok"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Dict value by key list",
            "graph": {
                "nodes": [
                    {
                        "id": dict_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "Dict",
                        "data": {"randomIntList": [1, 6, 4, 2, 1]},
                        "position": {"x": 100, "y": 100},
                    },
                    _dictionary_value_by_key_node(util_id, key_value="randomIntList"),
                ],
                "edges": [
                    {"source": dict_id, "target": util_id, "target_handle": "dictionary"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    step = next((r for r in result["node_results"] if r["node_id"] == util_id), None)
    assert step is not None
    assert step["status"] == "ok"
    assert step.get("output", {}).get("kind") == "list"
    assert step.get("output", {}).get("data") == [1, 6, 4, 2, 1]


def test_dictionary_value_by_key_missing_key_errors(client: TestClient):
    dict_id = "n_dict_miss"
    util_id = "n_dvbk_miss"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Dict value missing key",
            "graph": {
                "nodes": [
                    {
                        "id": dict_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "Dict",
                        "data": {"a": 1},
                        "position": {"x": 100, "y": 100},
                    },
                    _dictionary_value_by_key_node(util_id, key_value="missing"),
                ],
                "edges": [{"source": dict_id, "target": util_id, "target_handle": "dictionary"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] in ("ok", "partial")
    step = next((r for r in result["node_results"] if r["node_id"] == util_id), None)
    assert step is not None
    assert step["status"] == "error"
    assert "not present" in (step.get("error") or "").lower()
    ri = _resolved_inputs(step.get("details"))
    assert "a" in (ri.get("dictionary_keys") or [])
    assert ri.get("resolved_key") == "missing"


def test_dictionary_value_by_key_wrong_type_errors(client: TestClient):
    """Expect list but value is string -> error."""
    dict_id = "n_dict_wrong"
    util_id = "n_dvbk_wrong"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Dict value wrong type",
            "graph": {
                "nodes": [
                    {
                        "id": dict_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "Dict",
                        "data": {"x": "hello"},
                        "position": {"x": 100, "y": 100},
                    },
                    _dictionary_value_by_key_node(util_id, output_value_type="list", key_value="x"),
                ],
                "edges": [{"source": dict_id, "target": util_id, "target_handle": "dictionary"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    step = next((r for r in result["node_results"] if r["node_id"] == util_id), None)
    assert step is not None
    assert step["status"] == "error"
    assert "wrong type" in (step.get("error") or "").lower()


def test_dictionary_value_by_key_null_value_errors(client: TestClient):
    dict_id = "n_dict_null"
    util_id = "n_dvbk_null"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Dict value null",
            "graph": {
                "nodes": [
                    {
                        "id": dict_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "Dict",
                        "data": {"x": None},
                        "position": {"x": 100, "y": 100},
                    },
                    _dictionary_value_by_key_node(util_id, output_value_type="list", key_value="x"),
                ],
                "edges": [{"source": dict_id, "target": util_id, "target_handle": "dictionary"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    step = next((r for r in result["node_results"] if r["node_id"] == util_id), None)
    assert step is not None
    assert step["status"] == "error"
    assert "null" in (step.get("error") or "").lower()


def test_dictionary_value_by_key_missing_key_uses_static_fallback(client: TestClient):
    dict_id = "n_dict_fb_miss"
    util_id = "n_dvbk_fb1"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Dict dvbk missing key fallback",
            "graph": {
                "nodes": [
                    {
                        "id": dict_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "Dict",
                        "data": {"a": 1},
                        "position": {"x": 100, "y": 100},
                    },
                    _dictionary_value_by_key_node(
                        util_id,
                        output_value_type="list",
                        key_value="missing",
                        fallback_value=[9, 8],
                    ),
                ],
                "edges": [{"source": dict_id, "target": util_id, "target_handle": "dictionary"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    step = next((r for r in run_res.json()["node_results"] if r["node_id"] == util_id), None)
    assert step is not None
    assert step["status"] == "ok"
    assert step.get("output", {}).get("kind") == "list"
    assert step.get("output", {}).get("data") == [9, 8]
    ri = _resolved_inputs(step.get("details"))
    assert ri.get("use_fallback") is True
    assert ri.get("fallback_source") == "data"


def test_dictionary_value_by_key_null_uses_static_fallback(client: TestClient):
    dict_id = "n_dict_fb_null"
    util_id = "n_dvbk_fb2"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Dict dvbk null fallback",
            "graph": {
                "nodes": [
                    {
                        "id": dict_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "Dict",
                        "data": {"x": None},
                        "position": {"x": 100, "y": 100},
                    },
                    _dictionary_value_by_key_node(
                        util_id,
                        output_value_type="list",
                        key_value="x",
                        fallback_value=[1, 2, 3],
                    ),
                ],
                "edges": [{"source": dict_id, "target": util_id, "target_handle": "dictionary"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    step = next((r for r in run_res.json()["node_results"] if r["node_id"] == util_id), None)
    assert step is not None
    assert step["status"] == "ok"
    assert step.get("output", {}).get("data") == [1, 2, 3]


def test_dictionary_value_by_key_wrong_type_still_errors_with_fallback(client: TestClient):
    """Wrong JSON type at key: fallback is not used."""
    dict_id = "n_dict_fb_wrong"
    util_id = "n_dvbk_fb3"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Dict dvbk wrong type with fallback",
            "graph": {
                "nodes": [
                    {
                        "id": dict_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "Dict",
                        "data": {"x": "hello"},
                        "position": {"x": 100, "y": 100},
                    },
                    _dictionary_value_by_key_node(
                        util_id,
                        output_value_type="list",
                        key_value="x",
                        fallback_value=[0, 0],
                    ),
                ],
                "edges": [{"source": dict_id, "target": util_id, "target_handle": "dictionary"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    step = next((r for r in run_res.json()["node_results"] if r["node_id"] == util_id), None)
    assert step is not None
    assert step["status"] == "error"
    assert "wrong type" in (step.get("error") or "").lower()


def test_dictionary_value_by_key_static_fallback_in_required_inputs_only(client: TestClient):
    """``required_inputs`` fallback slot (no ``data.fallback_value``) supplies the value."""
    dict_id = "n_dict_ri_fb"
    util_id = "n_dvbk_ri"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Dict dvbk fallback in required_inputs only",
            "graph": {
                "nodes": [
                    {
                        "id": dict_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "Dict",
                        "data": {"a": 1},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": util_id,
                        "kind": "utility",
                        "utility_type": "dictionary_value_by_key",
                        "label": "DVBK",
                        "data": {
                            "output_value_type": "list",
                            "required_inputs": [
                                {"key": "key", "type": "string", "value": "missing_key"},
                                {"key": "dictionary", "type": "dictionary", "value": None},
                                {"key": "fallback", "type": "any", "value": [9, 9]},
                            ],
                        },
                        "position": {"x": 300, "y": 100},
                    },
                ],
                "edges": [
                    {"source": dict_id, "target": util_id, "target_handle": "dictionary"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    step = next((r for r in run_res.json()["node_results"] if r["node_id"] == util_id), None)
    assert step is not None
    assert step["status"] == "ok"
    assert step.get("output", {}).get("data") == [9, 9]
    ri = _resolved_inputs(step.get("details"))
    assert ri.get("use_fallback") is True
    assert ri.get("fallback_source") == "required_input"


def test_dictionary_value_by_key_wired_fallback_overrides_static(client: TestClient):
    dict_id = "n_dict_fb_w"
    list_id = "n_list_fb_w"
    util_id = "n_dvbk_fb4"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Dict dvbk wire fallback wins",
            "graph": {
                "nodes": [
                    {
                        "id": dict_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "Dict",
                        "data": {},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "Fb list",
                        "data": [7, 7, 7],
                        "position": {"x": 100, "y": 200},
                    },
                    _dictionary_value_by_key_node(
                        util_id,
                        key_value="k",
                        fallback_value=[0, 0],
                    ),
                ],
                "edges": [
                    {"source": dict_id, "target": util_id, "target_handle": "dictionary"},
                    {"source": list_id, "target": util_id, "target_handle": "fallback"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    step = next((r for r in run_res.json()["node_results"] if r["node_id"] == util_id), None)
    assert step is not None
    assert step["status"] == "ok"
    assert step.get("output", {}).get("data") == [7, 7, 7]
    ri = _resolved_inputs(step.get("details"))
    assert ri.get("fallback_source") == "wire"


def test_dictionary_set_value_by_key_overwrites_and_keeps_other_keys(client: TestClient):
    dict_id = "n_dict_dsvbk"
    util_id = "n_dsvbk1"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Dict set value by key overwrite",
            "graph": {
                "nodes": [
                    {
                        "id": dict_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "Dict",
                        "data": {"summaries": [0], "other": 1},
                        "position": {"x": 100, "y": 100},
                    },
                    _dictionary_set_value_by_key_node(
                        util_id,
                        key_value="summaries",
                        value_value=[1, 2, 3],
                    ),
                ],
                "edges": [{"source": dict_id, "target": util_id, "target_handle": "dictionary"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    step = next((r for r in result["node_results"] if r["node_id"] == util_id), None)
    assert step is not None
    assert step["status"] == "ok"
    assert step.get("output", {}).get("kind") == "dictionary"
    assert step.get("output", {}).get("data") == {"summaries": [1, 2, 3], "other": 1}


def test_dictionary_set_value_by_key_adds_new_key(client: TestClient):
    util_id = "n_dsvbk2"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Dict set new key",
            "graph": {
                "nodes": [
                    _dictionary_set_value_by_key_node(
                        util_id,
                        key_value="x",
                        dictionary_value={},
                        value_value="hello",
                    ),
                ],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    step = next((r for r in result["node_results"] if r["node_id"] == util_id), None)
    assert step is not None
    assert step["status"] == "ok"
    assert step.get("output", {}).get("data") == {"x": "hello"}


def test_dictionary_set_value_by_key_invalid_dictionary_input_errors(client: TestClient):
    str_id = "n_str_bad"
    util_id = "n_dsvbk_bad"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Dict set bad dict",
            "graph": {
                "nodes": [
                    {
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "S",
                        "data": {"text": "not-json"},
                        "position": {"x": 100, "y": 100},
                    },
                    _dictionary_set_value_by_key_node(util_id, key_value="k", value_value=1),
                ],
                "edges": [{"source": str_id, "target": util_id, "target_handle": "dictionary"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    step = next((r for r in run_res.json()["node_results"] if r["node_id"] == util_id), None)
    assert step is not None
    assert step["status"] == "error"
    assert "dictionary" in (step.get("error") or "").lower()


def test_dictionary_set_value_by_key_empty_key_errors(client: TestClient):
    util_id = "n_dsvbk_ek"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Dict set empty key",
            "graph": {
                "nodes": [
                    _dictionary_set_value_by_key_node(
                        util_id,
                        key_value="",
                        dictionary_value={"a": 1},
                        value_value=2,
                    ),
                ],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    step = next((r for r in run_res.json()["node_results"] if r["node_id"] == util_id), None)
    assert step is not None
    assert step["status"] == "error"
    assert "key" in (step.get("error") or "").lower()


def test_dictionary_set_value_by_key_value_wired_from_list_primitive(client: TestClient):
    dict_id = "n_dict_w"
    list_id = "n_list_w"
    util_id = "n_dsvbk_w"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Dict set wired list",
            "graph": {
                "nodes": [
                    {
                        "id": dict_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "D",
                        "data": {"a": 1},
                        "position": {"x": 50, "y": 100},
                    },
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "L",
                        "data": [9, 8],
                        "position": {"x": 50, "y": 200},
                    },
                    _dictionary_set_value_by_key_node(util_id, key_value="b"),
                ],
                "edges": [
                    {"source": dict_id, "target": util_id, "target_handle": "dictionary"},
                    {"source": list_id, "target": util_id, "target_handle": "value"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    step = next((r for r in result["node_results"] if r["node_id"] == util_id), None)
    assert step is not None
    assert step["status"] == "ok"
    assert step.get("output", {}).get("data") == {"a": 1, "b": [9, 8]}


# ---------------------------------------------------------------------------
# Prepend Text utility tests (no LLM calls)
# ---------------------------------------------------------------------------


def _prepend_text_node(
    node_id: str,
    target_string: str | None = None,
    text_to_prepend: str | None = None,
    add_additional_line: bool = False,
    label: str = "Prepend Text",
):
    """Prepend Text utility node."""
    required_inputs = [
        {"key": "target_string", "type": "string", "value": target_string},
        {"key": "text_to_prepend", "type": "string", "value": text_to_prepend},
    ]
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "prepend_text",
        "label": label,
        "data": {"required_inputs": required_inputs, "add_additional_line": add_additional_line},
        "position": {"x": 300, "y": 100},
    }


def test_prepend_text_utility_basic(client: TestClient):
    """Two string inputs, no additional line -> output is prepend + target."""
    pt_node_id = "n_pt_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Prepend Text Basic",
            "graph": {
                "nodes": [
                    _prepend_text_node(pt_node_id, target_string="World", text_to_prepend="Hello "),
                ],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    pt_result = next((r for r in result["node_results"] if r["node_id"] == pt_node_id), None)
    assert pt_result is not None
    assert pt_result["status"] == "ok"
    output = pt_result.get("output", {})
    assert output.get("kind") == "string"
    assert output.get("text") == "Hello World"


def test_prepend_text_utility_with_additional_line(client: TestClient):
    """Checkbox true -> blank line between prepended text and target."""
    pt_node_id = "n_pt_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Prepend Text With Line",
            "graph": {
                "nodes": [
                    _prepend_text_node(
                        pt_node_id, target_string="World", text_to_prepend="Hello", add_additional_line=True
                    ),
                ],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    pt_result = next((r for r in result["node_results"] if r["node_id"] == pt_node_id), None)
    assert pt_result is not None
    assert pt_result["status"] == "ok"
    output = pt_result.get("output", {})
    assert output.get("kind") == "string"
    assert output.get("text") == "Hello\n\nWorld"


def _message_utility_node(node_id: str, message: str | None = None, label: str = "Message"):
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "message",
        "label": label,
        "data": {"required_inputs": [{"key": "message", "type": "string", "value": message}]},
        "position": {"x": 300, "y": 100},
    }


def test_decision_action_primitive_emits_string(client: TestClient):
    """Decision action primitive outputs validated DecisionAction as string (for sandbox_decision_intent)."""
    da_id = "n_da_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Decision Action Primitive",
            "graph": {
                "nodes": [
                    {
                        "id": da_id,
                        "kind": "primitive",
                        "primitive_type": "decision_action",
                        "label": "Action",
                        "data": {"action": "sleep"},
                        "position": {"x": 100, "y": 100},
                    }
                ],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    step = next((r for r in result["node_results"] if r["node_id"] == da_id), None)
    assert step is not None
    assert step["status"] == "ok"
    out = step.get("output") or {}
    assert out.get("kind") == "string"
    assert out.get("text") == "sleep"


def test_sandbox_tick_primitive_emits_dictionary_from_overrides(client: TestClient):
    """sandbox_tick primitive outputs validated SandboxTickInput as dictionary (fan-out tick in graphs)."""
    from app.domain.sandbox.engine import initial_sandbox_state_clean
    from app.domain.schemas.sandbox import SandboxTickInput

    st = initial_sandbox_state_clean()
    tick = SandboxTickInput(tick=1, pet=st.pet, world=st.world, recent_actions=[]).model_dump(mode="json")
    node_id = "n_sandbox_tick_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Sandbox tick primitive",
            "graph": {
                "nodes": [
                    {
                        "id": node_id,
                        "kind": "primitive",
                        "primitive_type": "sandbox_tick",
                        "label": "Tick",
                        "data": {},
                        "position": {"x": 100, "y": 100},
                    }
                ],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(
        f"/api/v1/workflow-definitions/{workflow_id}/run",
        json={"input_overrides": {"sandbox_tick": tick}},
    )
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    step = next((r for r in result["node_results"] if r["node_id"] == node_id), None)
    assert step is not None
    assert step["status"] == "ok"
    out = step.get("output") or {}
    assert out.get("kind") == "dictionary"
    assert out.get("data", {}).get("tick") == 1


def test_message_utility_inline(client: TestClient):
    """Message utility surfaces text in details and emits empty string output (no downstream data)."""
    msg_id = "n_msg_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Message Inline",
            "graph": {
                "nodes": [_message_utility_node(msg_id, message="hello from agent")],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    step = next((r for r in result["node_results"] if r["node_id"] == msg_id), None)
    assert step is not None
    assert step["status"] == "ok"
    out = step.get("output") or {}
    assert out.get("kind") == "string"
    assert out.get("text") == ""
    det = step.get("details") or {}
    assert det.get("user_message") == "hello from agent"


def test_prepend_text_utility_from_upstream(client: TestClient):
    """Wire from String primitives -> output combines them."""
    str1_id = "n_str1"
    str2_id = "n_str2"
    pt_node_id = "n_pt_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Prepend Text From Upstream",
            "graph": {
                "nodes": [
                    {
                        "id": str1_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Target",
                        "data": {"text": "target"},
                        "position": {"x": 100, "y": 80},
                    },
                    {
                        "id": str2_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Prepend",
                        "data": {"text": "prefix-"},
                        "position": {"x": 100, "y": 120},
                    },
                    _prepend_text_node(pt_node_id),
                ],
                "edges": [
                    {"source": str1_id, "target": pt_node_id, "target_handle": "target_string"},
                    {"source": str2_id, "target": pt_node_id, "target_handle": "text_to_prepend"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    pt_result = next((r for r in result["node_results"] if r["node_id"] == pt_node_id), None)
    assert pt_result is not None
    assert pt_result["status"] == "ok"
    output = pt_result.get("output", {})
    assert output.get("kind") == "string"
    assert output.get("text") == "prefix-target"


# ---------------------------------------------------------------------------
# String Trunc utility tests (no LLM calls)
# ---------------------------------------------------------------------------


def _string_trunc_node(
    node_id: str,
    target_string: str | None = None,
    start_index: int | None = 0,
    end_index: int | None = -1,
    label: str = "String Trunc",
):
    return {
        "id": node_id,
        "kind": "utility",
        "utility_type": "string_trunc",
        "label": label,
        "data": {
            "required_inputs": [
                {"key": "target_string", "type": "string", "value": target_string},
                {"key": "start_index", "type": "int", "value": start_index},
                {"key": "end_index", "type": "int", "value": end_index},
            ]
        },
        "position": {"x": 300, "y": 100},
    }


def test_string_trunc_inclusive_basic(client: TestClient):
    nid = "n_st_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "String Trunc Inclusive",
            "graph": {
                "nodes": [
                    _string_trunc_node(nid, target_string="This is my target string", start_index=8, end_index=9),
                ],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    step = next((r for r in result["node_results"] if r["node_id"] == nid), None)
    assert step is not None and step["status"] == "ok"
    assert step.get("output", {}).get("text") == "my"


def test_string_trunc_end_negative_one(client: TestClient):
    nid = "n_st_002"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "String Trunc Tail",
            "graph": {
                "nodes": [
                    _string_trunc_node(
                        nid,
                        target_string="This is another test string",
                        start_index=5,
                        end_index=-1,
                    ),
                ],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    step = next((r for r in result["node_results"] if r["node_id"] == nid), None)
    assert step is not None and step["status"] == "ok"
    assert step.get("output", {}).get("text") == "is another test string"


def test_string_trunc_prefix_cap(client: TestClient):
    nid = "n_st_003"
    body = "x" * 800
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "String Trunc Cap",
            "graph": {
                "nodes": [_string_trunc_node(nid, target_string=body, start_index=0, end_index=500)],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    step = next((r for r in result["node_results"] if r["node_id"] == nid), None)
    assert step is not None and step["status"] == "ok"
    assert step.get("output", {}).get("text") == "x" * 501


def test_string_trunc_resolved_inputs_omits_huge_target(client: TestClient):
    nid = "n_st_big"
    body = "y" * 5000
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "String Trunc Big Resolved",
            "graph": {
                "nodes": [_string_trunc_node(nid, target_string=body, start_index=0, end_index=10)],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    step = next((r for r in run_res.json()["node_results"] if r["node_id"] == nid), None)
    assert step is not None and step["status"] == "ok"
    det = step.get("details") or {}
    ri = det.get("resolved_inputs") or {}
    assert ri.get("target_truncated") is True
    assert ri.get("target_prefix") == "y" * 200
    assert "target_string" not in ri
    assert ri.get("target_chars") == 5000


def test_string_trunc_inverted_range_errors(client: TestClient):
    nid = "n_st_inv"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "String Trunc Inverted",
            "graph": {
                "nodes": [_string_trunc_node(nid, target_string="abc", start_index=5, end_index=2)],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    step = next((r for r in run_res.json()["node_results"] if r["node_id"] == nid), None)
    assert step is not None and step["status"] == "error"
    assert "end_index" in (step.get("error") or "")


def test_string_trunc_negative_start_errors(client: TestClient):
    nid = "n_st_ns"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "String Trunc Neg Start",
            "graph": {
                "nodes": [_string_trunc_node(nid, target_string="abc", start_index=-1, end_index=1)],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    step = next((r for r in run_res.json()["node_results"] if r["node_id"] == nid), None)
    assert step is not None and step["status"] == "error"
    assert "start_index" in (step.get("error") or "")


def test_string_trunc_end_lt_minus_one_errors(client: TestClient):
    nid = "n_st_e2"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "String Trunc Bad End",
            "graph": {
                "nodes": [_string_trunc_node(nid, target_string="abc", start_index=0, end_index=-2)],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    step = next((r for r in run_res.json()["node_results"] if r["node_id"] == nid), None)
    assert step is not None and step["status"] == "error"
    assert "end_index" in (step.get("error") or "")


def test_string_trunc_non_int_start_errors(client: TestClient):
    nid = "n_st_bad"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "String Trunc Bad Int",
            "graph": {
                "nodes": [
                    {
                        "id": nid,
                        "kind": "utility",
                        "utility_type": "string_trunc",
                        "label": "ST",
                        "data": {
                            "required_inputs": [
                                {"key": "target_string", "type": "string", "value": "x"},
                                {"key": "start_index", "type": "int", "value": "nope"},
                                {"key": "end_index", "type": "int", "value": 0},
                            ]
                        },
                        "position": {"x": 0, "y": 0},
                    }
                ],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    step = next((r for r in run_res.json()["node_results"] if r["node_id"] == nid), None)
    assert step is not None and step["status"] == "error"
    assert "start_index" in (step.get("error") or "")


def test_string_trunc_from_upstream(client: TestClient):
    str_id = "n_str_st"
    nid = "n_st_up"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "String Trunc Upstream",
            "graph": {
                "nodes": [
                    {
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "S",
                        "data": {"text": "abcdefghij"},
                        "position": {"x": 50, "y": 50},
                    },
                    _string_trunc_node(nid, target_string=None, start_index=2, end_index=4),
                ],
                "edges": [{"source": str_id, "target": nid, "target_handle": "target_string"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    step = next((r for r in run_res.json()["node_results"] if r["node_id"] == nid), None)
    assert step is not None and step["status"] == "ok"
    assert step.get("output", {}).get("text") == "cde"


def test_parallel_sibling_llm_calls_execute_concurrently(client: TestClient):
    """
    When multiple SimpleLLMCall nodes share the same upstream source (parallel siblings),
    they should execute concurrently via asyncio.gather, not sequentially.
    Total elapsed time should be ~0.1s (parallel) not ~0.3s (sequential).
    """
    persona_id = _get_persona_id(client)
    string_node_id = "n_string_001"
    llm_a_id = "n_llm_a"
    llm_b_id = "n_llm_b"
    llm_c_id = "n_llm_c"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Parallel Siblings LLM Test",
            "graph": {
                "nodes": [
                    {
                        "id": string_node_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "String Input",
                        "data": {"text": "Hello from String"},
                        "position": {"x": 100, "y": 100},
                    },
                    _simple_llm_node(llm_a_id, persona_id, label="LLM A"),
                    _simple_llm_node(llm_b_id, persona_id, label="LLM B"),
                    _simple_llm_node(llm_c_id, persona_id, label="LLM C"),
                ],
                "edges": [
                    {"source": string_node_id, "target": llm_a_id, "target_handle": "user_prompt"},
                    {"source": string_node_id, "target": llm_b_id, "target_handle": "user_prompt"},
                    {"source": string_node_id, "target": llm_c_id, "target_handle": "user_prompt"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="Mock LLM response",
        parsed=None,
        provider_name="lmstudio",
        usage=None,
    )

    async def mock_chat_with_delay(*args, **kwargs):
        await asyncio.sleep(0.1)
        return mock_response

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(side_effect=mock_chat_with_delay)
        MockProvider.return_value = mock_instance

        start = time.monotonic()
        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        elapsed = time.monotonic() - start

    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    assert mock_instance.chat.call_count == 3
    assert elapsed < 0.25, (
        f"Parallel execution should complete in ~0.1s (3 parallel calls). "
        f"Sequential would take ~0.3s. Got {elapsed:.2f}s"
    )

    for node_id in llm_a_id, llm_b_id, llm_c_id:
        node_result = next((r for r in result["node_results"] if r["node_id"] == node_id), None)
        assert node_result is not None, f"Node {node_id} should have a result"
        assert node_result["status"] == "ok", f"Node {node_id} should succeed"


def test_parallel_simple_llm_nodes_each_get_same_resolved_lmstudio_token(client: TestClient):
    """
    Regression: parallel waves run several Simple LLM nodes concurrently. User.api_keys must be
    read under the executor's async lock so each LMStudioProvider gets the same decrypted Bearer
    token (Session misuse previously caused intermittent wrong/missing auth).
    """
    expected_token = "parallel-regression-lmstudio-bearer-token"
    assert (
        client.put(
            "/api/v1/auth/me",
            json={"api_keys": {"lmstudio_api_key": expected_token}},
        ).status_code
        == 200
    )

    persona_id = _get_persona_id(client)
    string_node_id = "n_string_pr"
    llm_a_id = "n_llm_pr_a"
    llm_b_id = "n_llm_pr_b"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Parallel LLM token regression",
            "graph": {
                "nodes": [
                    {
                        "id": string_node_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "String Input",
                        "data": {"text": "Hello"},
                        "position": {"x": 100, "y": 100},
                    },
                    _simple_llm_node(llm_a_id, persona_id, label="LLM A"),
                    _simple_llm_node(llm_b_id, persona_id, label="LLM B"),
                ],
                "edges": [
                    {"source": string_node_id, "target": llm_a_id, "target_handle": "user_prompt"},
                    {"source": string_node_id, "target": llm_b_id, "target_handle": "user_prompt"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="ok",
        parsed=None,
        provider_name="lmstudio",
        usage=None,
    )

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] == "ok"
    assert MockProvider.call_count == 2
    for c in MockProvider.call_args_list:
        assert c.kwargs.get("api_key") == expected_token

    for node_id in llm_a_id, llm_b_id:
        node_result = next((r for r in result["node_results"] if r["node_id"] == node_id), None)
        assert node_result is not None
        assert node_result["status"] == "ok"


def test_simple_llm_empty_exception_returns_informative_error(client: TestClient):
    """
    When SimpleLLMCall raises an exception with empty str(e), the error message
    should include the exception type name so the user gets useful feedback.
    """
    persona_id = _get_persona_id(client)
    llm_node_id = "n_llm_001"

    class EmptyMessageError(Exception):
        def __str__(self) -> str:
            return ""

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Empty Exception Test",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "user_input", "type": "string", "value": "Hi"}]},
                        "position": {"x": 50, "y": 100},
                    },
                    _simple_llm_node(llm_node_id, persona_id),
                ],
                "edges": [
                    {
                        "source": "n_start",
                        "target": llm_node_id,
                        "source_handle": "user_input",
                        "target_handle": "user_prompt",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(side_effect=EmptyMessageError())
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] in ("partial", "error")
    llm_result = next((r for r in result["node_results"] if r["node_id"] == llm_node_id), None)
    assert llm_result is not None
    assert llm_result["status"] == "error"
    assert llm_result["error"]
    assert "EmptyMessageError" in llm_result["error"]
    assert "no details available" in llm_result["error"]


def test_workflow_node_error_includes_sub_workflow_details(client: TestClient):
    """
    When a Workflow node's sub-workflow fails, the Workflow node result should
    include details.sub_workflow_node_results and sub_workflow_node_labels
    so the user can see which step failed.
    """
    persona_id = _get_persona_id(client)
    sub_llm_id = "n_llm_sub"

    sub_wf_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Failing Sub Workflow",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start_sub",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "user_input", "type": "string", "value": "Hi"}]},
                        "position": {"x": 50, "y": 100},
                    },
                    _simple_llm_node(sub_llm_id, persona_id, label="Sub LLM"),
                    {
                        "id": "n_stop_sub",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start_sub",
                        "target": sub_llm_id,
                        "source_handle": "user_input",
                        "target_handle": "user_prompt",
                    },
                    {"source": sub_llm_id, "target": "n_stop_sub"},
                ],
            },
        },
    )
    assert sub_wf_res.status_code == 201
    sub_wf_id = sub_wf_res.json()["id"]

    parent_wf_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Parent With Failing Sub",
            "graph": {
                "nodes": [
                    {
                        "id": "n_wf_001",
                        "kind": "workflow",
                        "label": "Sub Workflow",
                        "data": {"workflow_id": sub_wf_id},
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": "n_stop_parent",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_wf_001", "target": "n_stop_parent", "source_handle": "output"},
                ],
            },
        },
    )
    assert parent_wf_res.status_code == 201
    parent_wf_id = parent_wf_res.json()["id"]

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(side_effect=RuntimeError("LM Studio connection refused"))
        MockProvider.return_value = mock_instance

        run_res = client.post(f"/api/v1/workflow-definitions/{parent_wf_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

    assert result["status"] in ("partial", "error")
    wf_result = next((r for r in result["node_results"] if r["node_id"] == "n_wf_001"), None)
    assert wf_result is not None
    assert wf_result["status"] == "error"
    assert wf_result["error"]
    details = wf_result.get("details", {})
    assert "sub_workflow_node_results" in details
    assert "sub_workflow_node_labels" in details
    assert details.get("sub_workflow_name") == "Failing Sub Workflow"
    sub_results = details["sub_workflow_node_results"]
    assert len(sub_results) >= 2
    failed_llm = next((r for r in sub_results if r["node_id"] == sub_llm_id), None)
    assert failed_llm is not None
    assert failed_llm["status"] == "error"
    assert "connection refused" in failed_llm.get("error", "").lower()
    labels = details["sub_workflow_node_labels"]
    assert labels.get(sub_llm_id) == "Sub LLM"


# ---------------------------------------------------------------------------
# Basic Conditional control node tests
# ---------------------------------------------------------------------------


def test_basic_conditional_true_branch_only(client: TestClient):
    """
    Conditional with condition='true' (UI) -> only True-branch node runs.
    False-branch node does not appear in results.
    """
    cond_id = "n_cond_001"
    true_string_id = "n_true_001"
    false_string_id = "n_false_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Conditional True Branch",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _basic_conditional_node(cond_id, condition_value="true"),
                    {
                        "id": true_string_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "True Branch",
                        "data": {"text": "from-true"},
                        "position": {"x": 400, "y": 50},
                    },
                    {
                        "id": false_string_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "False Branch",
                        "data": {"text": "from-false"},
                        "position": {"x": 400, "y": 150},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": cond_id},
                    {"source": cond_id, "target": true_string_id, "source_handle": "true"},
                    {"source": cond_id, "target": false_string_id, "source_handle": "false"},
                    {"source": true_string_id, "target": "n_stop"},
                    {"source": false_string_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    node_ids = {r["node_id"] for r in result["node_results"]}
    assert cond_id in node_ids
    assert true_string_id in node_ids
    assert false_string_id not in node_ids, "False branch should not run when condition is true"
    stop_result = next(r for r in result["node_results"] if r["node_id"] == "n_stop")
    assert stop_result["output"]["text"] == "from-true"


def test_basic_conditional_false_branch_only(client: TestClient):
    """
    Condition='false' -> only False-branch node runs.
    """
    cond_id = "n_cond_001"
    true_string_id = "n_true_001"
    false_string_id = "n_false_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Conditional False Branch",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _basic_conditional_node(cond_id, condition_value="false"),
                    {
                        "id": true_string_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "True Branch",
                        "data": {"text": "from-true"},
                        "position": {"x": 400, "y": 50},
                    },
                    {
                        "id": false_string_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "False Branch",
                        "data": {"text": "from-false"},
                        "position": {"x": 400, "y": 150},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": cond_id},
                    {"source": cond_id, "target": true_string_id, "source_handle": "true"},
                    {"source": cond_id, "target": false_string_id, "source_handle": "false"},
                    {"source": true_string_id, "target": "n_stop"},
                    {"source": false_string_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    node_ids = {r["node_id"] for r in result["node_results"]}
    assert cond_id in node_ids
    assert true_string_id not in node_ids, "True branch should not run when condition is false"
    assert false_string_id in node_ids
    stop_result = next(r for r in result["node_results"] if r["node_id"] == "n_stop")
    assert stop_result["output"]["text"] == "from-false"


def test_basic_conditional_wired_condition(client: TestClient):
    """
    String node with "true" -> Conditional -> True branch executes.
    """
    string_id = "n_string_001"
    cond_id = "n_cond_001"
    true_string_id = "n_true_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Conditional Wired Condition",
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
                        "id": string_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Condition",
                        "data": {"text": "true"},
                        "position": {"x": 150, "y": 100},
                    },
                    _basic_conditional_node(cond_id, condition_value=None),
                    {
                        "id": true_string_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "True Branch",
                        "data": {"text": "executed"},
                        "position": {"x": 400, "y": 100},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 550, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": string_id},
                    {"source": string_id, "target": cond_id, "target_handle": "condition"},
                    {"source": cond_id, "target": true_string_id, "source_handle": "true"},
                    {"source": true_string_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    assert any(r["node_id"] == true_string_id for r in result["node_results"])
    stop_result = next(r for r in result["node_results"] if r["node_id"] == "n_stop")
    assert stop_result["output"]["text"] == "executed"


def test_basic_conditional_empty_condition_false(client: TestClient):
    """
    No condition, no wire -> treat as false.
    """
    cond_id = "n_cond_001"
    true_string_id = "n_true_001"
    false_string_id = "n_false_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Conditional Empty Condition",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _basic_conditional_node(cond_id, condition_value=""),
                    {
                        "id": true_string_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "True Branch",
                        "data": {"text": "from-true"},
                        "position": {"x": 400, "y": 50},
                    },
                    {
                        "id": false_string_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "False Branch",
                        "data": {"text": "from-false"},
                        "position": {"x": 400, "y": 150},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": cond_id},
                    {"source": cond_id, "target": true_string_id, "source_handle": "true"},
                    {"source": cond_id, "target": false_string_id, "source_handle": "false"},
                    {"source": true_string_id, "target": "n_stop"},
                    {"source": false_string_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    node_ids = {r["node_id"] for r in result["node_results"]}
    assert false_string_id in node_ids
    assert true_string_id not in node_ids


def test_basic_conditional_bool_like_values(client: TestClient):
    """
    "yes", "1", "YES" -> true; "no", "0" -> false.
    """
    for val, expect_true in [("yes", True), ("1", True), ("YES", True), ("no", False), ("0", False)]:
        cond_id = "n_cond"
        true_id = "n_true"
        false_id = "n_false"

        workflow_res = client.post(
            "/api/v1/workflow-definitions/",
            json={
                "name": f"Conditional {val}",
                "graph": {
                    "nodes": [
                        {
                            "id": "n_start",
                            "kind": "start",
                            "label": "Start",
                            "data": {"required_inputs": []},
                            "position": {"x": 50, "y": 100},
                        },
                        _basic_conditional_node(cond_id, condition_value=val),
                        {
                            "id": true_id,
                            "kind": "primitive",
                            "primitive_type": "string",
                            "label": "True",
                            "data": {"text": "T"},
                            "position": {"x": 300, "y": 50},
                        },
                        {
                            "id": false_id,
                            "kind": "primitive",
                            "primitive_type": "string",
                            "label": "False",
                            "data": {"text": "F"},
                            "position": {"x": 300, "y": 150},
                        },
                        {
                            "id": "n_stop",
                            "kind": "stop",
                            "label": "Stop",
                            "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                            "position": {"x": 500, "y": 100},
                        },
                    ],
                    "edges": [
                        {"source": "n_start", "target": cond_id},
                        {"source": cond_id, "target": true_id, "source_handle": "true"},
                        {"source": cond_id, "target": false_id, "source_handle": "false"},
                        {"source": true_id, "target": "n_stop"},
                        {"source": false_id, "target": "n_stop"},
                    ],
                },
            },
        )
        assert workflow_res.status_code == 201
        workflow_id = workflow_res.json()["id"]

        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
        assert run_res.status_code == 200
        result = run_res.json()

        assert result["status"] == "ok"
        node_ids = {r["node_id"] for r in result["node_results"]}
        if expect_true:
            assert true_id in node_ids, f"Expected true branch for condition={val!r}"
            assert false_id not in node_ids
        else:
            assert false_id in node_ids, f"Expected false branch for condition={val!r}"
            assert true_id not in node_ids


def test_basic_conditional_both_branches_stop(client: TestClient):
    """
    Conditional -> True -> Stop; Conditional -> False -> Stop.
    Only one Stop receives output based on condition.
    """
    cond_id = "n_cond"
    stop_true_id = "n_stop_true"
    stop_false_id = "n_stop_false"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Conditional Both Stops",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _basic_conditional_node(cond_id, condition_value="true"),
                    {
                        "id": "n_str_true",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "T",
                        "data": {"text": "true-result"},
                        "position": {"x": 300, "y": 50},
                    },
                    {
                        "id": "n_str_false",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "F",
                        "data": {"text": "false-result"},
                        "position": {"x": 300, "y": 150},
                    },
                    {
                        "id": stop_true_id,
                        "kind": "stop",
                        "label": "Stop True",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 500, "y": 50},
                    },
                    {
                        "id": stop_false_id,
                        "kind": "stop",
                        "label": "Stop False",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 500, "y": 150},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": cond_id},
                    {"source": cond_id, "target": "n_str_true", "source_handle": "true"},
                    {"source": cond_id, "target": "n_str_false", "source_handle": "false"},
                    {"source": "n_str_true", "target": stop_true_id},
                    {"source": "n_str_false", "target": stop_false_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    node_ids = {r["node_id"] for r in result["node_results"]}
    assert stop_true_id in node_ids
    assert stop_false_id not in node_ids
    stop_true_result = next(r for r in result["node_results"] if r["node_id"] == stop_true_id)
    assert stop_true_result["output"]["text"] == "true-result"


# ---------------------------------------------------------------------------
# Is? control node tests
# ---------------------------------------------------------------------------


def test_is_control_equal_strings_true_branch(client: TestClient):
    """Is? with input_a='hello', input_b='hello' -> True branch only."""
    is_id = "n_is_001"
    true_id = "n_true_001"
    false_id = "n_false_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Is Equal Strings",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _is_node(is_id, input_a="hello", input_b="hello"),
                    {
                        "id": true_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "True",
                        "data": {"text": "equal"},
                        "position": {"x": 400, "y": 50},
                    },
                    {
                        "id": false_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "False",
                        "data": {"text": "not-equal"},
                        "position": {"x": 400, "y": 150},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": is_id},
                    {"source": is_id, "target": true_id, "source_handle": "true"},
                    {"source": is_id, "target": false_id, "source_handle": "false"},
                    {"source": true_id, "target": "n_stop"},
                    {"source": false_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    node_ids = {r["node_id"] for r in result["node_results"]}
    assert is_id in node_ids
    assert true_id in node_ids
    assert false_id not in node_ids
    stop_result = next(r for r in result["node_results"] if r["node_id"] == "n_stop")
    assert stop_result["output"]["text"] == "equal"


def test_is_control_unequal_strings_false_branch(client: TestClient):
    """Is? with input_a='a', input_b='b' -> False branch only."""
    is_id = "n_is_001"
    true_id = "n_true_001"
    false_id = "n_false_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Is Unequal Strings",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _is_node(is_id, input_a="a", input_b="b"),
                    {
                        "id": true_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "True",
                        "data": {"text": "equal"},
                        "position": {"x": 400, "y": 50},
                    },
                    {
                        "id": false_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "False",
                        "data": {"text": "not-equal"},
                        "position": {"x": 400, "y": 150},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": is_id},
                    {"source": is_id, "target": true_id, "source_handle": "true"},
                    {"source": is_id, "target": false_id, "source_handle": "false"},
                    {"source": true_id, "target": "n_stop"},
                    {"source": false_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    node_ids = {r["node_id"] for r in result["node_results"]}
    assert is_id in node_ids
    assert true_id not in node_ids
    assert false_id in node_ids
    stop_result = next(r for r in result["node_results"] if r["node_id"] == "n_stop")
    assert stop_result["output"]["text"] == "not-equal"


def test_is_empty_empty_list_true_branch(client: TestClient):
    """Is Empty? with [] -> True branch only."""
    empty_id = "n_list_empty"
    ie_id = "n_is_empty"
    true_id = "n_true"
    false_id = "n_false"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Is Empty list true",
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
                        "id": empty_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "Empty",
                        "data": [],
                        "position": {"x": 150, "y": 100},
                    },
                    _is_empty_node(ie_id, value=None),
                    {
                        "id": true_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "True",
                        "data": {"text": "was-empty"},
                        "position": {"x": 450, "y": 50},
                    },
                    {
                        "id": false_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "False",
                        "data": {"text": "not-empty"},
                        "position": {"x": 450, "y": 150},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 650, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": ie_id},
                    {"source": empty_id, "target": ie_id, "target_handle": "value"},
                    {"source": ie_id, "target": true_id, "source_handle": "true"},
                    {"source": ie_id, "target": false_id, "source_handle": "false"},
                    {"source": true_id, "target": "n_stop"},
                    {"source": false_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    assert true_id in {r["node_id"] for r in result["node_results"]}
    assert false_id not in {r["node_id"] for r in result["node_results"]}
    stop_result = next(r for r in result["node_results"] if r["node_id"] == "n_stop")
    assert stop_result["output"]["text"] == "was-empty"


def test_is_empty_nonempty_list_false_branch(client: TestClient):
    """Is Empty? with [1] -> False branch only."""
    list_id = "n_list_one"
    ie_id = "n_is_empty"
    true_id = "n_true"
    false_id = "n_false"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Is Empty list false",
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
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "One",
                        "data": [1],
                        "position": {"x": 150, "y": 100},
                    },
                    _is_empty_node(ie_id, value=None),
                    {
                        "id": true_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "True",
                        "data": {"text": "was-empty"},
                        "position": {"x": 450, "y": 50},
                    },
                    {
                        "id": false_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "False",
                        "data": {"text": "not-empty"},
                        "position": {"x": 450, "y": 150},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 650, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": ie_id},
                    {"source": list_id, "target": ie_id, "target_handle": "value"},
                    {"source": ie_id, "target": true_id, "source_handle": "true"},
                    {"source": ie_id, "target": false_id, "source_handle": "false"},
                    {"source": true_id, "target": "n_stop"},
                    {"source": false_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    assert false_id in {r["node_id"] for r in result["node_results"]}
    assert true_id not in {r["node_id"] for r in result["node_results"]}
    stop_result = next(r for r in result["node_results"] if r["node_id"] == "n_stop")
    assert stop_result["output"]["text"] == "not-empty"


def test_is_empty_empty_dict_true_branch(client: TestClient):
    """Is Empty? with {} -> True branch."""
    dict_id = "n_dict_empty"
    ie_id = "n_is_empty"
    true_id = "n_true"
    false_id = "n_false"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Is Empty dict true",
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
                        "id": dict_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "Empty dict",
                        "data": {},
                        "position": {"x": 150, "y": 100},
                    },
                    _is_empty_node(ie_id, value=None),
                    {
                        "id": true_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "True",
                        "data": {"text": "was-empty"},
                        "position": {"x": 450, "y": 50},
                    },
                    {
                        "id": false_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "False",
                        "data": {"text": "not-empty"},
                        "position": {"x": 450, "y": 150},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 650, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": ie_id},
                    {"source": dict_id, "target": ie_id, "target_handle": "value"},
                    {"source": ie_id, "target": true_id, "source_handle": "true"},
                    {"source": ie_id, "target": false_id, "source_handle": "false"},
                    {"source": true_id, "target": "n_stop"},
                    {"source": false_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    assert true_id in {r["node_id"] for r in result["node_results"]}
    stop_result = next(r for r in result["node_results"] if r["node_id"] == "n_stop")
    assert stop_result["output"]["text"] == "was-empty"


def test_is_empty_invalid_type_errors(client: TestClient):
    """Is Empty? with a bare string value errors."""
    str_id = "n_str_bad"
    ie_id = "n_is_empty"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Is Empty invalid",
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
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Bad",
                        "data": {"text": "hello"},
                        "position": {"x": 150, "y": 100},
                    },
                    _is_empty_node(ie_id, value=None),
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 650, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": ie_id},
                    {"source": str_id, "target": ie_id, "target_handle": "value"},
                    {"source": ie_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] in ("partial", "error")
    ie_res = next(r for r in result["node_results"] if r["node_id"] == ie_id)
    assert ie_res["status"] == "error"
    assert "is_empty" in (ie_res.get("error") or "").lower()


def test_is_control_equal_lists_true_branch(client: TestClient):
    """Wire two List nodes with same data -> True branch."""
    list_a_id = "n_list_a"
    list_b_id = "n_list_b"
    is_id = "n_is_001"
    true_id = "n_true_001"
    false_id = "n_false_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Is Equal Lists",
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
                        "id": list_a_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List A",
                        "data": [1, 2, 3],
                        "position": {"x": 150, "y": 50},
                    },
                    {
                        "id": list_b_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List B",
                        "data": [1, 2, 3],
                        "position": {"x": 150, "y": 150},
                    },
                    _is_node(is_id, input_a=None, input_b=None),
                    {
                        "id": true_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "True",
                        "data": {"text": "equal"},
                        "position": {"x": 450, "y": 50},
                    },
                    {
                        "id": false_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "False",
                        "data": {"text": "not-equal"},
                        "position": {"x": 450, "y": 150},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 650, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": is_id},
                    {"source": list_a_id, "target": is_id, "target_handle": "input_a"},
                    {"source": list_b_id, "target": is_id, "target_handle": "input_b"},
                    {"source": is_id, "target": true_id, "source_handle": "true"},
                    {"source": is_id, "target": false_id, "source_handle": "false"},
                    {"source": true_id, "target": "n_stop"},
                    {"source": false_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    node_ids = {r["node_id"] for r in result["node_results"]}
    assert true_id in node_ids
    assert false_id not in node_ids
    stop_result = next(r for r in result["node_results"] if r["node_id"] == "n_stop")
    assert stop_result["output"]["text"] == "equal"


def test_is_control_unequal_lists_false_branch(client: TestClient):
    """Wire two List nodes with different data -> False branch."""
    list_a_id = "n_list_a"
    list_b_id = "n_list_b"
    is_id = "n_is_001"
    true_id = "n_true_001"
    false_id = "n_false_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Is Unequal Lists",
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
                        "id": list_a_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List A",
                        "data": [1, 2],
                        "position": {"x": 150, "y": 50},
                    },
                    {
                        "id": list_b_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List B",
                        "data": [1, 2, 3],
                        "position": {"x": 150, "y": 150},
                    },
                    _is_node(is_id, input_a=None, input_b=None),
                    {
                        "id": true_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "True",
                        "data": {"text": "equal"},
                        "position": {"x": 450, "y": 50},
                    },
                    {
                        "id": false_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "False",
                        "data": {"text": "not-equal"},
                        "position": {"x": 450, "y": 150},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 650, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": is_id},
                    {"source": list_a_id, "target": is_id, "target_handle": "input_a"},
                    {"source": list_b_id, "target": is_id, "target_handle": "input_b"},
                    {"source": is_id, "target": true_id, "source_handle": "true"},
                    {"source": is_id, "target": false_id, "source_handle": "false"},
                    {"source": true_id, "target": "n_stop"},
                    {"source": false_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    node_ids = {r["node_id"] for r in result["node_results"]}
    assert true_id not in node_ids
    assert false_id in node_ids
    stop_result = next(r for r in result["node_results"] if r["node_id"] == "n_stop")
    assert stop_result["output"]["text"] == "not-equal"


def test_is_control_wired_inputs(client: TestClient):
    """String 'x' -> input_a, String 'x' -> input_b -> True branch."""
    str_a_id = "n_str_a"
    str_b_id = "n_str_b"
    is_id = "n_is_001"
    true_id = "n_true_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Is Wired Inputs",
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
                        "id": str_a_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "A",
                        "data": {"text": "x"},
                        "position": {"x": 150, "y": 80},
                    },
                    {
                        "id": str_b_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "B",
                        "data": {"text": "x"},
                        "position": {"x": 150, "y": 120},
                    },
                    _is_node(is_id, input_a=None, input_b=None),
                    {
                        "id": true_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "True",
                        "data": {"text": "match"},
                        "position": {"x": 400, "y": 100},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 550, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": is_id},
                    {"source": str_a_id, "target": is_id, "target_handle": "input_a"},
                    {"source": str_b_id, "target": is_id, "target_handle": "input_b"},
                    {"source": is_id, "target": true_id, "source_handle": "true"},
                    {"source": true_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    assert any(r["node_id"] == true_id for r in result["node_results"])
    stop_result = next(r for r in result["node_results"] if r["node_id"] == "n_stop")
    assert stop_result["output"]["text"] == "match"


def test_is_control_mixed_types_false(client: TestClient):
    """String vs list -> False branch."""
    str_id = "n_str"
    list_id = "n_list"
    is_id = "n_is_001"
    true_id = "n_true_001"
    false_id = "n_false_001"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Is Mixed Types",
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
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Str",
                        "data": {"text": "x"},
                        "position": {"x": 150, "y": 50},
                    },
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": [],
                        "position": {"x": 150, "y": 150},
                    },
                    _is_node(is_id, input_a=None, input_b=None),
                    {
                        "id": true_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "True",
                        "data": {"text": "equal"},
                        "position": {"x": 450, "y": 50},
                    },
                    {
                        "id": false_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "False",
                        "data": {"text": "not-equal"},
                        "position": {"x": 450, "y": 150},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 650, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": is_id},
                    {"source": str_id, "target": is_id, "target_handle": "input_a"},
                    {"source": list_id, "target": is_id, "target_handle": "input_b"},
                    {"source": is_id, "target": true_id, "source_handle": "true"},
                    {"source": is_id, "target": false_id, "source_handle": "false"},
                    {"source": true_id, "target": "n_stop"},
                    {"source": false_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    node_ids = {r["node_id"] for r in result["node_results"]}
    assert true_id not in node_ids
    assert false_id in node_ids
    stop_result = next(r for r in result["node_results"] if r["node_id"] == "n_stop")
    assert stop_result["output"]["text"] == "not-equal"


def test_is_control_both_branches_to_stop(client: TestClient):
    """Is? -> True -> Stop; Is? -> False -> Stop. Only one Stop runs."""
    is_id = "n_is"
    stop_true_id = "n_stop_true"
    stop_false_id = "n_stop_false"

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Is Both Branches",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _is_node(is_id, input_a="same", input_b="same"),
                    {
                        "id": "n_str_true",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "T",
                        "data": {"text": "true-result"},
                        "position": {"x": 300, "y": 50},
                    },
                    {
                        "id": "n_str_false",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "F",
                        "data": {"text": "false-result"},
                        "position": {"x": 300, "y": 150},
                    },
                    {
                        "id": stop_true_id,
                        "kind": "stop",
                        "label": "Stop True",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 500, "y": 50},
                    },
                    {
                        "id": stop_false_id,
                        "kind": "stop",
                        "label": "Stop False",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 500, "y": 150},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": is_id},
                    {"source": is_id, "target": "n_str_true", "source_handle": "true"},
                    {"source": is_id, "target": "n_str_false", "source_handle": "false"},
                    {"source": "n_str_true", "target": stop_true_id},
                    {"source": "n_str_false", "target": stop_false_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    node_ids = {r["node_id"] for r in result["node_results"]}
    assert stop_true_id in node_ids
    assert stop_false_id not in node_ids
    stop_true_result = next(r for r in result["node_results"] if r["node_id"] == stop_true_id)
    assert stop_true_result["output"]["text"] == "true-result"


# ---------------------------------------------------------------------------
# Gt?, Lt?, Gte?, Lte?, And, Or, Xor control node tests
# ---------------------------------------------------------------------------


def test_gt_control_true_branch(client: TestClient):
    """Gt? with 5 > 3 -> True branch."""
    gt_id = "n_gt"
    true_id, false_id = "n_true", "n_false"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Gt True",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _comparison_node(gt_id, "gt", 5, 3, "Gt?"),
                    {
                        "id": true_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "T",
                        "data": {"text": "yes"},
                        "position": {"x": 400, "y": 50},
                    },
                    {
                        "id": false_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "F",
                        "data": {"text": "no"},
                        "position": {"x": 400, "y": 150},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": gt_id},
                    {"source": gt_id, "target": true_id, "source_handle": "true"},
                    {"source": gt_id, "target": false_id, "source_handle": "false"},
                    {"source": true_id, "target": "n_stop"},
                    {"source": false_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    assert true_id in {r["node_id"] for r in result["node_results"]}
    assert false_id not in {r["node_id"] for r in result["node_results"]}
    stop_result = next(r for r in result["node_results"] if r["node_id"] == "n_stop")
    assert stop_result["output"]["text"] == "yes"


def test_gt_control_signal_out_triggers_downstream(client: TestClient):
    """Branching controls emit signal_out; executor schedules signal_out → trigger targets."""
    gt_id = "n_gt"
    add_id = "n_add"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Gt Signal Out",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _comparison_node(gt_id, "gt", 5, 3, "Gt?"),
                    {
                        "id": "n_true",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "T",
                        "data": {"text": "branch"},
                        "position": {"x": 400, "y": 50},
                    },
                    _binary_int_utility_node(add_id, "add_ints", 10, 20, "Add"),
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": gt_id},
                    {"source": gt_id, "target": "n_true", "source_handle": "true"},
                    {"source": "n_true", "target": "n_stop"},
                    {"source": gt_id, "target": add_id, "source_handle": "signal_out", "target_handle": "trigger"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    assert add_id in {r["node_id"] for r in result["node_results"]}
    add_r = next(r for r in result["node_results"] if r["node_id"] == add_id)
    assert add_r["output"]["value"] == 30


def test_lt_control_false_branch(client: TestClient):
    """Lt? with 3 < 5 -> True; 3 < 2 -> False."""
    lt_id = "n_lt"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Lt False",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _comparison_node(lt_id, "lt", 3, 2, "Lt?"),
                    {
                        "id": "n_true",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "T",
                        "data": {"text": "yes"},
                        "position": {"x": 400, "y": 50},
                    },
                    {
                        "id": "n_false",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "F",
                        "data": {"text": "no"},
                        "position": {"x": 400, "y": 150},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": lt_id},
                    {"source": lt_id, "target": "n_true", "source_handle": "true"},
                    {"source": lt_id, "target": "n_false", "source_handle": "false"},
                    {"source": "n_false", "target": "n_stop"},
                    {"source": "n_true", "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    assert "n_false" in {r["node_id"] for r in result["node_results"]}
    assert "n_true" not in {r["node_id"] for r in result["node_results"]}
    stop_result = next(r for r in result["node_results"] if r["node_id"] == "n_stop")
    assert stop_result["output"]["text"] == "no"


def test_and_control_output(client: TestClient):
    """And with true and true -> true."""
    and_id = "n_and"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "And True",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _logical_node(and_id, "and", True, True, "And"),
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "boolean"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [{"source": "n_start", "target": and_id}, {"source": and_id, "target": "n_stop"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    and_result = next(r for r in result["node_results"] if r["node_id"] == and_id)
    assert and_result["output"]["value"] is True


def test_or_control_output(client: TestClient):
    """Or with false or true -> true."""
    or_id = "n_or"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Or True",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _logical_node(or_id, "or", False, True, "Or"),
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "boolean"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [{"source": "n_start", "target": or_id}, {"source": or_id, "target": "n_stop"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    or_result = next(r for r in result["node_results"] if r["node_id"] == or_id)
    assert or_result["output"]["value"] is True


def test_xor_control_output(client: TestClient):
    """Xor with true and false -> true; true and true -> false."""
    xor_id = "n_xor"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Xor",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _logical_node(xor_id, "xor", True, False, "Xor"),
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "boolean"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [{"source": "n_start", "target": xor_id}, {"source": xor_id, "target": "n_stop"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    xor_result = next(r for r in result["node_results"] if r["node_id"] == xor_id)
    assert xor_result["output"]["value"] is True


def test_not_control_inverts_boolean(client: TestClient):
    """Not control: NOT true -> false."""
    not_id = "n_not"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Not",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _not_control_node(not_id, True, "Not"),
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "boolean"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [{"source": "n_start", "target": not_id}, {"source": not_id, "target": "n_stop"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    nr = next(r for r in result["node_results"] if r["node_id"] == not_id)
    assert nr["output"]["value"] is False


def test_between_control_true_and_false_branch(client: TestClient):
    """Between: 2 <= 5 <= 10 -> true branch only."""
    bet_id = "n_bet"
    true_id, false_id = "n_true", "n_false"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Between",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _between_control_node(bet_id, 2, 5, 10, "Between"),
                    {
                        "id": true_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "T",
                        "data": {"text": "in"},
                        "position": {"x": 400, "y": 50},
                    },
                    {
                        "id": false_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "F",
                        "data": {"text": "out"},
                        "position": {"x": 400, "y": 150},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": bet_id},
                    {"source": bet_id, "target": true_id, "source_handle": "true"},
                    {"source": bet_id, "target": false_id, "source_handle": "false"},
                    {"source": true_id, "target": "n_stop"},
                    {"source": false_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    assert true_id in {r["node_id"] for r in result["node_results"]}
    assert false_id not in {r["node_id"] for r in result["node_results"]}


def test_between_control_low_gt_high_errors(client: TestClient):
    bet_id = "n_bet"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Between Bad",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _between_control_node(bet_id, 10, 5, 2, "Between"),
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": bet_id},
                    {"source": bet_id, "target": "n_stop", "source_handle": "true"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "partial"
    bet_result = next(r for r in result["node_results"] if r["node_id"] == bet_id)
    assert bet_result["status"] == "error"
    assert "low" in (bet_result.get("error") or "").lower()


def test_add_ints_and_divide_ints_utility(client: TestClient):
    add_id, div_id = "n_add", "n_div"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Int Math",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _binary_int_utility_node(add_id, "add_ints", 2, 3, "Add"),
                    _binary_int_utility_node(div_id, "divide_ints", -7, 3, "Div"),
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "a", "type": "int"}, {"key": "b", "type": "int"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": add_id},
                    {"source": "n_start", "target": div_id},
                    {"source": add_id, "target": "n_stop", "target_handle": "a"},
                    {"source": div_id, "target": "n_stop", "target_handle": "b"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    add_r = next(r for r in result["node_results"] if r["node_id"] == add_id)
    div_r = next(r for r in result["node_results"] if r["node_id"] == div_id)
    assert add_r["output"]["value"] == 5
    assert div_r["output"]["value"] == -2


def test_divide_ints_zero_errors(client: TestClient):
    div_id = "n_div"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Div0",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _binary_int_utility_node(div_id, "divide_ints", 1, 0, "Div"),
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [{"source": "n_start", "target": div_id}, {"source": div_id, "target": "n_stop"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "partial"
    div_r = next(r for r in result["node_results"] if r["node_id"] == div_id)
    assert div_r["status"] == "error"


def test_modulo_ints_zero_errors(client: TestClient):
    mid = "n_mod"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Mod0",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _binary_int_utility_node(mid, "modulo_ints", 5, 0, "Mod"),
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [{"source": "n_start", "target": mid}, {"source": mid, "target": "n_stop"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "partial"
    mod_r = next(r for r in result["node_results"] if r["node_id"] == mid)
    assert mod_r["status"] == "error"


def test_min_max_ints_utility(client: TestClient):
    min_id, max_id = "n_min", "n_max"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "MinMax",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _binary_int_utility_node(min_id, "min_ints", 3, 7, "Min"),
                    _binary_int_utility_node(max_id, "max_ints", 3, 7, "Max"),
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [{"source": "n_start", "target": min_id}, {"source": min_id, "target": "n_stop"}],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    min_r = next(r for r in result["node_results"] if r["node_id"] == min_id)
    assert min_r["output"]["value"] == 3

    workflow_res2 = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "MaxOnly",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 50, "y": 100},
                    },
                    _binary_int_utility_node("n_max2", "max_ints", 3, 7, "Max"),
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [{"source": "n_start", "target": "n_max2"}, {"source": "n_max2", "target": "n_stop"}],
            },
        },
    )
    assert workflow_res2.status_code == 201
    run_res2 = client.post(f"/api/v1/workflow-definitions/{workflow_res2.json()['id']}/run")
    assert run_res2.status_code == 200
    result2 = run_res2.json()
    assert result2["status"] == "ok"
    max_r = next(r for r in result2["node_results"] if r["node_id"] == "n_max2")
    assert max_r["output"]["value"] == 7


# ---------------------------------------------------------------------------
# Boolean primitive, Int primitive, Len from List utility tests
# ---------------------------------------------------------------------------


def test_boolean_primitive_static_value(client: TestClient):
    """Boolean primitive with value=true produces BooleanNodeOutput with value True."""
    bool_id = "n_bool_001"
    stop_id = "n_stop_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Boolean Static Test",
            "graph": {
                "nodes": [
                    {
                        "id": bool_id,
                        "kind": "primitive",
                        "primitive_type": "boolean",
                        "label": "Boolean",
                        "data": {"value": True},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "boolean"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [
                    {"source": bool_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    bool_result = next((r for r in result["node_results"] if r["node_id"] == bool_id), None)
    assert bool_result is not None
    assert bool_result["status"] == "ok"
    assert bool_result["output"]["kind"] == "boolean"
    assert bool_result["output"]["value"] is True

    stop_result = next((r for r in result["node_results"] if r["node_id"] == stop_id), None)
    assert stop_result is not None
    assert stop_result["output"]["kind"] == "boolean"
    assert stop_result["output"]["value"] is True


def test_boolean_primitive_wired_from_upstream(client: TestClient):
    """Boolean wired from another Boolean passes through."""
    bool1_id = "n_bool_001"
    bool2_id = "n_bool_002"
    stop_id = "n_stop_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Boolean Wired Test",
            "graph": {
                "nodes": [
                    {
                        "id": bool1_id,
                        "kind": "primitive",
                        "primitive_type": "boolean",
                        "label": "B1",
                        "data": {"value": True},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": bool2_id,
                        "kind": "primitive",
                        "primitive_type": "boolean",
                        "label": "B2",
                        "data": {"value": False},
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "boolean"}]},
                        "position": {"x": 500, "y": 100},
                    },
                ],
                "edges": [
                    {"source": bool1_id, "target": bool2_id},
                    {"source": bool2_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    bool2_result = next((r for r in result["node_results"] if r["node_id"] == bool2_id), None)
    assert bool2_result is not None
    assert bool2_result["output"]["kind"] == "boolean"
    assert bool2_result["output"]["value"] is True


def test_int_primitive_static_value(client: TestClient):
    """Int primitive with value=42 produces IntNodeOutput with value 42."""
    int_id = "n_int_001"
    stop_id = "n_stop_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Int Static Test",
            "graph": {
                "nodes": [
                    {
                        "id": int_id,
                        "kind": "primitive",
                        "primitive_type": "int",
                        "label": "Int",
                        "data": {"value": 42},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [
                    {"source": int_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    int_result = next((r for r in result["node_results"] if r["node_id"] == int_id), None)
    assert int_result is not None
    assert int_result["output"]["kind"] == "int"
    assert int_result["output"]["value"] == 42

    stop_result = next((r for r in result["node_results"] if r["node_id"] == stop_id), None)
    assert stop_result is not None
    assert stop_result["output"]["kind"] == "int"
    assert stop_result["output"]["value"] == 42


def test_datetime_primitive_static_value(client: TestClient):
    """DateTime primitive with valid RFC3339 iso produces DateTimeNodeOutput."""
    dt_id = "n_dt_001"
    stop_id = "n_stop_001"
    iso = "2026-03-01T15:00:00Z"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "DateTime Static Test",
            "graph": {
                "nodes": [
                    {
                        "id": dt_id,
                        "kind": "primitive",
                        "primitive_type": "datetime",
                        "label": "DateTime",
                        "data": {"iso": iso},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "datetime"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [
                    {"source": dt_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    dt_result = next((r for r in result["node_results"] if r["node_id"] == dt_id), None)
    assert dt_result is not None
    assert dt_result["output"]["kind"] == "datetime"
    assert dt_result["output"]["iso"] == iso

    stop_result = next((r for r in result["node_results"] if r["node_id"] == stop_id), None)
    assert stop_result is not None
    assert stop_result["output"]["kind"] == "datetime"
    assert stop_result["output"]["iso"] == iso


def test_datetime_primitive_use_now_normalized_utc(client: TestClient):
    """DateTime with use_now emits patched UTC now as normalized RFC3339."""
    from app.domain.workflow_executor import helpers as wf_helpers

    dt_id = "n_dt_now"
    stop_id = "n_stop_001"
    fixed = datetime(2026, 3, 10, 8, 15, 0, tzinfo=timezone.utc)
    expected_iso = "2026-03-10T08:15:00Z"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "DateTime use_now Test",
            "graph": {
                "nodes": [
                    {
                        "id": dt_id,
                        "kind": "primitive",
                        "primitive_type": "datetime",
                        "label": "DateTime",
                        "data": {"iso": None, "use_now": True},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "datetime"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [{"source": dt_id, "target": stop_id}],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    with patch.object(wf_helpers, "utc_now_for_workflow_execution", return_value=fixed):
        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    dt_result = next((r for r in result["node_results"] if r["node_id"] == dt_id), None)
    assert dt_result is not None
    assert dt_result["output"]["iso"] == expected_iso


def test_datetime_primitive_use_now_on_node_root(client: TestClient):
    """Root-level use_now (outside data) is merged at parse time."""
    from app.domain.workflow_executor import helpers as wf_helpers

    dt_id = "n_dt_root"
    stop_id = "n_stop_root"
    fixed = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
    expected_iso = "2026-04-01T10:00:00Z"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "DateTime use_now root Test",
            "graph": {
                "nodes": [
                    {
                        "id": dt_id,
                        "kind": "primitive",
                        "primitive_type": "datetime",
                        "label": "DateTime",
                        "use_now": True,
                        "data": {"iso": None},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "datetime"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [{"source": dt_id, "target": stop_id}],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    with patch.object(wf_helpers, "utc_now_for_workflow_execution", return_value=fixed):
        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    dt_result = next((r for r in result["node_results"] if r["node_id"] == dt_id), None)
    assert dt_result is not None
    assert dt_result["output"]["iso"] == expected_iso


def test_datetime_primitive_use_now_camel_case_in_data(client: TestClient):
    """data.useNow is normalized to use_now."""
    from app.domain.workflow_executor import helpers as wf_helpers

    dt_id = "n_dt_camel"
    stop_id = "n_stop_camel"
    fixed = datetime(2026, 5, 2, 15, 30, 0, tzinfo=timezone.utc)
    expected_iso = "2026-05-02T15:30:00Z"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "DateTime useNow Test",
            "graph": {
                "nodes": [
                    {
                        "id": dt_id,
                        "kind": "primitive",
                        "primitive_type": "datetime",
                        "label": "DateTime",
                        "data": {"iso": None, "useNow": True},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "datetime"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [{"source": dt_id, "target": stop_id}],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    with patch.object(wf_helpers, "utc_now_for_workflow_execution", return_value=fixed):
        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    dt_result = next((r for r in result["node_results"] if r["node_id"] == dt_id), None)
    assert dt_result is not None
    assert dt_result["output"]["iso"] == expected_iso


def test_datetime_primitive_upstream_wins_over_use_now(client: TestClient):
    """Wired upstream datetime/string overrides use_now on the DateTime primitive."""
    from app.domain.workflow_executor import helpers as wf_helpers

    str_id = "n_str"
    dt_id = "n_dt"
    stop_id = "n_stop"
    wired_iso = "2026-01-01T12:00:00Z"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "DateTime upstream vs use_now",
            "graph": {
                "nodes": [
                    {
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Str",
                        "data": {"text": wired_iso},
                        "position": {"x": 50, "y": 100},
                    },
                    {
                        "id": dt_id,
                        "kind": "primitive",
                        "primitive_type": "datetime",
                        "label": "DateTime",
                        "data": {"iso": None, "use_now": True},
                        "position": {"x": 200, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "datetime"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [
                    {"source": str_id, "target": dt_id, "target_handle": "input"},
                    {"source": dt_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    wrong = datetime(2099, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    with patch.object(wf_helpers, "utc_now_for_workflow_execution", return_value=wrong):
        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    dt_result = next((r for r in result["node_results"] if r["node_id"] == dt_id), None)
    assert dt_result is not None
    assert dt_result["output"]["iso"] == wired_iso


def test_add_days_negative_days(client: TestClient):
    """add_days shifts a wired static datetime by negative whole days."""
    dt_id = "n_dt"
    add_id = "n_add"
    stop_id = "n_stop"
    iso_in = "2026-03-10T12:00:00Z"
    iso_out = "2026-03-05T12:00:00Z"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Add days negative",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 100},
                    },
                    {
                        "id": dt_id,
                        "kind": "primitive",
                        "primitive_type": "datetime",
                        "label": "DateTime",
                        "data": {"iso": iso_in},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": add_id,
                        "kind": "utility",
                        "utility_type": "add_days",
                        "label": "Add days",
                        "data": {
                            "required_inputs": [
                                {"key": "input", "type": "datetime", "value": None},
                                {"key": "days", "type": "int", "value": -5},
                            ],
                        },
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "datetime"}]},
                        "position": {"x": 500, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": dt_id},
                    {"source": "n_start", "target": add_id},
                    {"source": dt_id, "target": add_id, "source_handle": "output", "target_handle": "input"},
                    {"source": add_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    add_r = next(r for r in result["node_results"] if r["node_id"] == add_id)
    assert add_r["output"]["kind"] == "datetime"
    assert add_r["output"]["iso"] == iso_out


def test_add_days_invalid_input_errors(client: TestClient):
    add_id = "n_add"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Add days bad input",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 100},
                    },
                    {
                        "id": add_id,
                        "kind": "utility",
                        "utility_type": "add_days",
                        "label": "Add days",
                        "data": {
                            "required_inputs": [
                                {"key": "input", "type": "datetime", "value": "not-rfc3339"},
                                {"key": "days", "type": "int", "value": 1},
                            ],
                        },
                        "position": {"x": 200, "y": 100},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "datetime"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": add_id},
                    {"source": add_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "partial"
    add_r = next(r for r in result["node_results"] if r["node_id"] == add_id)
    assert add_r["status"] == "error"


def test_add_days_after_use_now_datetime(client: TestClient):
    """Chain DateTime use_now with add_days -1."""
    from app.domain.workflow_executor import helpers as wf_helpers

    dt_id = "n_dt"
    add_id = "n_add"
    stop_id = "n_stop"
    fixed = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    expected = "2026-03-09T12:00:00Z"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "use_now add_days",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 100},
                    },
                    {
                        "id": dt_id,
                        "kind": "primitive",
                        "primitive_type": "datetime",
                        "label": "DateTime",
                        "data": {"iso": None, "use_now": True},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": add_id,
                        "kind": "utility",
                        "utility_type": "add_days",
                        "label": "Add days",
                        "data": {
                            "required_inputs": [
                                {"key": "input", "type": "datetime", "value": None},
                                {"key": "days", "type": "int", "value": -1},
                            ],
                        },
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "datetime"}]},
                        "position": {"x": 500, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": dt_id},
                    {"source": "n_start", "target": add_id},
                    {"source": dt_id, "target": add_id, "source_handle": "output", "target_handle": "input"},
                    {"source": add_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    with patch.object(wf_helpers, "utc_now_for_workflow_execution", return_value=fixed):
        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    add_r = next(r for r in result["node_results"] if r["node_id"] == add_id)
    assert add_r["output"]["iso"] == expected


def test_start_node_datetime_input_resolved(client: TestClient):
    """Start required_inputs datetime slot is normalized and present in outputs."""
    start_id = "n_start_001"
    stop_id = "n_stop_001"
    iso = "2026-06-15T12:30:00Z"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Start DateTime Test",
            "graph": {
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {
                            "required_inputs": [
                                {"key": "after", "type": "datetime", "value": iso},
                            ],
                        },
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [
                    {"source": start_id, "source_handle": "after", "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    start_res = next((r for r in result["node_results"] if r["node_id"] == start_id), None)
    assert start_res is not None
    out = start_res["output"]
    assert out["kind"] == "start"
    assert out["outputs"]["after"] == iso


def test_int_primitive_wired_from_upstream(client: TestClient):
    """Int wired from Len from List passes through."""
    list_id = "n_list_001"
    len_id = "n_len_001"
    int_id = "n_int_001"
    stop_id = "n_stop_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Int From Len Test",
            "graph": {
                "nodes": [
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": [1, 2, 3],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": len_id,
                        "kind": "utility",
                        "utility_type": "len_from_list",
                        "label": "Len",
                        "data": {},
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": int_id,
                        "kind": "primitive",
                        "primitive_type": "int",
                        "label": "Int",
                        "data": {"value": 0},
                        "position": {"x": 500, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 700, "y": 100},
                    },
                ],
                "edges": [
                    {"source": list_id, "target": len_id, "target_handle": "list"},
                    {"source": len_id, "target": int_id},
                    {"source": int_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    int_result = next((r for r in result["node_results"] if r["node_id"] == int_id), None)
    assert int_result is not None
    assert int_result["output"]["kind"] == "int"
    assert int_result["output"]["value"] == 3


def test_len_from_list_returns_length(client: TestClient):
    """List [1,2,3] -> Len from List -> output is 3."""
    list_id = "n_list_001"
    len_id = "n_len_001"
    stop_id = "n_stop_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Len From List Test",
            "graph": {
                "nodes": [
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": [1, 2, 3],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": len_id,
                        "kind": "utility",
                        "utility_type": "len_from_list",
                        "label": "Len",
                        "data": {},
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 500, "y": 100},
                    },
                ],
                "edges": [
                    {"source": list_id, "target": len_id, "target_handle": "list"},
                    {"source": len_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    len_result = next((r for r in result["node_results"] if r["node_id"] == len_id), None)
    assert len_result is not None
    assert len_result["output"]["kind"] == "int"
    assert len_result["output"]["value"] == 3
    stop_result = next((r for r in result["node_results"] if r["node_id"] == stop_id), None)
    assert stop_result["output"]["kind"] == "int"
    assert stop_result["output"]["value"] == 3


def test_random_item_from_list_returns_picked_element(client: TestClient, monkeypatch):
    """With deterministic index 0, output matches first list element."""
    monkeypatch.setattr(
        "app.domain.workflow_executor.executor.secrets.randbelow",
        lambda n: 0,
    )
    list_id = "n_list_rand"
    util_id = "n_rand_001"
    stop_id = "n_stop_rand"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Random Item From List",
            "graph": {
                "nodes": [
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": ["a", "b", "c"],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": util_id,
                        "kind": "utility",
                        "utility_type": "random_item_from_list",
                        "label": "Random",
                        "data": {},
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 500, "y": 100},
                    },
                ],
                "edges": [
                    {"source": list_id, "target": util_id, "target_handle": "list"},
                    {"source": util_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u = next((r for r in result["node_results"] if r["node_id"] == util_id), None)
    assert u is not None
    assert u["output"]["kind"] == "string"
    assert u["output"]["text"] == "a"
    assert u.get("details", {}).get("resolved_inputs", {}).get("picked_index") == 0


def test_random_item_from_list_empty_list_errors(client: TestClient):
    list_id = "n_list_empty"
    util_id = "n_rand_empty"
    stop_id = "n_stop_empty"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Random Item Empty",
            "graph": {
                "nodes": [
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": [],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": util_id,
                        "kind": "utility",
                        "utility_type": "random_item_from_list",
                        "label": "Random",
                        "data": {},
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 500, "y": 100},
                    },
                ],
                "edges": [
                    {"source": list_id, "target": util_id, "target_handle": "list"},
                    {"source": util_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] in ("ok", "partial", "error")
    u = next((r for r in result["node_results"] if r["node_id"] == util_id), None)
    assert u is not None
    assert u["status"] == "error"
    assert "empty" in u["error"].lower()


def test_len_from_list_empty_list(client: TestClient):
    """List [] -> Len from List -> output is 0."""
    list_id = "n_list_001"
    len_id = "n_len_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Len Empty List",
            "graph": {
                "nodes": [
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": [],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": len_id,
                        "kind": "utility",
                        "utility_type": "len_from_list",
                        "label": "Len",
                        "data": {},
                        "position": {"x": 300, "y": 100},
                    },
                ],
                "edges": [
                    {"source": list_id, "target": len_id, "target_handle": "list"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    len_result = next((r for r in result["node_results"] if r["node_id"] == len_id), None)
    assert len_result is not None
    assert len_result["output"]["value"] == 0


def test_workflow_node_outputs_list_to_len_from_list(client: TestClient):
    """Workflow node with sub-workflow Stop type list -> Len from List gets correct length."""
    sub_wf_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Sub List",
            "graph": {
                "nodes": [
                    {
                        "id": "n_list_sub",
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": [{"x": 1}, {"x": 2}, {"x": 3}],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": "n_stop_sub",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "list"}]},
                        "position": {"x": 300, "y": 100},
                    },
                ],
                "edges": [{"source": "n_list_sub", "target": "n_stop_sub"}],
            },
        },
    )
    assert sub_wf_res.status_code == 201
    sub_wf_id = sub_wf_res.json()["id"]

    parent_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Parent Workflow List to Len",
            "graph": {
                "nodes": [
                    {
                        "id": "n_wf",
                        "kind": "workflow",
                        "label": "Sub",
                        "data": {"workflow_id": sub_wf_id},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": "n_len",
                        "kind": "utility",
                        "utility_type": "len_from_list",
                        "label": "Len",
                        "data": {},
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 500, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_wf", "target": "n_len", "source_handle": "output"},
                    {"source": "n_len", "target": "n_stop"},
                ],
            },
        },
    )
    assert parent_res.status_code == 201
    parent_id = parent_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{parent_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    len_result = next((r for r in result["node_results"] if r["node_id"] == "n_len"), None)
    assert len_result is not None
    assert len_result["output"]["value"] == 3


def test_len_from_list_wired_list(client: TestClient):
    """Wire List primitive to Len from List -> correct length."""
    list_id = "n_list_001"
    len_id = "n_len_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Len Wired List",
            "graph": {
                "nodes": [
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": ["a", "b", "c", "d"],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": len_id,
                        "kind": "utility",
                        "utility_type": "len_from_list",
                        "label": "Len",
                        "data": {},
                        "position": {"x": 300, "y": 100},
                    },
                ],
                "edges": [
                    {"source": list_id, "target": len_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    len_result = next((r for r in result["node_results"] if r["node_id"] == len_id), None)
    assert len_result is not None
    assert len_result["output"]["value"] == 4


def test_list_item_by_index_valid_index(client: TestClient):
    """List Item by Index with valid index returns correct item."""
    list_id = "n_list_001"
    item_id = "n_item_001"
    stop_id = "n_stop_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "List Item By Index Valid",
            "graph": {
                "nodes": [
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": ["a", "b", "c"],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": item_id,
                        "kind": "utility",
                        "utility_type": "list_item_by_index",
                        "label": "Item",
                        "data": {
                            "required_inputs": [
                                {"key": "index", "type": "int", "value": 1},
                                {"key": "list", "type": "list", "value": None},
                            ]
                        },
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 500, "y": 100},
                    },
                ],
                "edges": [
                    {"source": list_id, "target": item_id, "target_handle": "list"},
                    {"source": item_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    for nr in result.get("node_results", []):
        if nr["status"] != "ok":
            raise AssertionError(f"Node {nr['node_id']} failed: {nr.get('error')}")
    assert result["status"] == "ok"
    item_result = next((r for r in result["node_results"] if r["node_id"] == item_id), None)
    assert item_result is not None
    assert item_result["output"]["kind"] == "string"
    assert item_result["output"]["text"] == "b"
    stop_result = next((r for r in result["node_results"] if r["node_id"] == stop_id), None)
    assert stop_result["output"]["text"] == "b"


def test_list_item_by_index_out_of_bounds_negative(client: TestClient):
    """List Item by Index with negative index returns error."""
    list_id = "n_list_001"
    item_id = "n_item_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "List Item By Index Negative",
            "graph": {
                "nodes": [
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": ["a", "b"],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": item_id,
                        "kind": "utility",
                        "utility_type": "list_item_by_index",
                        "label": "Item",
                        "data": {
                            "required_inputs": [
                                {"key": "index", "type": "int", "value": -1},
                                {"key": "list", "type": "list", "value": None},
                            ]
                        },
                        "position": {"x": 300, "y": 100},
                    },
                ],
                "edges": [
                    {"source": list_id, "target": item_id, "target_handle": "list"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] in ("ok", "partial")
    item_result = next((r for r in result["node_results"] if r["node_id"] == item_id), None)
    assert item_result is not None
    assert item_result["status"] == "error"
    assert "out of bounds" in item_result["error"].lower()
    assert "non-negative" in item_result["error"].lower()


def test_list_item_by_index_out_of_bounds_too_large(client: TestClient):
    """List Item by Index with index >= len(list) returns error."""
    list_id = "n_list_001"
    item_id = "n_item_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "List Item By Index Too Large",
            "graph": {
                "nodes": [
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": ["a", "b"],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": item_id,
                        "kind": "utility",
                        "utility_type": "list_item_by_index",
                        "label": "Item",
                        "data": {
                            "required_inputs": [
                                {"key": "index", "type": "int", "value": 5},
                                {"key": "list", "type": "list", "value": None},
                            ]
                        },
                        "position": {"x": 300, "y": 100},
                    },
                ],
                "edges": [
                    {"source": list_id, "target": item_id, "target_handle": "list"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] in ("ok", "partial")
    item_result = next((r for r in result["node_results"] if r["node_id"] == item_id), None)
    assert item_result is not None
    assert item_result["status"] == "error"
    assert "out of bounds" in item_result["error"].lower()
    ri = _resolved_inputs(item_result.get("details"))
    assert ri.get("index") == 5
    assert ri.get("list") == ["a", "b"]


def test_list_item_by_index_wired_index_overrides_stored_zero(client: TestClient):
    """When index is wired from Int, upstream value wins over stored 0 in node."""
    list_id = "n_list_001"
    int_id = "n_int_001"
    item_id = "n_item_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "List Item Wired Index Overrides Zero",
            "graph": {
                "nodes": [
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": ["a", "b", "c"],
                        "position": {"x": 100, "y": 50},
                    },
                    {
                        "id": int_id,
                        "kind": "primitive",
                        "primitive_type": "int",
                        "label": "Index",
                        "data": {"value": 2},
                        "position": {"x": 100, "y": 150},
                    },
                    {
                        "id": item_id,
                        "kind": "utility",
                        "utility_type": "list_item_by_index",
                        "label": "Item",
                        "data": {
                            "required_inputs": [
                                {"key": "index", "type": "int", "value": 0},
                                {"key": "list", "type": "list", "value": None},
                            ]
                        },
                        "position": {"x": 300, "y": 100},
                    },
                ],
                "edges": [
                    {"source": list_id, "target": item_id, "target_handle": "list"},
                    {"source": int_id, "target": item_id, "target_handle": "index"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    item_result = next((r for r in result["node_results"] if r["node_id"] == item_id), None)
    assert item_result is not None
    assert item_result["output"]["kind"] == "string"
    assert item_result["output"]["text"] == "c"


def test_list_item_by_index_wired_inputs(client: TestClient):
    """List Item by Index with index and list from upstream nodes."""
    list_id = "n_list_001"
    int_id = "n_int_001"
    item_id = "n_item_001"
    stop_id = "n_stop_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "List Item By Index Wired",
            "graph": {
                "nodes": [
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": [10, 20, 30, 40],
                        "position": {"x": 100, "y": 50},
                    },
                    {
                        "id": int_id,
                        "kind": "primitive",
                        "primitive_type": "int",
                        "label": "Index",
                        "data": {"value": 2},
                        "position": {"x": 100, "y": 150},
                    },
                    {
                        "id": item_id,
                        "kind": "utility",
                        "utility_type": "list_item_by_index",
                        "label": "Item",
                        "data": {
                            "required_inputs": [
                                {"key": "index", "type": "int", "value": None},
                                {"key": "list", "type": "list", "value": None},
                            ]
                        },
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 500, "y": 100},
                    },
                ],
                "edges": [
                    {"source": list_id, "target": item_id, "target_handle": "list"},
                    {"source": int_id, "target": item_id, "target_handle": "index"},
                    {"source": item_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    item_result = next((r for r in result["node_results"] if r["node_id"] == item_id), None)
    assert item_result is not None
    assert item_result["output"]["kind"] == "int"
    assert item_result["output"]["value"] == 30
    stop_result = next((r for r in result["node_results"] if r["node_id"] == stop_id), None)
    assert stop_result["output"]["kind"] == "int"
    assert stop_result["output"]["value"] == 30


def test_basic_conditional_boolean_input_true(client: TestClient):
    """Boolean true -> condition -> True branch."""
    bool_id = "n_bool_001"
    cond_id = "n_cond_001"
    true_id = "n_true_001"
    stop_id = "n_stop_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Conditional Boolean True",
            "graph": {
                "nodes": [
                    {
                        "id": bool_id,
                        "kind": "primitive",
                        "primitive_type": "boolean",
                        "label": "Bool",
                        "data": {"value": True},
                        "position": {"x": 100, "y": 100},
                    },
                    _basic_conditional_node(cond_id, condition_value=None),
                    {
                        "id": true_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "True",
                        "data": {"text": "yes"},
                        "position": {"x": 400, "y": 50},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": bool_id, "target": cond_id, "target_handle": "condition"},
                    {"source": cond_id, "target": true_id, "source_handle": "true"},
                    {"source": true_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    assert any(r["node_id"] == true_id for r in result["node_results"])
    stop_result = next(r for r in result["node_results"] if r["node_id"] == stop_id)
    assert stop_result["output"]["text"] == "yes"


def test_basic_conditional_boolean_input_false(client: TestClient):
    """Boolean false -> condition -> False branch."""
    bool_id = "n_bool_001"
    cond_id = "n_cond_001"
    false_id = "n_false_001"
    stop_id = "n_stop_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Conditional Boolean False",
            "graph": {
                "nodes": [
                    {
                        "id": bool_id,
                        "kind": "primitive",
                        "primitive_type": "boolean",
                        "label": "Bool",
                        "data": {"value": False},
                        "position": {"x": 100, "y": 100},
                    },
                    _basic_conditional_node(cond_id, condition_value=None),
                    {
                        "id": false_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "False",
                        "data": {"text": "no"},
                        "position": {"x": 400, "y": 150},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 600, "y": 100},
                    },
                ],
                "edges": [
                    {"source": bool_id, "target": cond_id, "target_handle": "condition"},
                    {"source": cond_id, "target": false_id, "source_handle": "false"},
                    {"source": false_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    assert any(r["node_id"] == false_id for r in result["node_results"])
    stop_result = next(r for r in result["node_results"] if r["node_id"] == stop_id)
    assert stop_result["output"]["text"] == "no"


def test_stop_node_accepts_boolean_output(client: TestClient):
    """Boolean -> Stop (required_outputs type boolean)."""
    bool_id = "n_bool_001"
    stop_id = "n_stop_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Stop Boolean",
            "graph": {
                "nodes": [
                    {
                        "id": bool_id,
                        "kind": "primitive",
                        "primitive_type": "boolean",
                        "label": "Bool",
                        "data": {"value": True},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "boolean"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [
                    {"source": bool_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    stop_result = next(r for r in result["node_results"] if r["node_id"] == stop_id)
    assert stop_result["output"]["kind"] == "boolean"
    assert stop_result["output"]["value"] is True


def test_start_any_slot_and_stop_any_output(client: TestClient):
    """Start `any` slot carries JSON values; Stop `any` passes typed output through."""
    start_id = "n_start"
    stop_id = "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Start Any Stop Any",
            "graph": {
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {
                            "required_inputs": [
                                {"key": "payload", "type": "any", "value": {"x": 1}},
                            ]
                        },
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "any"}]},
                        "position": {"x": 300, "y": 0},
                    },
                ],
                "edges": [
                    {"source": start_id, "target": stop_id, "source_handle": "payload"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    start_r = next(r for r in result["node_results"] if r["node_id"] == start_id)
    assert start_r["output"]["outputs"]["payload"] == {"x": 1}
    stop_r = next(r for r in result["node_results"] if r["node_id"] == stop_id)
    assert stop_r["output"]["kind"] == "dictionary"
    assert stop_r["output"]["data"] == {"x": 1}


def test_stop_node_accepts_int_output(client: TestClient):
    """Int -> Stop (required_outputs type int)."""
    int_id = "n_int_001"
    stop_id = "n_stop_001"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Stop Int",
            "graph": {
                "nodes": [
                    {
                        "id": int_id,
                        "kind": "primitive",
                        "primitive_type": "int",
                        "label": "Int",
                        "data": {"value": 99},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "int"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [
                    {"source": int_id, "target": stop_id},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()

    assert result["status"] == "ok"
    stop_result = next(r for r in result["node_results"] if r["node_id"] == stop_id)
    assert stop_result["output"]["kind"] == "int"
    assert stop_result["output"]["value"] == 99


def test_for_loop_runs_body_per_list_item(client: TestClient):
    """List -> For Loop -> String -> Stop; body runs once per item; step_numbers increase."""
    start_id = "n_start"
    list_id = "n_list"
    fl_id = "n_fl"
    str_id = "n_str"
    stop_id = "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "For Loop String Body",
            "graph": {
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
                        "data": ["alpha", "beta", "gamma"],
                        "position": {"x": 100, "y": 0},
                    },
                    {
                        "id": fl_id,
                        "kind": "control",
                        "control_type": "for_loop",
                        "label": "For Loop",
                        "data": {"required_inputs": [{"key": "input", "type": "list", "value": None}]},
                        "position": {"x": 250, "y": 0},
                    },
                    {
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Echo",
                        "data": {"text": ""},
                        "position": {"x": 400, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 550, "y": 0},
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
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"

    str_runs = [r for r in result["node_results"] if r["node_id"] == str_id]
    assert len(str_runs) == 3
    texts = {r["output"]["text"] for r in str_runs}
    assert texts == {"alpha", "beta", "gamma"}

    steps = [r["step_number"] for r in result["node_results"] if r.get("step_number") is not None]
    assert steps == sorted(steps)
    assert len(steps) == len(set(steps))

    fl_result = next(r for r in result["node_results"] if r["node_id"] == fl_id)
    assert fl_result["details"]["resolved_inputs"].get("iteration_count") == 3


def test_for_loop_body_branching_control_signal_out_matches_main_schedule(client: TestClient):
    """Branch + signal_out to the same trigger target must schedule in loop body (parity with main run)."""
    start_id = "n_start"
    list_id = "n_list"
    fl_id = "n_fl"
    gt_id = "n_gt"
    str_id = "n_str"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "For Loop Gt Branch And Signal Out Same Target",
            "graph": {
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
                        "data": [1],
                        "position": {"x": 50, "y": 0},
                    },
                    {
                        "id": fl_id,
                        "kind": "control",
                        "control_type": "for_loop",
                        "label": "For Loop",
                        "data": {"required_inputs": [{"key": "input", "type": "list", "value": None}]},
                        "position": {"x": 150, "y": 0},
                    },
                    _comparison_node(gt_id, "gt", 5, 3, "Gt?"),
                    {
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "T",
                        "data": {"text": "ok"},
                        "position": {"x": 350, "y": 0},
                    },
                ],
                "edges": [
                    {"source": start_id, "target": list_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": list_id, "target": fl_id, "source_handle": "output", "target_handle": "input"},
                    {"source": list_id, "target": fl_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": fl_id, "target": gt_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": gt_id, "target": str_id, "source_handle": "true", "target_handle": "trigger"},
                    {"source": gt_id, "target": str_id, "source_handle": "signal_out", "target_handle": "trigger"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    str_runs = [r for r in result["node_results"] if r["node_id"] == str_id]
    assert len(str_runs) == 1
    assert str_runs[0]["output"]["text"] == "ok"


def test_add_to_list_inline_appends(client: TestClient):
    add_id = "n_add"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Add to List Inline",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": add_id,
                        "kind": "utility",
                        "utility_type": "add_to_list",
                        "label": "Add to List",
                        "data": {
                            "required_inputs": [
                                {"key": "list", "type": "list", "value": [1, 2]},
                                {"key": "value", "type": "any", "value": 3},
                            ]
                        },
                        "position": {"x": 100, "y": 0},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "list"}]},
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": add_id},
                    {"source": add_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    add_r = next(r for r in result["node_results"] if r["node_id"] == add_id)
    assert add_r["output"]["data"] == [1, 2, 3]


def test_add_to_list_inline_appends_string(client: TestClient):
    add_id = "n_add"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Add to List Inline String",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": add_id,
                        "kind": "utility",
                        "utility_type": "add_to_list",
                        "label": "Add to List",
                        "data": {
                            "required_inputs": [
                                {"key": "list", "type": "list", "value": ["a", "b"]},
                                {"key": "value", "type": "any", "value": "c"},
                            ]
                        },
                        "position": {"x": 100, "y": 0},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "list"}]},
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": add_id},
                    {"source": add_id, "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    add_r = next(r for r in result["node_results"] if r["node_id"] == add_id)
    assert add_r["output"]["data"] == ["a", "b", "c"]


def test_add_to_list_missing_list_errors(client: TestClient):
    add_id = "n_add"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Add to List Missing List",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": add_id,
                        "kind": "utility",
                        "utility_type": "add_to_list",
                        "label": "Add",
                        "data": {
                            "required_inputs": [
                                {"key": "list", "type": "list", "value": None},
                                {"key": "value", "type": "any", "value": 1},
                            ]
                        },
                        "position": {"x": 100, "y": 0},
                    },
                ],
                "edges": [{"source": "n_start", "target": add_id}],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "partial"
    add_r = next(r for r in result["node_results"] if r["node_id"] == add_id)
    assert add_r["status"] == "error"
    assert "list" in (add_r.get("error") or "").lower()


def test_add_to_list_missing_value_errors(client: TestClient):
    add_id = "n_add"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Add to List Missing Value",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": add_id,
                        "kind": "utility",
                        "utility_type": "add_to_list",
                        "label": "Add",
                        "data": {
                            "required_inputs": [
                                {"key": "list", "type": "list", "value": [1]},
                                {"key": "value", "type": "any", "value": None},
                            ]
                        },
                        "position": {"x": 100, "y": 0},
                    },
                ],
                "edges": [{"source": "n_start", "target": add_id}],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "partial"
    add_r = next(r for r in result["node_results"] if r["node_id"] == add_id)
    assert add_r["status"] == "error"
    assert "value" in (add_r.get("error") or "").lower()


def test_add_to_list_list_input_must_be_list(client: TestClient):
    add_id = "n_add"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Add to List Bad List Type",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": add_id,
                        "kind": "utility",
                        "utility_type": "add_to_list",
                        "label": "Add",
                        "data": {
                            "required_inputs": [
                                {"key": "list", "type": "list", "value": 123},
                                {"key": "value", "type": "any", "value": 1},
                            ]
                        },
                        "position": {"x": 100, "y": 0},
                    },
                ],
                "edges": [{"source": "n_start", "target": add_id}],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "partial"
    add_r = next(r for r in result["node_results"] if r["node_id"] == add_id)
    assert add_r["status"] == "error"
    assert "must be a list" in (add_r.get("error") or "").lower()


def test_for_loop_add_to_list_accumulates(client: TestClient):
    """Empty list seed + For loop items; Add to List carry yields [1,2,3] on last iteration."""
    start_id = "n_start"
    list_src_id = "n_src"
    list_seed_id = "n_seed"
    fl_id = "n_fl"
    add_id = "n_add"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "For Loop Add to List",
            "graph": {
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": list_src_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "Src",
                        "data": [1, 2, 3],
                        "position": {"x": 50, "y": 0},
                    },
                    {
                        "id": list_seed_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "Seed",
                        "data": [],
                        "position": {"x": 50, "y": 50},
                    },
                    {
                        "id": fl_id,
                        "kind": "control",
                        "control_type": "for_loop",
                        "label": "For Loop",
                        "data": {"required_inputs": [{"key": "input", "type": "list", "value": None}]},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": add_id,
                        "kind": "utility",
                        "utility_type": "add_to_list",
                        "label": "Add to List",
                        "data": {
                            "required_inputs": [
                                {"key": "list", "type": "list", "value": None},
                                {"key": "value", "type": "any", "value": None},
                            ]
                        },
                        "position": {"x": 350, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": start_id,
                        "target": list_src_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                    {"source": list_src_id, "target": fl_id, "source_handle": "output", "target_handle": "input"},
                    {"source": list_src_id, "target": fl_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {
                        "source": fl_id,
                        "target": list_seed_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                    {"source": list_seed_id, "target": add_id, "source_handle": "output", "target_handle": "list"},
                    {"source": fl_id, "target": add_id, "source_handle": "item", "target_handle": "value"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    add_runs = [r for r in result["node_results"] if r["node_id"] == add_id]
    assert len(add_runs) == 3
    last = max(add_runs, key=lambda r: r["step_number"])
    assert last["output"]["data"] == [1, 2, 3]


def test_for_loop_parallel_add_to_list_matches_sequential_order(client: TestClient):
    """parallel_iterations: Add to List carry merges in list index order (same as sequential)."""
    start_id = "n_start"
    list_src_id = "n_src"
    list_seed_id = "n_seed"
    fl_id = "n_fl"
    add_id = "n_add"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "For Loop Add to List Parallel",
            "graph": {
                "nodes": [
                    {
                        "id": start_id,
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": list_src_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "Src",
                        "data": [1, 2, 3],
                        "position": {"x": 50, "y": 0},
                    },
                    {
                        "id": list_seed_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "Seed",
                        "data": [],
                        "position": {"x": 50, "y": 50},
                    },
                    {
                        "id": fl_id,
                        "kind": "control",
                        "control_type": "for_loop",
                        "label": "For Loop",
                        "data": {
                            "required_inputs": [{"key": "input", "type": "list", "value": None}],
                            "parallel_iterations": True,
                        },
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": add_id,
                        "kind": "utility",
                        "utility_type": "add_to_list",
                        "label": "Add to List",
                        "data": {
                            "required_inputs": [
                                {"key": "list", "type": "list", "value": None},
                                {"key": "value", "type": "any", "value": None},
                            ]
                        },
                        "position": {"x": 350, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": start_id,
                        "target": list_src_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                    {"source": list_src_id, "target": fl_id, "source_handle": "output", "target_handle": "input"},
                    {"source": list_src_id, "target": fl_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {
                        "source": fl_id,
                        "target": list_seed_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                    {"source": list_seed_id, "target": add_id, "source_handle": "output", "target_handle": "list"},
                    {"source": fl_id, "target": add_id, "source_handle": "item", "target_handle": "value"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    add_runs = [r for r in result["node_results"] if r["node_id"] == add_id]
    assert len(add_runs) == 3
    last = max(add_runs, key=lambda r: r["step_number"])
    assert last["output"]["data"] == [1, 2, 3]


def test_parallel_for_loop_simple_llm_run_stream_completes(client: TestClient):
    """Parallel For Loop + Simple LLM (mocked): session-safe Persona reads; NDJSON stream ends with event end."""
    persona_id = _get_persona_id(client)
    start_id = "n_start"
    list_id = "n_list"
    fl_id = "n_fl"
    llm_id = "n_llm"
    stop_id = "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Parallel FL LLM stream",
            "graph": {
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
                        "data": ["a", "b"],
                        "position": {"x": 100, "y": 0},
                    },
                    {
                        "id": fl_id,
                        "kind": "control",
                        "control_type": "for_loop",
                        "label": "For Loop",
                        "data": {
                            "required_inputs": [{"key": "input", "type": "list", "value": None}],
                            "parallel_iterations": True,
                        },
                        "position": {"x": 250, "y": 0},
                    },
                    _simple_llm_node(llm_id, persona_id, label="LLM"),
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 550, "y": 0},
                    },
                ],
                "edges": [
                    {"source": start_id, "target": list_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": list_id, "target": fl_id, "source_handle": "output", "target_handle": "input"},
                    {"source": list_id, "target": fl_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": fl_id, "target": llm_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": fl_id, "target": llm_id, "source_handle": "item", "target_handle": "user_prompt"},
                    {"source": llm_id, "target": stop_id, "source_handle": "output"},
                    {"source": llm_id, "target": stop_id, "source_handle": "signal_out", "target_handle": "trigger"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    mock_response = ProviderResponse(
        raw_text="ok",
        parsed=None,
        provider_name="lmstudio",
        usage=None,
    )
    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance
        enqueue = client.post(f"/api/v1/workflow-definitions/{wf_id}/runs", json={})
        assert enqueue.status_code == 200
        run_uid = enqueue.json()["run_id"]
        time.sleep(0.05)
        with client.stream("GET", f"/api/v1/workflow-runs/{run_uid}/events") as response:
            assert response.status_code == 200
            raw = b"".join(response.iter_bytes())
        assert mock_instance.chat.await_count == 2

        events = sse_response_body_to_legacy_workflow_events(raw)
        assert events[0].get("event") == "start"
        assert events[-1].get("event") == "end"
        assert not any(e.get("event") == "error" for e in events)


def test_parallel_for_loop_with_nested_inner_loop_returns_422(client: TestClient):
    """parallel_iterations is incompatible with a nested For Loop in the body (v1)."""
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Parallel outer nested inner",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": "n_list",
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "Outer list",
                        "data": [1, 2],
                        "position": {"x": 100, "y": 0},
                    },
                    {
                        "id": "n_inner_list",
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "Inner list",
                        "data": [1],
                        "position": {"x": 100, "y": 80},
                    },
                    {
                        "id": "n_outer",
                        "kind": "control",
                        "control_type": "for_loop",
                        "label": "Outer",
                        "data": {
                            "required_inputs": [{"key": "input", "type": "list", "value": None}],
                            "parallel_iterations": True,
                        },
                        "position": {"x": 250, "y": 0},
                    },
                    {
                        "id": "n_inner",
                        "kind": "control",
                        "control_type": "for_loop",
                        "label": "Inner",
                        "data": {"required_inputs": [{"key": "input", "type": "list", "value": None}]},
                        "position": {"x": 400, "y": 0},
                    },
                    {
                        "id": "n_str",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Body",
                        "data": {"text": ""},
                        "position": {"x": 550, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start",
                        "target": "n_list",
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                    {"source": "n_list", "target": "n_outer", "source_handle": "output", "target_handle": "input"},
                    {
                        "source": "n_list",
                        "target": "n_outer",
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                    {
                        "source": "n_outer",
                        "target": "n_inner_list",
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                    {
                        "source": "n_outer",
                        "target": "n_inner",
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                    {
                        "source": "n_inner_list",
                        "target": "n_inner",
                        "source_handle": "output",
                        "target_handle": "input",
                    },
                    {"source": "n_inner", "target": "n_str", "source_handle": "item", "target_handle": "input"},
                    {
                        "source": "n_inner",
                        "target": "n_str",
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 422
    assert "parallel_iterations" in run_res.json()["detail"] or "nested" in run_res.json()["detail"].lower()


def test_for_loop_empty_list_zero_iterations(client: TestClient):
    start_id = "n_start"
    list_id = "n_list"
    fl_id = "n_fl"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "For Loop Empty",
            "graph": {
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
                        "data": [],
                        "position": {"x": 100, "y": 0},
                    },
                    {
                        "id": fl_id,
                        "kind": "control",
                        "control_type": "for_loop",
                        "label": "For Loop",
                        "data": {"required_inputs": [{"key": "input", "type": "list", "value": None}]},
                        "position": {"x": 250, "y": 0},
                    },
                ],
                "edges": [
                    {"source": start_id, "target": list_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": list_id, "target": fl_id, "source_handle": "output", "target_handle": "input"},
                    {"source": list_id, "target": fl_id, "source_handle": "signal_out", "target_handle": "trigger"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    fl_result = next(r for r in result["node_results"] if r["node_id"] == fl_id)
    assert fl_result["details"]["resolved_inputs"].get("iteration_count") == 0
    assert fl_result["output"]["kind"] == "list"
    assert fl_result["output"]["data"] == []


def test_for_loop_overlapping_bodies_returns_422(client: TestClient):
    """Two For Loops sharing a body node without nesting must fail validation."""
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Overlapping loops",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": "n_l1",
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "L1",
                        "data": [1],
                        "position": {"x": 100, "y": 0},
                    },
                    {
                        "id": "n_l2",
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "L2",
                        "data": [2],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": "n_fl1",
                        "kind": "control",
                        "control_type": "for_loop",
                        "label": "FL1",
                        "data": {"required_inputs": [{"key": "input", "type": "list", "value": None}]},
                        "position": {"x": 250, "y": 0},
                    },
                    {
                        "id": "n_fl2",
                        "kind": "control",
                        "control_type": "for_loop",
                        "label": "FL2",
                        "data": {"required_inputs": [{"key": "input", "type": "list", "value": None}]},
                        "position": {"x": 250, "y": 100},
                    },
                    {
                        "id": "n_shared",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Shared",
                        "data": {"text": ""},
                        "position": {"x": 400, "y": 50},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": "n_l1", "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": "n_start", "target": "n_l2", "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": "n_l1", "target": "n_fl1", "source_handle": "output", "target_handle": "input"},
                    {"source": "n_l1", "target": "n_fl1", "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": "n_l2", "target": "n_fl2", "source_handle": "output", "target_handle": "input"},
                    {"source": "n_l2", "target": "n_fl2", "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": "n_fl1", "target": "n_shared", "source_handle": "item", "target_handle": "input"},
                    {
                        "source": "n_fl1",
                        "target": "n_shared",
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                    {"source": "n_fl2", "target": "n_shared", "source_handle": "item", "target_handle": "input"},
                    {
                        "source": "n_fl2",
                        "target": "n_shared",
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 422


def test_list_primitive_parses_json_array_string_upstream(client: TestClient):
    """Single string upstream that is a JSON array becomes list elements."""
    str_id = "n_str"
    list_id = "n_list"
    len_id = "n_len"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "List from JSON string",
            "graph": {
                "nodes": [
                    {
                        "id": str_id,
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "JSON",
                        "data": {"text": '["p","q"]'},
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": list_id,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "List",
                        "data": [],
                        "position": {"x": 300, "y": 100},
                    },
                    {
                        "id": len_id,
                        "kind": "utility",
                        "utility_type": "len_from_list",
                        "label": "Len",
                        "data": {},
                        "position": {"x": 500, "y": 100},
                    },
                ],
                "edges": [
                    {"source": str_id, "target": list_id, "target_handle": "input"},
                    {"source": list_id, "target": len_id, "target_handle": "list"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    len_result = next(r for r in result["node_results"] if r["node_id"] == len_id)
    assert len_result["output"]["value"] == 2


def test_resolved_inputs_on_string_start_stop_nodes(client: TestClient):
    """Primitives and Start/Stop attach ``details.resolved_inputs`` for Explorer Last Run."""
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Resolved inputs smoke",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "user_input", "type": "string", "value": "go"}]},
                        "position": {"x": 50, "y": 100},
                    },
                    {
                        "id": "n_str",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "Str",
                        "data": {"text": "hello"},
                        "position": {"x": 200, "y": 100},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": "n_str"},
                    {"source": "n_str", "target": "n_stop"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    by_id = {r["node_id"]: r for r in run_res.json()["node_results"]}
    assert by_id["n_start"]["details"]["resolved_inputs"] == {"user_input": "go"}
    assert by_id["n_str"]["details"]["resolved_inputs"]["text"] == "go\n\nhello"
    up = by_id["n_stop"]["details"]["resolved_inputs"]["upstream_output"]
    assert isinstance(up, dict)
    assert up.get("kind") == "string"
    assert up.get("text") == "go\n\nhello"


def test_for_loop_end_odds_evens_dictionary(client: TestClient):
    """For Loop End aggregates Add to List carry from branched body into one dictionary output."""
    start_id = "n_start"
    list_id = "n_list"
    fl_id = "n_fl"
    end_id = "n_end"
    seed_o = "n_seed_o"
    seed_e = "n_seed_e"
    int2_id = "n_i2"
    int0_id = "n_i0"
    mod_id = "n_mod"
    gt_id = "n_gt"
    add_o = "n_add_o"
    add_e = "n_add_e"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "For Loop End odds evens",
            "graph": {
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
                        "label": "Src",
                        "data": [1, 2, 3, 4, 5],
                        "position": {"x": 50, "y": 0},
                    },
                    {
                        "id": int2_id,
                        "kind": "primitive",
                        "primitive_type": "int",
                        "label": "Two",
                        "data": {"value": 2},
                        "position": {"x": 50, "y": 80},
                    },
                    {
                        "id": int0_id,
                        "kind": "primitive",
                        "primitive_type": "int",
                        "label": "Zero",
                        "data": {"value": 0},
                        "position": {"x": 50, "y": 120},
                    },
                    {
                        "id": fl_id,
                        "kind": "control",
                        "control_type": "for_loop",
                        "label": "For Loop",
                        "data": {"required_inputs": [{"key": "input", "type": "list", "value": None}]},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": seed_o,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "Seed O",
                        "data": [],
                        "position": {"x": 200, "y": 100},
                    },
                    {
                        "id": seed_e,
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "Seed E",
                        "data": [],
                        "position": {"x": 200, "y": 140},
                    },
                    {
                        "id": mod_id,
                        "kind": "utility",
                        "utility_type": "modulo_ints",
                        "label": "Mod 2",
                        "data": {
                            "required_inputs": [
                                {"key": "input_a", "type": "int", "value": None},
                                {"key": "input_b", "type": "int", "value": None},
                            ]
                        },
                        "position": {"x": 350, "y": 0},
                    },
                    {
                        "id": gt_id,
                        "kind": "control",
                        "control_type": "gt",
                        "label": "Gt 0",
                        "data": {},
                        "position": {"x": 500, "y": 0},
                    },
                    {
                        "id": add_o,
                        "kind": "utility",
                        "utility_type": "add_to_list",
                        "label": "Odds",
                        "data": {
                            "required_inputs": [
                                {"key": "list", "type": "list", "value": None},
                                {"key": "value", "type": "any", "value": None},
                            ]
                        },
                        "position": {"x": 650, "y": 0},
                    },
                    {
                        "id": add_e,
                        "kind": "utility",
                        "utility_type": "add_to_list",
                        "label": "Evens",
                        "data": {
                            "required_inputs": [
                                {"key": "list", "type": "list", "value": None},
                                {"key": "value", "type": "any", "value": None},
                            ]
                        },
                        "position": {"x": 650, "y": 80},
                    },
                    {
                        "id": end_id,
                        "kind": "control",
                        "control_type": "for_loop_end",
                        "label": "Loop End",
                        "data": {"for_loop_id": fl_id, "exports": ["odds", "evens"]},
                        "position": {"x": 850, "y": 0},
                    },
                ],
                "edges": [
                    {"source": start_id, "target": list_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": start_id, "target": int2_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": start_id, "target": int0_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": list_id, "target": fl_id, "source_handle": "output", "target_handle": "input"},
                    {"source": list_id, "target": fl_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": fl_id, "target": seed_o, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": fl_id, "target": seed_e, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": fl_id, "target": end_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": seed_o, "target": add_o, "source_handle": "output", "target_handle": "list"},
                    {"source": seed_e, "target": add_e, "source_handle": "output", "target_handle": "list"},
                    {"source": fl_id, "target": mod_id, "source_handle": "item", "target_handle": "input_a"},
                    {"source": int2_id, "target": mod_id, "source_handle": "output", "target_handle": "input_b"},
                    {"source": mod_id, "target": gt_id, "source_handle": "output", "target_handle": "input_a"},
                    {"source": int0_id, "target": gt_id, "source_handle": "output", "target_handle": "input_b"},
                    {"source": fl_id, "target": add_o, "source_handle": "item", "target_handle": "value"},
                    {"source": fl_id, "target": add_e, "source_handle": "item", "target_handle": "value"},
                    {"source": gt_id, "target": add_o, "source_handle": "true", "target_handle": "trigger"},
                    {"source": gt_id, "target": add_e, "source_handle": "false", "target_handle": "trigger"},
                    {"source": add_o, "target": end_id, "source_handle": "output", "target_handle": "odds"},
                    {"source": add_e, "target": end_id, "source_handle": "output", "target_handle": "evens"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    end_r = next(r for r in result["node_results"] if r["node_id"] == end_id)
    assert end_r["status"] == "ok"
    data = end_r["output"]["data"]
    assert data["odds"] == [1, 3, 5]
    assert data["evens"] == [2, 4]


def test_for_loop_end_validation_requires_trigger_and_exports(client: TestClient):
    """For Loop End without trigger edge or exports fails validation."""
    fl_id = "n_fl"
    end_id = "n_end"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Bad end",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": fl_id,
                        "kind": "control",
                        "control_type": "for_loop",
                        "label": "For Loop",
                        "data": {"required_inputs": [{"key": "input", "type": "list", "value": []}]},
                        "position": {"x": 100, "y": 0},
                    },
                    {
                        "id": end_id,
                        "kind": "control",
                        "control_type": "for_loop_end",
                        "label": "End",
                        "data": {"for_loop_id": fl_id, "exports": ["a"]},
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 422


def test_for_loop_end_validation_errors_rejected_at_enqueue_preflight(client: TestClient):
    """Invalid For Loop End wiring is caught during preflight (same validators as executor) — no queued run."""
    fl_id = "n_fl"
    end_id = "n_end"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Bad end stream",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": fl_id,
                        "kind": "control",
                        "control_type": "for_loop",
                        "label": "For Loop",
                        "data": {"required_inputs": [{"key": "input", "type": "list", "value": []}]},
                        "position": {"x": 100, "y": 0},
                    },
                    {
                        "id": end_id,
                        "kind": "control",
                        "control_type": "for_loop_end",
                        "label": "End",
                        "data": {"for_loop_id": fl_id, "exports": ["a"]},
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    enq = client.post(f"/api/v1/workflow-definitions/{wf_id}/runs", json={})
    assert enq.status_code == 422
    detail = enq.json()["detail"]
    assert isinstance(detail, str)
    assert "for loop end" in detail.lower()

_MINI_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _multimodal_llm_node(node_id: str, persona_id: str) -> dict:
    return {
        "id": node_id,
        "kind": "skill",
        "skill_type": "multimodal_llm",
        "label": "Multimodal LLM",
        "data": {
            "persona_id": persona_id,
            "required_inputs": [
                {"key": "user_prompt", "type": "string", "value": None},
                {"key": "images", "type": "list", "value": None},
            ],
        },
        "position": {"x": 400, "y": 100},
    }


def test_multimodal_llm_missing_images_structured_error(client: TestClient):
    persona_id = _get_persona_id(client)
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Multimodal missing images",
            "graph": {
                "nodes": [
                    {
                        "id": "n_s",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "P",
                        "data": {"text": "hi"},
                        "position": {"x": 100, "y": 100},
                    },
                    _multimodal_llm_node("n_mm", persona_id),
                ],
                "edges": [
                    {"source": "n_s", "target": "n_mm", "target_handle": "user_prompt"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock()
        MockProvider.return_value = mock_instance
        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    mm = next(r for r in run_res.json()["node_results"] if r["node_id"] == "n_mm")
    assert mm["status"] == "error"
    se = (mm.get("details") or {}).get("structured_error") or {}
    assert se.get("type") == "MISSING_IMAGE_INPUT"
    mock_instance.chat.assert_not_called()


def test_multimodal_llm_invalid_artifact_structured_error(client: TestClient):
    persona_id = _get_persona_id(client)
    bad_id = str(uuid.uuid4())
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Multimodal bad artifact",
            "graph": {
                "nodes": [
                    {
                        "id": "n_l",
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "L",
                        "data": [{"artifact_id": bad_id}],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": "n_s",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "P",
                        "data": {"text": "hi"},
                        "position": {"x": 100, "y": 200},
                    },
                    _multimodal_llm_node("n_mm", persona_id),
                ],
                "edges": [
                    {"source": "n_l", "target": "n_mm", "target_handle": "images"},
                    {"source": "n_s", "target": "n_mm", "target_handle": "user_prompt"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]
    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock()
        MockProvider.return_value = mock_instance
        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    mm = next(r for r in run_res.json()["node_results"] if r["node_id"] == "n_mm")
    assert mm["status"] == "error"
    se = (mm.get("details") or {}).get("structured_error") or {}
    assert se.get("type") == "INVALID_IMAGE_REFERENCE"
    mock_instance.chat.assert_not_called()


def test_multimodal_llm_model_not_multimodal_error(client: TestClient, db_session: Session):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    art = UrlSnapshotArtifact(
        user_id=user.id,
        image_bytes=_MINI_PNG_1X1,
        mime_type="image/png",
        width=1,
        height=1,
        final_url="",
    )
    db_session.add(art)
    db_session.commit()
    db_session.refresh(art)

    persona_id = _get_persona_id(client)
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Multimodal not vision model",
            "graph": {
                "nodes": [
                    {
                        "id": "n_l",
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "L",
                        "data": [{"artifact_id": str(art.id)}],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": "n_s",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "P",
                        "data": {"text": "hi"},
                        "position": {"x": 100, "y": 200},
                    },
                    _multimodal_llm_node("n_mm", persona_id),
                ],
                "edges": [
                    {"source": "n_l", "target": "n_mm", "target_handle": "images"},
                    {"source": "n_s", "target": "n_mm", "target_handle": "user_prompt"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    async def _raise_mm(*args: Any, **kwargs: Any):
        raise LMStudioModelNotMultimodalError(
            "Selected model does not support image input.",
            provider_detail="this model is text-only",
        )

    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(side_effect=_raise_mm)
        MockProvider.return_value = mock_instance
        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    mm = next(r for r in run_res.json()["node_results"] if r["node_id"] == "n_mm")
    assert mm["status"] == "error"
    se = (mm.get("details") or {}).get("structured_error") or {}
    assert se.get("type") == "MODEL_NOT_MULTIMODAL"
    assert se.get("retryable") is False


def test_multimodal_llm_success_sends_image_url_parts(client: TestClient, db_session: Session):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    art = UrlSnapshotArtifact(
        user_id=user.id,
        image_bytes=_MINI_PNG_1X1,
        mime_type="image/png",
        width=1,
        height=1,
        final_url="",
    )
    db_session.add(art)
    db_session.commit()
    db_session.refresh(art)

    persona_id = _get_persona_id(client)
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Multimodal ok",
            "graph": {
                "nodes": [
                    {
                        "id": "n_l",
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "L",
                        "data": [{"artifact_id": str(art.id)}],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": "n_s",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "P",
                        "data": {"text": "Describe the pixel"},
                        "position": {"x": 100, "y": 200},
                    },
                    _multimodal_llm_node("n_mm", persona_id),
                ],
                "edges": [
                    {"source": "n_l", "target": "n_mm", "target_handle": "images"},
                    {"source": "n_s", "target": "n_mm", "target_handle": "user_prompt"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="A single pixel.",
        parsed=None,
        provider_name="lmstudio",
        usage={"input_tokens": 1, "output_tokens": 2},
    )
    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance
        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    mm = next(r for r in run_res.json()["node_results"] if r["node_id"] == "n_mm")
    assert mm["status"] == "ok"
    out = mm.get("output") or {}
    assert out.get("text") == "A single pixel."
    md = out.get("metadata") or {}
    assert md.get("model") is not None or md.get("usage") is not None

    mock_instance.chat.assert_awaited_once()
    messages = mock_instance.chat.await_args[0][0]
    assert messages[0]["role"] == "system"
    assert isinstance(messages[0]["content"], str)
    assert messages[1]["role"] == "user"
    user_parts = messages[1]["content"]
    assert isinstance(user_parts, list)
    assert user_parts[0] == {"type": "text", "text": "Describe the pixel"}
    assert any(
        p.get("type") == "image_url" and "data:image/png;base64," in (p.get("image_url") or {}).get("url", "")
        for p in user_parts[1:]
    )


def test_multimodal_llm_success_with_list_of_snapshot_output_dicts(client: TestClient, db_session: Session):
    """Images wired as a list of full capture_url_snapshot output rows (nested image.artifact_id)."""
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    art = UrlSnapshotArtifact(
        user_id=user.id,
        image_bytes=_MINI_PNG_1X1,
        mime_type="image/png",
        width=1,
        height=1,
        final_url="",
    )
    db_session.add(art)
    db_session.commit()
    db_session.refresh(art)

    snapshot_row = {
        "image": {
            "artifact_id": str(art.id),
            "mime_type": "image/png",
            "width": 1,
            "height": 1,
        },
        "final_url": "https://example.com/",
        "captured_at": "2026-04-23T18:45:00.494384Z",
        "duration_ms": 0,
        "cached": True,
    }

    persona_id = _get_persona_id(client)
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Multimodal list of snapshot dicts",
            "graph": {
                "nodes": [
                    {
                        "id": "n_l",
                        "kind": "primitive",
                        "primitive_type": "list",
                        "label": "L",
                        "data": [snapshot_row],
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": "n_s",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "P",
                        "data": {"text": "Describe the pixel"},
                        "position": {"x": 100, "y": 200},
                    },
                    _multimodal_llm_node("n_mm", persona_id),
                ],
                "edges": [
                    {"source": "n_l", "target": "n_mm", "target_handle": "images"},
                    {"source": "n_s", "target": "n_mm", "target_handle": "user_prompt"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    workflow_id = workflow_res.json()["id"]

    mock_response = ProviderResponse(
        raw_text="A single pixel.",
        parsed=None,
        provider_name="lmstudio",
        usage={"input_tokens": 1, "output_tokens": 2},
    )
    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance
        run_res = client.post(f"/api/v1/workflow-definitions/{workflow_id}/run")
    assert run_res.status_code == 200
    mm = next(r for r in run_res.json()["node_results"] if r["node_id"] == "n_mm")
    assert mm["status"] == "ok"
    mock_instance.chat.assert_awaited_once()


def _image_primitive_node(
    node_id: str,
    *,
    artifact_id: str | None,
    position: dict | None = None,
) -> dict:
    data: dict = {
        "label": "Image",
        "required_inputs": [{"key": "image", "type": "dictionary", "value": None}],
    }
    if artifact_id is not None:
        data["artifact_id"] = artifact_id
    return {
        "id": node_id,
        "kind": "primitive",
        "primitive_type": "image",
        "label": "Image",
        "data": data,
        "position": position or {"x": 50, "y": 100},
    }


def test_image_primitive_emits_normalized_dictionary(client: TestClient, db_session: Session):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    art = UrlSnapshotArtifact(
        user_id=user.id,
        image_bytes=_MINI_PNG_1X1,
        mime_type="image/png",
        width=1,
        height=1,
        final_url="",
    )
    db_session.add(art)
    db_session.commit()
    db_session.refresh(art)

    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Image primitive emit",
            "graph": {
                "nodes": [
                    _image_primitive_node("n_i", artifact_id=str(art.id)),
                    {
                        "id": "st",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 400, "y": 100},
                    },
                ],
                "edges": [
                    {
                        "source": "n_i",
                        "target": "st",
                        "source_handle": "output",
                        "target_handle": "output",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    n = next(r for r in run_res.json()["node_results"] if r["node_id"] == "n_i")
    assert n["status"] == "ok"
    out = n.get("output") or {}
    assert out.get("kind") == "dictionary"
    d = out.get("data") or {}
    assert d.get("artifact_id") == str(art.id)
    assert d.get("mime_type") == "image/png"
    assert d.get("width") == 1
    assert d.get("height") == 1


def test_image_primitive_error_when_no_artifact(client: TestClient):
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Image primitive empty",
            "graph": {
                "nodes": [_image_primitive_node("n_i", artifact_id=None)],
                "edges": [],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    n = next(r for r in run_res.json()["node_results"] if r["node_id"] == "n_i")
    assert n["status"] == "error"


def test_multimodal_llm_from_image_primitive_node(client: TestClient, db_session: Session):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    art = UrlSnapshotArtifact(
        user_id=user.id,
        image_bytes=_MINI_PNG_1X1,
        mime_type="image/png",
        width=1,
        height=1,
        final_url="",
    )
    db_session.add(art)
    db_session.commit()
    db_session.refresh(art)

    persona_id = _get_persona_id(client)
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "MM from image primitive",
            "graph": {
                "nodes": [
                    _image_primitive_node("n_i", artifact_id=str(art.id)),
                    {
                        "id": "n_s",
                        "kind": "primitive",
                        "primitive_type": "string",
                        "label": "P",
                        "data": {"text": "Describe"},
                        "position": {"x": 100, "y": 200},
                    },
                    _multimodal_llm_node("n_mm", persona_id),
                ],
                "edges": [
                    {"source": "n_i", "target": "n_mm", "source_handle": "output", "target_handle": "images"},
                    {"source": "n_s", "target": "n_mm", "target_handle": "user_prompt"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    mock_response = ProviderResponse(
        raw_text="ok",
        parsed=None,
        provider_name="lmstudio",
        usage={"input_tokens": 1, "output_tokens": 1},
    )
    with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
        mock_instance = AsyncMock()
        mock_instance.chat = AsyncMock(return_value=mock_response)
        MockProvider.return_value = mock_instance
        run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    mm = next(r for r in run_res.json()["node_results"] if r["node_id"] == "n_mm")
    assert mm["status"] == "ok"
    mock_instance.chat.assert_awaited_once()
