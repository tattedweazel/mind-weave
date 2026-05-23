"""Tests for sandbox engine atomic navigation."""

from __future__ import annotations

from app.domain.sandbox.engine import SandboxEngine, initial_sandbox_state_clean
from app.domain.schemas.sandbox import (
    CreatureState,
    DecisionIntent,
    GridCell,
    SandboxItem,
    SandboxState,
    WorldGrid,
    WorldState,
)


def _state_with_creature(*, x: int = 2, y: int = 2, facing: str = "N") -> SandboxState:
    st = initial_sandbox_state_clean()
    st.creatures.append(
        CreatureState(
            id="c1",
            workflow_id="wf1",
            position=GridCell(x=x, y=y),
            facing=facing,  # type: ignore[arg-type]
        )
    )
    return st


def test_move_forward_updates_position():
    st = _state_with_creature(x=2, y=2, facing="N")
    eng = SandboxEngine()
    c = st.creatures[0]
    eng.apply_decision(st, c, DecisionIntent(action="move_forward"))
    assert c.position == GridCell(x=2, y=1)


def test_move_forward_blocked_by_wall():
    st = _state_with_creature(x=2, y=2, facing="N")
    st.world.items.append(SandboxItem(id="w1", type="wall", position=GridCell(x=2, y=1)))
    eng = SandboxEngine()
    c = st.creatures[0]
    eng.apply_decision(st, c, DecisionIntent(action="move_forward"))
    assert c.position == GridCell(x=2, y=2)


def test_turn_left_and_right():
    st = _state_with_creature(facing="N")
    eng = SandboxEngine()
    c = st.creatures[0]
    eng.apply_decision(st, c, DecisionIntent(action="turn_left"))
    assert c.facing == "W"
    eng.apply_decision(st, c, DecisionIntent(action="turn_right"))
    assert c.facing == "N"


def test_idle_records_recent_action():
    st = _state_with_creature(x=1, y=1)
    st.tick = 3
    eng = SandboxEngine()
    c = st.creatures[0]
    eng.apply_decision(st, c, DecisionIntent(action="idle", reason="wait"))
    assert len(st.recent_actions) == 1
    assert st.recent_actions[0].action == "idle"
    assert st.recent_actions[0].reason == "wait"


def test_move_forward_blocked_by_creature():
    st = _state_with_creature(x=2, y=2, facing="E")
    st.creatures.append(
        CreatureState(
            id="c2",
            workflow_id="wf2",
            position=GridCell(x=3, y=2),
            facing="W",
        )
    )
    eng = SandboxEngine()
    eng.apply_decision(st, st.creatures[0], DecisionIntent(action="move_forward"))
    assert st.creatures[0].position == GridCell(x=2, y=2)


def test_board_creature_default_facing():
    from app.domain.schemas.sandbox import BoardCreaturePlacement, BoardDefinition

    board = BoardDefinition(
        grid=WorldGrid(width=4, height=4),
        creatures=[
            BoardCreaturePlacement(id="c1", workflow_id="wf", position=GridCell(x=1, y=1)),
        ],
    )
    from app.domain.sandbox.engine import sandbox_state_from_board

    st = sandbox_state_from_board(board)
    assert st.creatures[0].facing == "N"


def test_board_creature_color_roundtrip():
    from app.domain.schemas.sandbox import BoardCreaturePlacement, BoardDefinition
    from app.domain.sandbox.engine import board_definition_from_sandbox_state, sandbox_state_from_board

    board = BoardDefinition(
        grid=WorldGrid(width=4, height=4),
        creatures=[
            BoardCreaturePlacement(
                id="c1",
                workflow_id="wf",
                position=GridCell(x=1, y=1),
                color="#AABBCC",
            ),
        ],
    )
    st = sandbox_state_from_board(board)
    assert st.creatures[0].color == "#AABBCC"
    saved = board_definition_from_sandbox_state(st)
    assert saved.creatures[0].color == "#AABBCC"


def test_place_creature_interaction_respects_facing_and_color():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(
        st,
        [
            {
                "type": "place_creature",
                "cell": {"x": 2, "y": 2},
                "workflow_id": "wf1",
                "facing": "E",
                "color": "#abc",
            }
        ],
    )
    assert len(st.creatures) == 1
    assert st.creatures[0].facing == "E"
    assert st.creatures[0].color == "#AABBCC"
    assert st.tick == 0


def test_place_creature_skips_invalid_color():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(
        st,
        [
            {
                "type": "place_creature",
                "cell": {"x": 2, "y": 2},
                "workflow_id": "wf1",
                "color": "bad",
            }
        ],
    )
    assert st.creatures == []


def test_place_creature_skips_missing_color():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(
        st,
        [
            {
                "type": "place_creature",
                "cell": {"x": 2, "y": 2},
                "workflow_id": "wf1",
            }
        ],
    )
    assert st.creatures == []


def test_place_region_on_occupied_cell_coexists_with_food():
    st = initial_sandbox_state_clean()
    st.world.items.append(SandboxItem(id="f1", type="food", position=GridCell(x=1, y=1), energy=48))
    eng = SandboxEngine()
    eng.apply_interactions(
        st,
        [{"type": "place_region", "cell": {"x": 1, "y": 1}, "color": "#FF0000"}],
    )
    types = {it.type for it in st.world.items if it.position.x == 1 and it.position.y == 1}
    assert types == {"food", "region"}
    region = next(it for it in st.world.items if it.type == "region")
    assert region.color == "#FF0000"


def test_remove_item_leaves_region():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(
        st,
        [
            {"type": "place_region", "cell": {"x": 0, "y": 0}, "color": "#3B82F6"},
            {"type": "place_item", "cell": {"x": 0, "y": 0}, "item_type": "wall"},
            {"type": "remove_item", "cell": {"x": 0, "y": 0}},
        ],
    )
    assert len(st.world.items) == 1
    assert st.world.items[0].type == "region"


def test_remove_region_leaves_food():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(
        st,
        [
            {"type": "place_region", "cell": {"x": 2, "y": 2}, "color": "#00FF00"},
            {"type": "place_item", "cell": {"x": 2, "y": 2}, "item_type": "food"},
            {"type": "remove_region", "cell": {"x": 2, "y": 2}},
        ],
    )
    assert len(st.world.items) == 1
    assert st.world.items[0].type == "food"


def test_place_region_replaces_existing_region():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(
        st,
        [
            {"type": "place_region", "cell": {"x": 1, "y": 1}, "color": "#111111"},
            {"type": "place_region", "cell": {"x": 1, "y": 1}, "color": "#222222"},
        ],
    )
    regions = [it for it in st.world.items if it.type == "region"]
    assert len(regions) == 1
    assert regions[0].color == "#222222"


def test_move_forward_through_region():
    st = _state_with_creature(x=2, y=2, facing="N")
    st.world.items.append(
        SandboxItem(
            id="r1",
            type="region",
            position=GridCell(x=2, y=1),
            color="#3B82F6",
        )
    )
    eng = SandboxEngine()
    eng.apply_decision(st, st.creatures[0], DecisionIntent(action="move_forward"))
    assert st.creatures[0].position == GridCell(x=2, y=1)


def test_place_region_skips_invalid_color():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(st, [{"type": "place_region", "cell": {"x": 0, "y": 0}, "color": "bad"}])
    assert not any(it.type == "region" for it in st.world.items)


def test_place_region_out_of_bounds_noop():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(st, [{"type": "place_region", "cell": {"x": 99, "y": 99}, "color": "#FF0000"}])
    assert st.world.items == []
