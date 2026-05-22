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
