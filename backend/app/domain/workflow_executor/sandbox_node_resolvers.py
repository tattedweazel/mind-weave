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
    SandboxGetInventoryUtilityNode,
    SandboxIdleUtilityNode,
    SandboxMoveForwardUtilityNode,
    SandboxPickUpItemUtilityNode,
    SandboxPlaceItemUtilityNode,
    SandboxPromptUserActionUtilityNode,
    SandboxRemoveItemAtCellUtilityNode,
    SandboxSpawnItemAtCellUtilityNode,
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


_SANDBOX_TICK_CONTEXT_ERROR = (
    "{label}: no tick or fixture context — wire sandbox_tick (Start output) or a tick-shaped dictionary, "
    "or run from Sandbox / fixture workflow"
)


class SandboxNodeResolverMixin:
    def _sandbox_item_definition_probe_maps(self: WorkflowExecutorResolverMixin):
        from app.domain.services.sandbox_definition_service import item_definition_probe_maps

        return item_definition_probe_maps(self.session, self.user_id)

    def _sandbox_fixture_definition_color_map(self: WorkflowExecutorResolverMixin):
        from app.domain.services.sandbox_definition_service import fixture_definition_color_map

        return fixture_definition_color_map(self.session, self.user_id)

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
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import (
            creature_position_from_tick_dict,
            fixture_cell_probe_from_fixture_dict,
        )

        definition_maps = self._sandbox_item_definition_probe_maps()
        fixture_colors = self._sandbox_fixture_definition_color_map()
        fx_raw = _executor_mod()._resolve_sandbox_fixture_dict(upstream, input_overrides)
        if fx_raw is not None:
            try:
                cell = fixture_cell_probe_from_fixture_dict(
                    fx_raw,
                    definition_labels=definition_maps.labels,
                    definition_defaults=definition_maps.defaults,
                    fixture_definition_colors=fixture_colors,
                )
            except Exception as exc:
                return _executor_mod()._error_with_resolved_inputs(
                    f"sandbox_get_position: {exc}",
                    {"sandbox_fixture": fx_raw},
                )
            return {
                "status": "ok",
                "output": DictionaryNodeOutput(node_id=node.id, data=cell),
                "details": {"resolved_inputs": cell},
            }

        raw = _executor_mod()._resolve_sandbox_tick_dict(upstream, input_overrides)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                _SANDBOX_TICK_CONTEXT_ERROR.format(label="sandbox_get_position"),
                {"sandbox_tick": None},
            )
        try:
            cell = creature_position_from_tick_dict(
                raw,
                definition_labels=definition_maps.labels,
                definition_defaults=definition_maps.defaults,
                fixture_definition_colors=fixture_colors,
            )
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
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import creature_facing_from_tick_dict

        raw = _executor_mod()._resolve_sandbox_tick_dict(upstream, input_overrides)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                _SANDBOX_TICK_CONTEXT_ERROR.format(label="sandbox_get_facing"),
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
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import nearby_cells_from_tick_dict

        raw = _executor_mod()._resolve_sandbox_tick_dict(upstream, input_overrides)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                _SANDBOX_TICK_CONTEXT_ERROR.format(label="sandbox_get_nearby"),
                {"sandbox_tick": None},
            )
        try:
            definition_maps = self._sandbox_item_definition_probe_maps()
            fixture_colors = self._sandbox_fixture_definition_color_map()
            cells = nearby_cells_from_tick_dict(
                raw,
                definition_labels=definition_maps.labels,
                definition_defaults=definition_maps.defaults,
                fixture_definition_colors=fixture_colors,
            )
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
        *,
        include_item_type: bool = False,
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import navigation_action_dict

        input_keys = ["reason", "item_type"] if include_item_type else ["reason"]
        raw_inputs = (node_data or {}).get("required_inputs") or [
            {"key": "reason", "type": "string", "value": None},
            *(
                [{"key": "item_type", "type": "string", "value": None}]
                if include_item_type
                else []
            ),
        ]
        resolved = _resolve_inputs_by_target_handle(
            node_id,
            input_keys,
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        reason_raw = resolved.get("reason")
        reason: str | None = None
        if reason_raw is not None and str(reason_raw).strip():
            reason = str(reason_raw).strip()
        item_type = None
        if include_item_type:
            raw_item_type = resolved.get("item_type")
            if raw_item_type in ("ball", "food"):
                item_type = raw_item_type
        try:
            data = navigation_action_dict(
                action,
                reason,
                item_type=item_type,
            )
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

    def _resolve_sandbox_pick_up_item_node(
        self: WorkflowExecutorResolverMixin,
        node: SandboxPickUpItemUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_sandbox_navigation_action_node(
            node.id, "pick_up_item", edges, outputs, input_overrides, node.data
        )

    def _resolve_sandbox_place_item_node(
        self: WorkflowExecutorResolverMixin,
        node: SandboxPlaceItemUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_sandbox_navigation_action_node(
            node.id,
            "place_item",
            edges,
            outputs,
            input_overrides,
            node.data,
            include_item_type=True,
        )

    def _resolve_sandbox_get_inventory_node(
        self: WorkflowExecutorResolverMixin,
        node: SandboxGetInventoryUtilityNode,
        upstream: list[NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import inventory_from_tick_dict

        raw = _executor_mod()._resolve_sandbox_tick_dict(upstream, input_overrides)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                _SANDBOX_TICK_CONTEXT_ERROR.format(label="sandbox_get_inventory"),
                {"sandbox_tick": None},
            )
        try:
            entries = inventory_from_tick_dict(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_get_inventory: {exc}",
                {"sandbox_tick": raw},
            )
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=entries),
            "details": {"resolved_inputs": {"count": len(entries)}},
        }

    def _resolve_sandbox_prompt_user_action_node(
        self: WorkflowExecutorResolverMixin,
        node: SandboxPromptUserActionUtilityNode,
        upstream: list[NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import navigation_action_dict

        raw_action = input_overrides.get("sandbox_user_action")
        if not isinstance(raw_action, dict):
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_prompt_user_action requires a simulation user action for this tick",
                {"sandbox_user_action": raw_action},
            )

        action_raw = raw_action.get("action")
        if not isinstance(action_raw, str) or not action_raw.strip():
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_prompt_user_action: action must be a non-empty string",
                {"sandbox_user_action": raw_action},
            )
        action = action_raw.strip()

        item_type = None
        raw_item_type = raw_action.get("item_type")
        if raw_item_type in ("ball", "food"):
            item_type = raw_item_type

        inventory_index = None
        raw_inventory_index = raw_action.get("inventory_index")
        if isinstance(raw_inventory_index, int) and raw_inventory_index >= 0:
            inventory_index = raw_inventory_index

        item_id = None
        raw_item_id = raw_action.get("item_id")
        if isinstance(raw_item_id, str) and raw_item_id.strip():
            item_id = raw_item_id.strip()

        pick_all = None
        raw_pick_all = raw_action.get("pick_all")
        if raw_pick_all is True:
            pick_all = True

        if action == "place_item" and item_type:
            if inventory_index is not None:
                auto_reason = f"user: place_item:{item_type}@{inventory_index}"
            else:
                auto_reason = f"user: place_item:{item_type}"
        elif action == "pick_up_item":
            if pick_all:
                auto_reason = "user: pick_up_item:all"
            elif item_id:
                auto_reason = f"user: pick_up_item:{item_id}"
            else:
                auto_reason = f"user: {action}"
        else:
            auto_reason = f"user: {action}"

        try:
            data = navigation_action_dict(
                action,
                auto_reason,
                item_type=item_type,
                inventory_index=inventory_index,
                item_id=item_id,
                pick_all=pick_all,
            )
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_prompt_user_action: {exc}",
                {"sandbox_user_action": raw_action},
            )

        tick_raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        details: dict[str, Any] = {
            "resolved_inputs": data,
            "user_action_source": "simulation_prompt",
            "auto_reason": auto_reason,
        }
        if tick_raw is not None:
            details["sandbox_tick"] = tick_raw

        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": details,
        }

    def _resolve_sandbox_region_primitive_node(
        self: WorkflowExecutorResolverMixin,
        node: Any,
        upstream: list[NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.domain.schemas.sandbox import RegionTriggerInput

        raw = input_overrides.get("sandbox_region")
        if not isinstance(raw, dict):
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_region primitive: no region context override",
                {"sandbox_region": None},
            )
        try:
            region_in = RegionTriggerInput.model_validate(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_region primitive: invalid input: {exc}",
                {"sandbox_region": raw},
            )
        data = region_in.model_dump(mode="json")
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": {"sandbox_region": data}},
        }

    def _resolve_sandbox_force_simulation_pause_node(
        self: WorkflowExecutorResolverMixin,
        node: Any,
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        effects = input_overrides.get("_simulation_effects")
        if effects is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_force_simulation_pause is only available during sandbox simulation ticks",
                {"_simulation_effects": None},
            )
        effects.force_pause = True
        data = {"pause": True}
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": data},
        }

    def _resolve_sandbox_get_cell_items_node(
        self: WorkflowExecutorResolverMixin,
        node: Any,
        upstream: list[NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw = input_overrides.get("sandbox_fixture")
        if not isinstance(raw, dict):
            raw_ov = _executor_mod()._sandbox_fixture_dict_from_upstream(upstream)
            raw = raw_ov
        if not isinstance(raw, dict):
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_get_cell_items: connect sandbox_fixture context",
                {"sandbox_fixture": None},
            )
        items = raw.get("cell_items") or []
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=list(items)),
            "details": {"resolved_inputs": {"cell_items": items}},
        }

    def _resolve_sandbox_remove_item_at_cell_node(
        self: WorkflowExecutorResolverMixin,
        node: SandboxRemoveItemAtCellUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "item_id", "type": "string", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["item_id"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        item_id = resolved.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_remove_item_at_cell: item_id required",
                resolved,
            )
        mutations = input_overrides.get("_fixture_mutations")
        removed = False
        if mutations is not None:
            removed = mutations.remove_item_by_id(item_id.strip())
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(
                node_id=node.id, data={"removed": removed, "item_id": item_id.strip()}
            ),
            "details": {"resolved_inputs": resolved},
        }

    def _resolve_sandbox_spawn_item_at_cell_node(
        self: WorkflowExecutorResolverMixin,
        node: SandboxSpawnItemAtCellUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        import uuid as _uuid

        from app.domain.schemas.sandbox import GridCell, SandboxItem
        from app.domain.schemas.sandbox_definitions import BUILTIN_FOOD_ID

        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "definition_id", "type": "string", "value": None},
            {"key": "target", "type": "string", "value": "self"},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["definition_id", "target", "energy", "color"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        raw_fx = input_overrides.get("sandbox_fixture")
        if not isinstance(raw_fx, dict):
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_spawn_item_at_cell: sandbox_fixture override required",
                resolved,
            )
        fixture_pos = (raw_fx.get("fixture") or {}).get("position") or {}
        try:
            base = GridCell.model_validate(fixture_pos)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_spawn_item_at_cell: invalid fixture position: {exc}",
                resolved,
            )
        target = str(resolved.get("target") or "self").strip()
        definition_id = str(resolved.get("definition_id") or BUILTIN_FOOD_ID)
        energy_raw = resolved.get("energy")
        color_raw = resolved.get("color")
        spawn_cell = base
        if target != "self":
            parts = target.replace(",", " ").split()
            if len(parts) >= 2:
                try:
                    dx, dy = int(parts[0]), int(parts[1])
                    spawn_cell = GridCell(x=base.x + dx, y=base.y + dy)
                except ValueError:
                    pass
        energy_val = 48
        if energy_raw is not None and str(energy_raw).strip() != "":
            try:
                energy_val = int(energy_raw)
            except (TypeError, ValueError):
                energy_val = 48
        color_val = str(color_raw).strip() if color_raw is not None and str(color_raw).strip() else None
        new_item = SandboxItem(
            id=str(_uuid.uuid4()),
            type="food" if not color_val else "ball",
            definition_id=definition_id,
            definition_kind="item",
            role="pickable",
            position=spawn_cell,
            energy=energy_val,
            color=color_val,
        )
        mutations = input_overrides.get("_fixture_mutations")
        if mutations is not None:
            mutations.spawn_item(new_item)
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(
                node_id=node.id,
                data={"spawned_id": new_item.id, "position": spawn_cell.model_dump()},
            ),
            "details": {"resolved_inputs": resolved},
        }
