"""Tests for sandbox query helpers."""

from __future__ import annotations

from app.domain.sandbox.query import (
    creature_facing_from_tick_dict,
    creature_position_from_tick_dict,
    nearby_cells_clockwise,
    nearby_cells_from_tick_dict,
    parse_tick,
)
from app.domain.schemas.sandbox import CreatureState, GridCell, SandboxItem, WorldGrid, WorldState


def _creature_dict(*, x: int, y: int, facing: str = "N") -> dict:
    return {
        "id": "c1",
        "workflow_id": "wf1",
        "position": {"x": x, "y": y},
        "facing": facing,
    }


def _minimal_tick(*, creature_pos: dict, items: list | None = None, facing: str = "N") -> dict:
    creature = _creature_dict(x=creature_pos["x"], y=creature_pos["y"], facing=facing)
    return {
        "tick": 1,
        "creature": creature,
        "creatures": [creature],
        "world": {"grid": {"width": 5, "height": 5}, "items": items or []},
        "recent_actions": [],
    }


def test_creature_position_and_facing_from_tick():
    raw = _minimal_tick(creature_pos={"x": 3, "y": 2}, facing="E")
    assert creature_position_from_tick_dict(raw) == {"x": 3, "y": 2}
    assert creature_facing_from_tick_dict(raw) == "E"


def test_nearby_cells_clockwise_facing_n():
    world = WorldState(
        grid=WorldGrid(width=5, height=5),
        items=[
            SandboxItem(id="w1", type="wall", position=GridCell(x=3, y=1)),
            SandboxItem(id="f1", type="food", position=GridCell(x=4, y=1)),
        ],
    )
    creature = CreatureState(id="c1", workflow_id="wf", position=GridCell(x=3, y=2), facing="N")
    cells = nearby_cells_clockwise("N", creature.position, 5, 5, world, [creature], exclude_creature_id="c1")
    kinds = [c.kind for c in cells]
    assert len(cells) == 8
    assert cells[0].x == 3 and cells[0].y == 1
    assert kinds[0] == "wall"


def test_nearby_out_of_bounds():
    world = WorldState(grid=WorldGrid(width=3, height=3), items=[])
    creature = CreatureState(id="c1", workflow_id="wf", position=GridCell(x=0, y=0), facing="N")
    cells = nearby_cells_clockwise("N", creature.position, 3, 3, world, [creature], exclude_creature_id="c1")
    assert any(c.kind == "out_of_bounds" for c in cells)


def test_nearby_cells_from_tick_dict():
    raw = _minimal_tick(
        creature_pos={"x": 2, "y": 2},
        items=[{"id": "w1", "type": "wall", "position": {"x": 2, "y": 1}}],
    )
    cells = nearby_cells_from_tick_dict(raw)
    assert len(cells) == 8
    assert cells[0]["kind"] == "wall"


def test_nearby_order_rotates_with_facing():
    world = WorldState(grid=WorldGrid(width=5, height=5), items=[])
    pos = GridCell(x=2, y=2)
    creatures = [CreatureState(id="c1", workflow_id="wf", position=pos, facing="N")]
    n_first = nearby_cells_clockwise("N", pos, 5, 5, world, creatures, exclude_creature_id="c1")[0]
    e_first = nearby_cells_clockwise("E", pos, 5, 5, world, creatures, exclude_creature_id="c1")[0]
    assert n_first.x == 2 and n_first.y == 1
    assert e_first.x == 3 and e_first.y == 2


def test_parse_tick_validates_creature_facing():
    raw = _minimal_tick(creature_pos={"x": 1, "y": 1}, facing="W")
    tick = parse_tick(raw)
    assert tick.creature.facing == "W"
