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
from app.domain.sandbox.workflow_bridge import decision_intent_from_workflow_result
from app.domain.schemas.sandbox import (
    BoardCreaturePlacement,
    BoardDefinition,
    CreatureState,
    DecisionIntent,
    Facing,
    GridCell,
    RecentAction,
    SOLID_ITEM_TYPES,
    SandboxItem,
    SandboxState,
    SandboxTickInput,
    WorldGrid,
    WorldState,
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


def _cell_occupied(state: SandboxState, g: GridCell) -> bool:
    if _creature_at_cell(state, g) is not None:
        return True
    return any(it.position.x == g.x and it.position.y == g.y for it in state.world.items)


def _item_blocks_movement(world: WorldState, cell: GridCell) -> bool:
    for it in world.items:
        if it.position.x == cell.x and it.position.y == cell.y and it.type in SOLID_ITEM_TYPES:
            return True
    return False


def _creature_blocks_cell(state: SandboxState, cell: GridCell, exclude_id: str | None = None) -> bool:
    for c in state.creatures:
        if exclude_id and c.id == exclude_id:
            continue
        if c.position.x == cell.x and c.position.y == cell.y:
            return True
    return False


def _remove_items_at_cell(state: SandboxState, g: GridCell) -> None:
    state.world.items = [
        it for it in state.world.items if not (it.position.x == g.x and it.position.y == g.y)
    ]


def _remove_creature_at_cell(state: SandboxState, g: GridCell) -> None:
    state.creatures = [c for c in state.creatures if not (c.position.x == g.x and c.position.y == g.y)]


def _place_item_at_cell(state: SandboxState, g: GridCell, item_type: str) -> None:
    if _cell_occupied(state, g):
        return
    if item_type == "food":
        state.world.items.append(
            SandboxItem(
                id=str(uuid.uuid4()),
                type="food",
                position=g,
                energy=DEFAULT_FOOD_ENERGY,
            )
        )
    elif item_type == "wall":
        state.world.items.append(
            SandboxItem(
                id=str(uuid.uuid4()),
                type="wall",
                position=g,
                energy=None,
            )
        )


def _place_creature_at_cell(
    state: SandboxState,
    g: GridCell,
    workflow_id: str,
    name: str | None = None,
) -> None:
    if _cell_occupied(state, g):
        return
    creature_num = len(state.creatures) + 1
    state.creatures.append(
        CreatureState(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            name=name or f"Creature {creature_num}",
            position=g,
            facing=DEFAULT_CREATURE_FACING,  # type: ignore[arg-type]
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
                if item_type not in ("food", "wall"):
                    continue
                _place_item_at_cell(state, g, item_type)
                continue
            if et == "remove_item":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                _remove_items_at_cell(state, g)
                continue
            if et == "place_creature":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                wf_id = ev.get("workflow_id")
                if not wf_id or not str(wf_id).strip():
                    continue
                _place_creature_at_cell(state, g, str(wf_id), ev.get("name"))
                continue
            if et == "remove_creature":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                _remove_creature_at_cell(state, g)
                continue
            if et == "cell_click":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                _remove_items_at_cell(state, g)
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
    ) -> None:
        w, h = state.world.grid.width, state.world.grid.height
        act = dec.action

        if act == "idle":
            _append_recent(state, creature.id, "idle", dec.reason)
            return

        if act == "turn_left":
            creature.facing = _TURN_LEFT[creature.facing]
            _append_recent(state, creature.id, "turn_left", dec.reason)
            return

        if act == "turn_right":
            creature.facing = _TURN_RIGHT[creature.facing]
            _append_recent(state, creature.id, "turn_right", dec.reason)
            return

        if act == "move_forward":
            nxt = _forward_cell(creature, w, h)
            if nxt is not None and not _item_blocks_movement(state.world, nxt):
                if not _creature_blocks_cell(state, nxt, exclude_id=creature.id):
                    creature.position = nxt
            _append_recent(state, creature.id, "move_forward", dec.reason)
            return

        assert_never(act)

    def parse_workflow_decision(
        self,
        result: WorkflowRunResult,
        graph: dict[str, Any],
    ) -> tuple[DecisionIntent | None, str | None]:
        nodes = graph.get("nodes") or []
        return decision_intent_from_workflow_result(result, list(nodes))
