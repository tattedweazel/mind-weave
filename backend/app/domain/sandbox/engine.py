"""Tick orchestration: intents, actions, grid — no HTTP/Phaser."""

from __future__ import annotations

import random
import uuid
from typing import Any, List, Optional, Set, assert_never

from app.domain.sandbox.constants import (
    DEFAULT_FOOD_ENERGY,
    EAT_ENERGY_BONUS_PER_TICK,
    EAT_FOOD_DRAIN_PER_TICK,
    EAT_HUNGER_RELIEF_PER_TICK,
    HUNGER_PASSIVE_PER_TICK,
    MAX_RETRY,
    RECENT_ACTIONS_MAX,
    SANDBOX_GRID_MAX_SIZE,
    SANDBOX_GRID_MIN_SIZE,
    SLEEP_ENERGY_PER_TICK,
)
from app.domain.sandbox.workflow_bridge import decision_intent_from_workflow_result
from app.domain.schemas.sandbox import (
    DecisionIntent,
    GridCell,
    PetIntent,
    PetState,
    RecentAction,
    SandboxItem,
    SandboxState,
    SandboxTickInput,
    WorldState,
)
from app.domain.schemas.workflow_run import WorkflowRunResult


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _manhattan(a: GridCell, b: GridCell) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def _is_nearby8(pet: GridCell, cell: GridCell) -> bool:
    dx = abs(pet.x - cell.x)
    dy = abs(pet.y - cell.y)
    return dx <= 1 and dy <= 1 and (dx + dy) > 0


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


def _remove_items_at_cell(state: SandboxState, g: GridCell) -> None:
    removed_ids: Set[str] = set()
    new_items: list[SandboxItem] = []
    for it in state.world.items:
        if it.position.x == g.x and it.position.y == g.y:
            removed_ids.add(it.id)
            continue
        new_items.append(it)
    if not removed_ids:
        return
    state.world.items = new_items
    tid = state.pet.intent.target_item_id if state.pet.intent else None
    if tid and tid in removed_ids:
        state.pet.intent = None


def _place_food_at_cell(state: SandboxState, g: GridCell) -> None:
    """Append food on `g` if the cell is empty and the pet is not on it (same rules as legacy cell_click add)."""
    if state.pet.position.x == g.x and state.pet.position.y == g.y:
        return
    if any(it.position.x == g.x and it.position.y == g.y for it in state.world.items):
        return
    state.world.items.append(
        SandboxItem(
            id=str(uuid.uuid4()),
            type="food",
            position=g,
            energy=DEFAULT_FOOD_ENERGY,
        )
    )


def _world_grid(w: int, h: int):
    from app.domain.schemas.sandbox import WorldGrid

    return WorldGrid(width=w, height=h)


def resize_world_grid(state: SandboxState, width: int, height: int) -> None:
    """Resize the world grid; clamp pet position; drop OOB items; clear pet intent.

    Callers must pass dimensions within ``SANDBOX_GRID_MIN_SIZE``..``SANDBOX_GRID_MAX_SIZE``.
    """
    w = _clamp_int(int(width), SANDBOX_GRID_MIN_SIZE, SANDBOX_GRID_MAX_SIZE)
    h = _clamp_int(int(height), SANDBOX_GRID_MIN_SIZE, SANDBOX_GRID_MAX_SIZE)
    state.world.grid = _world_grid(w, h)
    state.pet.position = GridCell(
        x=_clamp_int(state.pet.position.x, 0, w - 1),
        y=_clamp_int(state.pet.position.y, 0, h - 1),
    )
    kept: list[SandboxItem] = []
    for it in state.world.items:
        if 0 <= it.position.x < w and 0 <= it.position.y < h:
            kept.append(it)
    state.world.items = kept
    state.pet.intent = None


def initial_sandbox_state_clean() -> SandboxState:
    from app.domain.sandbox.constants import (
        DEFAULT_GRID_HEIGHT,
        DEFAULT_GRID_WIDTH,
        DEFAULT_PET_ENERGY,
        DEFAULT_PET_HUNGER,
        DEFAULT_PET_MOOD,
    )

    w, h = DEFAULT_GRID_WIDTH, DEFAULT_GRID_HEIGHT
    mid = GridCell(x=w // 2, y=h // 2)
    return SandboxState(
        tick=0,
        pet=PetState(
            hunger=DEFAULT_PET_HUNGER,
            energy=DEFAULT_PET_ENERGY,
            mood=DEFAULT_PET_MOOD,
            position=mid,
            intent=None,
        ),
        world=WorldState(grid=_world_grid(w, h), items=[]),
        recent_actions=[],
    )


def _item_blocks_cell(world: WorldState, cell: GridCell) -> bool:
    return any(it.position.x == cell.x and it.position.y == cell.y for it in world.items)


def _neighbors4(g: GridCell, width: int, height: int) -> List[GridCell]:
    out: List[GridCell] = []
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nx, ny = g.x + dx, g.y + dy
        if 0 <= nx < width and 0 <= ny < height:
            out.append(GridCell(x=nx, y=ny))
    return out


def _find_item(world: WorldState, item_id: str) -> SandboxItem | None:
    for it in world.items:
        if it.id == item_id:
            return it
    return None


def _first_nearby_food(world: WorldState, pet: GridCell) -> SandboxItem | None:
    """First food in ``world.items`` order that is 8-adjacent to the pet (matches ``query.first_nearby_food_item_dicts``)."""
    for it in world.items:
        if it.type == "food" and _is_nearby8(pet, it.position):
            return it
    return None


def _bump_intent_retry_or_fail(state: SandboxState, intent: PetIntent) -> None:
    """On repeated failure: increment retry_count, or clear intent when already at max (never exceeds ``le=3``)."""
    if intent.retry_count >= MAX_RETRY:
        state.pet.intent = None
    else:
        intent.retry_count += 1


def _goal_cell_for_move(intent: PetIntent, world: WorldState) -> GridCell | None:
    if intent.target_cell is not None:
        return intent.target_cell
    if intent.target_item_id:
        it = _find_item(world, intent.target_item_id)
        if it:
            return it.position
    return None


def _pick_step_toward(
    pet: GridCell,
    goal: GridCell,
    world: WorldState,
    width: int,
    height: int,
    rng: random.Random,
) -> GridCell | None:
    neighbors = _neighbors4(pet, width, height)
    best: list[GridCell] = []
    best_d = 10**9
    for n in neighbors:
        if _item_blocks_cell(world, n):
            continue
        d = _manhattan(n, goal)
        if d < best_d:
            best_d = d
            best = [n]
        elif d == best_d:
            best.append(n)
    if not best:
        return None
    return rng.choice(best)


def _append_recent(state: SandboxState, action: str, reason: str | None) -> None:
    ra = RecentAction(tick=state.tick, action=action, reason=reason)  # type: ignore[arg-type]
    state.recent_actions.append(ra)
    if len(state.recent_actions) > RECENT_ACTIONS_MAX:
        state.recent_actions = state.recent_actions[-RECENT_ACTIONS_MAX:]


class SandboxEngine:
    """Pure simulation steps."""

    def __init__(self, rng: Optional[random.Random] = None) -> None:
        self._rng = rng or random.Random()

    def apply_interactions(
        self,
        state: SandboxState,
        events: list[dict[str, Any]],
    ) -> None:
        """Apply queued UI interactions. Prefer `place_item` / `remove_item`; `cell_click` toggles food (legacy)."""
        w, h = state.world.grid.width, state.world.grid.height
        for ev in events:
            et = ev.get("type")
            if et == "place_item":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                item_type = ev.get("item_type")
                if item_type != "food":
                    continue
                _place_food_at_cell(state, g)
                continue
            if et == "remove_item":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                _remove_items_at_cell(state, g)
                continue
            if et == "cell_click":
                g = _parse_interaction_cell(ev, w, h)
                if g is None:
                    continue
                # Toggle: remove food on cell, else place food if allowed (legacy one-click UX).
                removed_id = None
                new_items: list[SandboxItem] = []
                for it in state.world.items:
                    if it.type == "food" and it.position.x == g.x and it.position.y == g.y:
                        removed_id = it.id
                        continue
                    new_items.append(it)
                if removed_id is not None:
                    state.world.items = new_items
                    if state.pet.intent and state.pet.intent.target_item_id == removed_id:
                        state.pet.intent = None
                    continue
                _place_food_at_cell(state, g)

    def passive_tick_start(self, state: SandboxState) -> None:
        state.pet.hunger = _clamp_int(state.pet.hunger + HUNGER_PASSIVE_PER_TICK, 0, 100)

    def advance_tick_counter(self, state: SandboxState) -> None:
        state.tick += 1

    def build_tick_input(self, state: SandboxState) -> SandboxTickInput:
        return SandboxTickInput(
            tick=state.tick,
            pet=state.pet.model_copy(deep=True),
            world=state.world.model_copy(deep=True),
            recent_actions=[r.model_copy() for r in state.recent_actions],
        )

    def continue_intent_step(self, state: SandboxState) -> bool:
        """Execute one tick of current in-progress intent. Returns True if consumed."""
        intent = state.pet.intent
        if not intent or intent.status != "in_progress":
            return False

        w, h = state.world.grid.width, state.world.grid.height
        act = intent.action
        valid_actions = (
            "idle",
            "sleep",
            "wander",
            "move_to",
            "eat_nearby",
        )
        if act not in valid_actions:
            state.pet.intent = None
            return True

        if act == "idle":
            intent.status = "complete"
            _append_recent(state, "idle", intent.reason)
            state.pet.intent = None
            return True

        if act == "sleep":
            state.pet.energy = _clamp_int(state.pet.energy + SLEEP_ENERGY_PER_TICK, 0, 100)
            if state.pet.energy >= 100:
                intent.status = "complete"
                _append_recent(state, "sleep", intent.reason)
                state.pet.intent = None
            return True

        if act == "wander":
            neighbors = _neighbors4(state.pet.position, w, h)
            empty = [n for n in neighbors if not _item_blocks_cell(state.world, n)]
            if not empty:
                _bump_intent_retry_or_fail(state, intent)
                return True
            choice = self._rng.choice(empty)
            state.pet.position = choice
            intent.status = "complete"
            _append_recent(state, "wander", intent.reason)
            state.pet.intent = None
            return True

        if act == "move_to":
            goal = _goal_cell_for_move(intent, state.world)
            if goal is None:
                _bump_intent_retry_or_fail(state, intent)
                return True
            px, py = state.pet.position.x, state.pet.position.y
            at_goal = px == goal.x and py == goal.y
            blocked = _item_blocks_cell(state.world, goal)
            if at_goal or (blocked and _is_nearby8(state.pet.position, goal)):
                intent.status = "complete"
                state.pet.intent = None
                return True

            nxt = _pick_step_toward(state.pet.position, goal, state.world, w, h, self._rng)
            if nxt is None:
                _bump_intent_retry_or_fail(state, intent)
                return True
            state.pet.position = nxt
            return True

        if act == "eat_nearby":
            tid = intent.target_item_id
            it: SandboxItem | None = None
            if tid:
                cand = _find_item(state.world, tid)
                if cand and cand.type == "food" and _is_nearby8(state.pet.position, cand.position):
                    it = cand
            if it is None:
                it = _first_nearby_food(state.world, state.pet.position)
            if it is None:
                _bump_intent_retry_or_fail(state, intent)
                return True
            drain = min(EAT_FOOD_DRAIN_PER_TICK, it.energy or 0)
            it.energy = max(0, (it.energy or 0) - drain)
            state.pet.hunger = _clamp_int(state.pet.hunger - min(EAT_HUNGER_RELIEF_PER_TICK, state.pet.hunger), 0, 100)
            state.pet.energy = _clamp_int(state.pet.energy + EAT_ENERGY_BONUS_PER_TICK, 0, 100)
            if it.energy <= 0:
                state.world.items = [x for x in state.world.items if x.id != it.id]
                intent.status = "complete"
                _append_recent(state, "eat_nearby", intent.reason)
                state.pet.intent = None
            return True

        assert_never(act)

    def start_intent_from_decision(self, state: SandboxState, dec: DecisionIntent) -> None:
        state.pet.intent = PetIntent(
            action=dec.action,
            status="in_progress",
            target_item_id=dec.target_item_id,
            target_cell=dec.target_cell,
            reason=dec.reason,
            retry_count=0,
        )
        if dec.action == "idle":
            self.continue_intent_step(state)

    def parse_workflow_decision(
        self,
        result: WorkflowRunResult,
        graph: dict[str, Any],
    ) -> tuple[DecisionIntent | None, str | None]:
        nodes = graph.get("nodes") or []
        return decision_intent_from_workflow_result(result, list(nodes))
