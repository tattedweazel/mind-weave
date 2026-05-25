"""Tick orchestration: atomic navigation actions, grid — no HTTP/Phaser."""

from __future__ import annotations

import uuid
from typing import Any, Optional, assert_never

from app.domain.sandbox.constants import (
    DEFAULT_CREATURE_FACING,
    DEFAULT_FOOD_ENERGY,
    DEFAULT_GRID_HEIGHT,
    DEFAULT_GRID_WIDTH,
    RECENT_ACTIONS_MAX,
    SANDBOX_GRID_MAX_SIZE,
    SANDBOX_GRID_MIN_SIZE,
)
from app.domain.sandbox.item_helpers import (
    is_pickable_item,
    is_region_item,
    is_solid_item,
    items_at_cell,
    pickables_at_cell,
    region_at_cell,
    resolved_item_type,
    solid_at_cell,
)
from app.domain.sandbox.region_triggers import RegionTriggerEvent, evaluate_transition_triggers
from app.domain.sandbox.workflow_bridge import decision_intent_from_workflow_result
from app.domain.schemas.sandbox import (
    BALL_ITEM_TYPE,
    BoardCreaturePlacement,
    BoardDefinition,
    CreatureState,
    DecisionIntent,
    Facing,
    FIXTURE_ITEM_TYPE,
    GridCell,
    InventoryItem,
    PlaceItemFilterType,
    RecentAction,
    REGION_ITEM_TYPE,
    RegionTriggerSessionState,
    SandboxItem,
    SandboxState,
    SandboxTickInput,
    WorldGrid,
    WorldState,
    default_region_trigger,
    normalize_hex_color,
)
from app.domain.schemas.workflow_run import WorkflowRunResult

_TURN_LEFT: dict[Facing, Facing] = {"N": "W", "W": "S", "S": "E", "E": "N"}
_TURN_RIGHT: dict[Facing, Facing] = {"N": "E", "E": "S", "S": "W", "W": "N"}
_FORWARD_DELTA: dict[Facing, tuple[int, int]] = {
    "N": (0, -1),
    "E": (1, 0),
    "S": (0, 1),
    "W": (-1, 0),
}


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _parse_interaction_cell(ev: dict[str, Any], w: int, h: int) -> Optional[GridCell]:
    cell = ev.get("cell") or {}
    try:
        cx = int(cell["x"])
        cy = int(cell["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if cx < 0 or cy < 0 or cx >= w or cy >= h:
        return None
    return GridCell(x=cx, y=cy)


def _creature_at_cell(state: SandboxState, g: GridCell) -> CreatureState | None:
    for c in state.creatures:
        if c.position.x == g.x and c.position.y == g.y:
            return c
    return None


def _blocking_item_at_cell(state: SandboxState, g: GridCell) -> SandboxItem | None:
    solid = solid_at_cell(state.world.items, g.x, g.y)
    if solid is not None:
        return solid
    pickables = pickables_at_cell(state.world.items, g.x, g.y)
    if pickables:
        return pickables[0]
    return None


def _region_at_cell(state: SandboxState, g: GridCell) -> SandboxItem | None:
    return region_at_cell(state.world.items, g.x, g.y)


def _cell_blocked_for_item_placement(state: SandboxState, g: GridCell, *, placing_solid: bool = False) -> bool:
    if _creature_at_cell(state, g) is not None:
        return True
    solid = solid_at_cell(state.world.items, g.x, g.y)
    if placing_solid:
        return solid is not None
    if solid is not None and resolved_item_type(solid) != FIXTURE_ITEM_TYPE:
        return True
    return False


def _cell_blocked_for_creature_placement(state: SandboxState, g: GridCell) -> bool:
    if _creature_at_cell(state, g) is not None:
        return True
    for it in items_at_cell(state.world.items, g.x, g.y):
        if is_region_item(it):
            continue
        return True
    return False


def _item_blocks_movement(world: WorldState, cell: GridCell) -> bool:
    solid = solid_at_cell(world.items, cell.x, cell.y)
    return solid is not None and is_solid_item(solid)


def _creature_blocks_cell(state: SandboxState, cell: GridCell, exclude_id: str | None = None) -> bool:
    for c in state.creatures:
        if exclude_id and c.id == exclude_id:
            continue
        if c.position.x == cell.x and c.position.y == cell.y:
            return True
    return False


def _is_removable_cell_item(it: SandboxItem) -> bool:
    if is_region_item(it):
        return False
    if resolved_item_type(it) == FIXTURE_ITEM_TYPE:
        return False
    return is_solid_item(it) or is_pickable_item(it)


def _remove_blocking_items_at_cell(
    state: SandboxState,
    g: GridCell,
    *,
    item_id: str | None = None,
) -> None:
    if item_id:
        state.world.items = [
            it
            for it in state.world.items
            if not (
                it.id == item_id
                and it.position.x == g.x
                and it.position.y == g.y
                and _is_removable_cell_item(it)
            )
        ]
        return
    state.world.items = [
        it
        for it in state.world.items
        if not (
            it.position.x == g.x
            and it.position.y == g.y
            and _is_removable_cell_item(it)
        )
    ]


def _remove_solid_at_cell(state: SandboxState, g: GridCell) -> None:
    state.world.items = [
        it
        for it in state.world.items
        if not (it.position.x == g.x and it.position.y == g.y and is_solid_item(it))
    ]


def _remove_region_at_cell(state: SandboxState, g: GridCell) -> None:
    state.world.items = [
        it
        for it in state.world.items
        if not (it.position.x == g.x and it.position.y == g.y and it.type == REGION_ITEM_TYPE)
    ]


def _remove_creature_at_cell(state: SandboxState, g: GridCell) -> None:
    state.creatures = [c for c in state.creatures if not (c.position.x == g.x and c.position.y == g.y)]


def _place_item_at_cell(
    state: SandboxState,
    g: GridCell,
    item_type: str,
    *,
    color: str | None = None,
    energy: int | None = None,
    definition_id: str | None = None,
) -> None:
    placing_solid = item_type == "wall"
    if _cell_blocked_for_item_placement(state, g, placing_solid=placing_solid):
        return
    if item_type == "food":
        state.world.items.append(
            SandboxItem(
                id=str(uuid.uuid4()),
                type="food",
                definition_id=definition_id,
                definition_kind="item",
                role="pickable",
                position=g,
                energy=energy if energy is not None else DEFAULT_FOOD_ENERGY,
            )
        )
    elif item_type == "wall":
        state.world.items.append(
            SandboxItem(
                id=str(uuid.uuid4()),
                type="wall",
                definition_id=definition_id,
                definition_kind="terrain",
                role="solid",
                position=g,
            )
        )
    elif item_type == BALL_ITEM_TYPE:
        if not color:
            return
        try:
            normalized = normalize_hex_color(color)
        except ValueError:
            return
        state.world.items.append(
            SandboxItem(
                id=str(uuid.uuid4()),
                type=BALL_ITEM_TYPE,
                definition_id=definition_id,
                definition_kind="item",
                role="pickable",
                position=g,
                color=normalized,
            )
        )


def _remove_pickable_item_at_cell(state: SandboxState, g: GridCell) -> SandboxItem | None:
    pickables = pickables_at_cell(state.world.items, g.x, g.y)
    if not pickables:
        return None
    removed = pickables[-1]
    state.world.items = [it for it in state.world.items if it.id != removed.id]
    return removed


def _inventory_item_from_world_item(it: SandboxItem) -> InventoryItem | None:
    t = resolved_item_type(it)
    if t == BALL_ITEM_TYPE and it.color:
        return InventoryItem(type=BALL_ITEM_TYPE, color=it.color)
    if t == "food" and it.energy is not None:
        return InventoryItem(type="food", energy=it.energy)
    return None


def _fixture_at_cell(state: SandboxState, g: GridCell) -> SandboxItem | None:
    solid = solid_at_cell(state.world.items, g.x, g.y)
    if solid is not None and resolved_item_type(solid) == FIXTURE_ITEM_TYPE:
        return solid
    return None


def _place_fixture_at_cell(state: SandboxState, g: GridCell, definition_id: str) -> None:
    if _creature_at_cell(state, g) is not None:
        return
    if solid_at_cell(state.world.items, g.x, g.y) is not None:
        return
    state.world.items.append(
        SandboxItem(
            id=str(uuid.uuid4()),
            type=FIXTURE_ITEM_TYPE,
            definition_id=definition_id,
            definition_kind="fixture",
            role="solid",
            position=g,
        )
    )


def _pop_inventory_entry(
    creature: CreatureState,
    *,
    item_type: PlaceItemFilterType | None = None,
    inventory_index: int | None = None,
) -> InventoryItem | None:
    if not creature.inventory:
        return None
    if inventory_index is not None:
        if 0 <= inventory_index < len(creature.inventory):
            return creature.inventory.pop(inventory_index)
        return None
    if item_type is None:
        return creature.inventory.pop(0)
    for idx, entry in enumerate(creature.inventory):
        if entry.type == item_type:
            return creature.inventory.pop(idx)
    return None


def _place_region_at_cell(state: SandboxState, g: GridCell, color: str, label: str = "") -> None:
    normalized = normalize_hex_color(color)
    _remove_region_at_cell(state, g)
    state.world.items.append(
        SandboxItem(
            id=str(uuid.uuid4()),
            type="region",
            position=g,
            color=normalized,
            label=label,
            trigger=default_region_trigger(),
        )
    )


def _parse_creature_facing(raw: Any) -> Facing:
    if raw in ("N", "E", "S", "W"):
        return raw  # type: ignore[return-value]
    return DEFAULT_CREATURE_FACING  # type: ignore[return-value]


def _place_creature_at_cell(
    state: SandboxState,
    g: GridCell,
    workflow_id: str,
    color: str,
    name: str | None = None,
    *,
    facing: Facing | None = None,
) -> None:
    if _cell_blocked_for_creature_placement(state, g):
        return
    try:
        normalized = normalize_hex_color(color)
    except ValueError:
        return
    creature_num = len(state.creatures) + 1
    resolved_facing = facing if facing is not None else DEFAULT_CREATURE_FACING
    state.creatures.append(
        CreatureState(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            name=name or f"Creature {creature_num}",
            position=g,
            facing=resolved_facing,
            color=normalized,
        )
    )


def _world_grid(w: int, h: int) -> WorldGrid:
    return WorldGrid(width=w, height=h)


def resize_world_grid(state: SandboxState, width: int, height: int) -> None:
    w = _clamp_int(int(width), SANDBOX_GRID_MIN_SIZE, SANDBOX_GRID_MAX_SIZE)
    h = _clamp_int(int(height), SANDBOX_GRID_MIN_SIZE, SANDBOX_GRID_MAX_SIZE)
    state.world.grid = _world_grid(w, h)
    for c in state.creatures:
        c.position = GridCell(
            x=_clamp_int(c.position.x, 0, w - 1),
            y=_clamp_int(c.position.y, 0, h - 1),
        )
    kept: list[SandboxItem] = []
    for it in state.world.items:
        if 0 <= it.position.x < w and 0 <= it.position.y < h:
            kept.append(it)
    state.world.items = kept


def initial_sandbox_state_clean() -> SandboxState:
    w, h = DEFAULT_GRID_WIDTH, DEFAULT_GRID_HEIGHT
    return SandboxState(
        tick=0,
        creatures=[],
        world=WorldState(grid=_world_grid(w, h), items=[]),
        recent_actions=[],
    )


def sandbox_state_from_board(board: BoardDefinition) -> SandboxState:
    """Snapshot a board template into a fresh sandbox state."""
    st = SandboxState(
        tick=0,
        creatures=[],
        world=WorldState(
            grid=board.grid.model_copy(deep=True),
            items=[it.model_copy(deep=True) for it in board.items],
        ),
        recent_actions=[],
    )
    for bp in board.creatures:
        st.creatures.append(
            CreatureState(
                id=bp.id,
                workflow_id=bp.workflow_id,
                name=bp.name,
                position=bp.position.model_copy(deep=True),
                facing=bp.facing,
                color=bp.color,
                inventory=[entry.model_copy(deep=True) for entry in bp.inventory],
            )
        )
    return st


def board_definition_from_sandbox_state(state: SandboxState) -> BoardDefinition:
    """Extract a board template from current sandbox layout (ignores tick)."""
    creatures = [
        BoardCreaturePlacement(
            id=c.id,
            workflow_id=c.workflow_id,
            name=c.name,
            position=c.position.model_copy(deep=True),
            facing=c.facing,
            color=c.color,
            inventory=[entry.model_copy(deep=True) for entry in c.inventory],
        )
        for c in state.creatures
    ]
    return BoardDefinition(
        grid=state.world.grid.model_copy(deep=True),
        items=[it.model_copy(deep=True) for it in state.world.items],
        creatures=creatures,
    )


def _append_recent(state: SandboxState, creature_id: str, action: str, reason: str | None) -> None:
    ra = RecentAction(tick=state.tick, creature_id=creature_id, action=action, reason=reason)  # type: ignore[arg-type]
    state.recent_actions.append(ra)
    if len(state.recent_actions) > RECENT_ACTIONS_MAX:
        state.recent_actions = state.recent_actions[-RECENT_ACTIONS_MAX:]


def _forward_cell(creature: CreatureState, width: int, height: int) -> GridCell | None:
    dx, dy = _FORWARD_DELTA[creature.facing]
    nx, ny = creature.position.x + dx, creature.position.y + dy
    if nx < 0 or ny < 0 or nx >= width or ny >= height:
        return None
    return GridCell(x=nx, y=ny)


class SandboxEngine:
    """Pure simulation steps."""

    def apply_interactions(
        self,
        state: SandboxState,
        events: list[dict[str, Any]],
    ) -> None:
        w, h = state.world.grid.width, state.world.grid.height
        for ev in events:
            et = ev.get("type")
            if et == "place_item":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                item_type = ev.get("item_type")
                if item_type == "food":
                    _place_item_at_cell(state, g, "food")
                elif item_type == "wall":
                    _place_item_at_cell(state, g, "wall")
                elif item_type == BALL_ITEM_TYPE:
                    raw_color = ev.get("color")
                    if not raw_color or not str(raw_color).strip():
                        continue
                    try:
                        _place_item_at_cell(state, g, BALL_ITEM_TYPE, color=str(raw_color))
                    except ValueError:
                        continue
                continue
            if et == "remove_item":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                raw_item_id = ev.get("item_id")
                item_id = str(raw_item_id).strip() if raw_item_id else None
                if item_id == "":
                    item_id = None
                _remove_blocking_items_at_cell(state, g, item_id=item_id)
                continue
            if et == "place_region":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                raw_color = ev.get("color")
                if not raw_color or not str(raw_color).strip():
                    continue
                raw_label = ev.get("label")
                label = "" if raw_label is None else str(raw_label)
                try:
                    _place_region_at_cell(state, g, str(raw_color), label)
                except ValueError:
                    continue
                continue
            if et == "remove_region":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                _remove_region_at_cell(state, g)
                continue
            if et == "place_creature":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                wf_id = ev.get("workflow_id")
                if not wf_id or not str(wf_id).strip():
                    continue
                raw_color = ev.get("color")
                if not raw_color or not str(raw_color).strip():
                    continue
                _place_creature_at_cell(
                    state,
                    g,
                    str(wf_id),
                    str(raw_color),
                    ev.get("name"),
                    facing=_parse_creature_facing(ev.get("facing")),
                )
                continue
            if et == "remove_creature":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                _remove_creature_at_cell(state, g)
                continue
            if et == "place_fixture":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                def_id = ev.get("definition_id")
                if not def_id or not str(def_id).strip():
                    continue
                _place_fixture_at_cell(state, g, str(def_id))
                continue
            if et == "remove_fixture":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                _remove_solid_at_cell(state, g)
                continue
            if et == "cell_click":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                _remove_blocking_items_at_cell(state, g)
                _place_item_at_cell(state, g, "food")

    def advance_tick_counter(self, state: SandboxState) -> None:
        state.tick += 1

    def build_tick_input(self, state: SandboxState, creature: CreatureState) -> SandboxTickInput:
        all_creatures = [c.model_copy(deep=True) for c in state.creatures]
        return SandboxTickInput(
            tick=state.tick,
            creature=creature.model_copy(deep=True),
            creatures=all_creatures,
            world=state.world.model_copy(deep=True),
            recent_actions=[r.model_copy() for r in state.recent_actions],
        )

    def apply_decision(
        self,
        state: SandboxState,
        creature: CreatureState,
        dec: DecisionIntent,
        *,
        region_trigger_session: RegionTriggerSessionState | None = None,
    ) -> tuple[list[RegionTriggerEvent], RegionTriggerSessionState | None]:
        w, h = state.world.grid.width, state.world.grid.height
        act = dec.action
        trigger_events: list[RegionTriggerEvent] = []
        next_session = region_trigger_session

        if act == "idle":
            _append_recent(state, creature.id, "idle", dec.reason)
            return trigger_events, next_session

        if act == "turn_left":
            creature.facing = _TURN_LEFT[creature.facing]
            _append_recent(state, creature.id, "turn_left", dec.reason)
            return trigger_events, next_session

        if act == "turn_right":
            creature.facing = _TURN_RIGHT[creature.facing]
            _append_recent(state, creature.id, "turn_right", dec.reason)
            return trigger_events, next_session

        if act == "move_forward":
            nxt = _forward_cell(creature, w, h)
            if nxt is not None and not _item_blocks_movement(state.world, nxt):
                if not _creature_blocks_cell(state, nxt, exclude_id=creature.id):
                    prev = creature.position.model_copy(deep=True)
                    creature.position = nxt
                    if next_session is not None:
                        trigger_events, next_session = evaluate_transition_triggers(
                            state,
                            creature=creature,
                            previous_position=prev,
                            session_state=next_session,
                        )
            _append_recent(state, creature.id, "move_forward", dec.reason)
            return trigger_events, next_session

        if act == "pick_up_item":
            fwd = _forward_cell(creature, w, h)
            if fwd is not None and not _creature_blocks_cell(state, fwd, exclude_id=creature.id):
                removed = _remove_pickable_item_at_cell(state, fwd)
                if removed is not None:
                    entry = _inventory_item_from_world_item(removed)
                    if entry is not None:
                        creature.inventory.append(entry)
            _append_recent(state, creature.id, "pick_up_item", dec.reason)
            return trigger_events, next_session

        if act == "place_item":
            fwd = _forward_cell(creature, w, h)
            entry = _pop_inventory_entry(
                creature,
                item_type=dec.item_type,
                inventory_index=dec.inventory_index,
            )
            if fwd is not None and entry is not None and not _creature_at_cell(state, fwd):
                if entry.type == BALL_ITEM_TYPE and entry.color:
                    _place_item_at_cell(state, fwd, BALL_ITEM_TYPE, color=entry.color)
                elif entry.type == "food" and entry.energy is not None:
                    _place_item_at_cell(state, fwd, "food", energy=entry.energy)
                else:
                    creature.inventory.insert(0, entry)
            elif entry is not None:
                creature.inventory.insert(0, entry)
            _append_recent(state, creature.id, "place_item", dec.reason)
            return trigger_events, next_session

        if act == "use_fixture":
            fwd = _forward_cell(creature, w, h)
            if fwd is not None and _fixture_at_cell(state, fwd) is not None:
                _append_recent(state, creature.id, "use_fixture", dec.reason)
            return trigger_events, next_session

        assert_never(act)

    def parse_workflow_decision(
        self,
        result: WorkflowRunResult,
        graph: dict[str, Any],
    ) -> tuple[DecisionIntent | None, str | None]:
        nodes = graph.get("nodes") or []
        return decision_intent_from_workflow_result(result, list(nodes))
