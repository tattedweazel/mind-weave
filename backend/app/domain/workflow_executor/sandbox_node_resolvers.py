"""Sandbox navigation utility node resolvers (mixed into ExecutorResolverMixin)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from app.domain.schemas import (
    DictionaryNodeOutput,
    GraphEdge,
    ListNodeOutput,
    NodeOutputUnion,
    SandboxGetFacingUtilityNode,
    SandboxGetNearbyUtilityNode,
    SandboxGetPositionUtilityNode,
    SandboxIdleUtilityNode,
    SandboxMoveForwardUtilityNode,
    SandboxTickPrimitiveNode,
    SandboxTurnLeftUtilityNode,
    SandboxTurnRightUtilityNode,
    StringNodeOutput,
)
from app.domain.schemas.sandbox import SandboxTickInput
from app.domain.workflow_executor.inputs import _resolve_inputs_by_target_handle

if TYPE_CHECKING:
    from app.domain.workflow_executor.executor_resolver_mixin import WorkflowExecutorResolverMixin


def _executor_mod():
    from app.domain.workflow_executor import executor as executor_mod

    return executor_mod


class SandboxNodeResolverMixin:
    def _resolve_sandbox_tick_primitive_node(
        self: WorkflowExecutorResolverMixin,
        node: SandboxTickPrimitiveNode,
        upstream: list[NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Emit validated ``SandboxTickInput`` as ``DictionaryNodeOutput``."""
        raw: dict | None = None
        ov = input_overrides.get("sandbox_tick")
        if isinstance(ov, dict) and "world" in ov and "creature" in ov and "tick" in ov:
            raw = dict(ov)
        if raw is None:
            raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                (
                    "sandbox_tick primitive: no tick — run from Sandbox (tick override), "
                    "or wire Start's sandbox_tick / a tick-shaped dictionary to input"
                ),
                {"sandbox_tick": None},
            )
        try:
            tick_in = SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_tick primitive: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        data = tick_in.model_dump(mode="json")
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": {"sandbox_tick": data}},
        }

    def _resolve_sandbox_get_position_node(
        self: WorkflowExecutorResolverMixin,
        node: SandboxGetPositionUtilityNode,
        upstream: list[NodeOutputUnion],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import creature_position_from_tick_dict

        raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_get_position: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            cell = creature_position_from_tick_dict(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_get_position: {exc}",
                {"sandbox_tick": raw},
            )
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=cell),
            "details": {"resolved_inputs": cell},
        }

    def _resolve_sandbox_get_facing_node(
        self: WorkflowExecutorResolverMixin,
        node: SandboxGetFacingUtilityNode,
        upstream: list[NodeOutputUnion],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import creature_facing_from_tick_dict

        raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_get_facing: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            facing = creature_facing_from_tick_dict(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_get_facing: {exc}",
                {"sandbox_tick": raw},
            )
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=facing),
            "details": {"resolved_inputs": {"facing": facing}},
        }

    def _resolve_sandbox_get_nearby_node(
        self: WorkflowExecutorResolverMixin,
        node: SandboxGetNearbyUtilityNode,
        upstream: list[NodeOutputUnion],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import nearby_cells_from_tick_dict

        raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_get_nearby: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            cells = nearby_cells_from_tick_dict(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_get_nearby: {exc}",
                {"sandbox_tick": raw},
            )
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=cells),
            "details": {"resolved_inputs": {"count": len(cells)}},
        }

    def _resolve_sandbox_navigation_action_node(
        self: WorkflowExecutorResolverMixin,
        node_id: str,
        action: str,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
        node_data: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import navigation_action_dict

        raw_inputs = (node_data or {}).get("required_inputs") or [
            {"key": "reason", "type": "string", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node_id,
            ["reason"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        reason_raw = resolved.get("reason")
        reason: str | None = None
        if reason_raw is not None and str(reason_raw).strip():
            reason = str(reason_raw).strip()
        try:
            data = navigation_action_dict(action, reason)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"{action}: {exc}",
                dict(resolved),
            )
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node_id, data=data),
            "details": {"resolved_inputs": data},
        }

    def _resolve_sandbox_move_forward_node(
        self: WorkflowExecutorResolverMixin,
        node: SandboxMoveForwardUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_sandbox_navigation_action_node(
            node.id, "move_forward", edges, outputs, input_overrides, node.data
        )

    def _resolve_sandbox_turn_left_node(
        self: WorkflowExecutorResolverMixin,
        node: SandboxTurnLeftUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_sandbox_navigation_action_node(
            node.id, "turn_left", edges, outputs, input_overrides, node.data
        )

    def _resolve_sandbox_turn_right_node(
        self: WorkflowExecutorResolverMixin,
        node: SandboxTurnRightUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_sandbox_navigation_action_node(
            node.id, "turn_right", edges, outputs, input_overrides, node.data
        )

    def _resolve_sandbox_idle_node(
        self: WorkflowExecutorResolverMixin,
        node: SandboxIdleUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_sandbox_navigation_action_node(
            node.id, "idle", edges, outputs, input_overrides, node.data
        )
