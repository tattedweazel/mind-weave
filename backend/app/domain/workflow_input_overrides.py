"""Validate run request overrides against workflow graph (SE-015)."""

from __future__ import annotations

from typing import Any

# Top-level keys the executor may read outside Start required_inputs.
_GLOBAL_OVERRIDE_KEYS = frozenset(
    {
        "text",
        "user_input",
        "user_prompt",
        "additional_system_prompt_context",
        "structure",
        # Injected by Sandbox tick runs and accepted by the sandbox_tick primitive / Start sandbox_tick slot.
        "sandbox_tick",
    }
)


def allowed_input_override_keys(graph: dict[str, Any]) -> frozenset[str]:
    keys: set[str] = set(_GLOBAL_OVERRIDE_KEYS)
    for node in graph.get("nodes") or []:
        if node.get("kind") != "start":
            continue
        data = node.get("data") or {}
        for ri in data.get("required_inputs") or []:
            k = ri.get("key")
            if isinstance(k, str) and k:
                keys.add(k)
    return frozenset(keys)


def validate_input_overrides_for_workflow(graph: dict[str, Any], overrides: dict[str, Any] | None) -> None:
    if not overrides:
        return
    allowed = allowed_input_override_keys(graph)
    bad = set(overrides) - allowed
    if bad:
        raise ValueError(f"input_overrides keys not allowed for this workflow: {sorted(bad)}")
