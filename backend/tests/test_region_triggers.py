"""Region trigger evaluation (all modes)."""

from __future__ import annotations

from app.domain.sandbox.engine import SandboxEngine, initial_sandbox_state_clean
from app.domain.sandbox.region_triggers import (
    RegionTriggerEvent,
    evaluate_transition_triggers,
    evaluate_while_inside_triggers,
)
from app.domain.schemas.sandbox import (
    CreatureState,
    GridCell,
    RegionTriggerConfig,
    RegionTriggerSessionState,
    SandboxItem,
    default_region_trigger,
)


def _region(x: int, y: int, *, region_id: str = "r1", mode: str = "enter", wf: str = "wf-pause") -> SandboxItem:
    return SandboxItem(
        id=region_id,
        type="region",
        position=GridCell(x=x, y=y),
        color="#FF0000",
        label="Goal",
        trigger=RegionTriggerConfig(enabled=True, mode=mode, workflow_id=wf, inputs={}),
    )


def _creature(x: int, y: int, *, cid: str = "c1") -> CreatureState:
    return CreatureState(
        id=cid,
        workflow_id="brain-wf",
        position=GridCell(x=x, y=y),
        facing="N",
    )


def test_enter_trigger_on_move_into_region():
    st = initial_sandbox_state_clean()
    st.world.items.append(_region(2, 2, mode="enter"))
    creature = _creature(2, 1)
    st.creatures.append(creature)
    session = RegionTriggerSessionState()

    creature.position = GridCell(x=2, y=2)
    events, session = evaluate_transition_triggers(
        st,
        creature=creature,
        previous_position=GridCell(x=2, y=1),
        session_state=session,
    )

    assert len(events) == 1
    assert events[0].mode == "enter"
    assert events[0].region_id == "r1"
    assert events[0].workflow_id == "wf-pause"


def test_exit_trigger_on_move_out_of_region():
    st = initial_sandbox_state_clean()
    st.world.items.append(_region(2, 2, mode="exit"))
    creature = _creature(2, 2)
    st.creatures.append(creature)
    session = RegionTriggerSessionState()

    creature.position = GridCell(x=2, y=1)
    events, _ = evaluate_transition_triggers(
        st,
        creature=creature,
        previous_position=GridCell(x=2, y=2),
        session_state=session,
    )

    assert len(events) == 1
    assert events[0].mode == "exit"


def test_on_enter_once_fires_once_per_creature():
    st = initial_sandbox_state_clean()
    st.world.items.append(_region(2, 2, mode="on_enter_once"))
    creature = _creature(2, 1)
    st.creatures.append(creature)
    session = RegionTriggerSessionState()

    creature.position = GridCell(x=2, y=2)
    events1, session = evaluate_transition_triggers(
        st,
        creature=creature,
        previous_position=GridCell(x=2, y=1),
        session_state=session,
    )
    assert len(events1) == 1
    assert events1[0].mode == "on_enter_once"

    creature.position = GridCell(x=2, y=1)
    events2, session = evaluate_transition_triggers(
        st,
        creature=creature,
        previous_position=GridCell(x=2, y=2),
        session_state=session,
    )
    assert events2 == []

    creature.position = GridCell(x=2, y=2)
    events3, _ = evaluate_transition_triggers(
        st,
        creature=creature,
        previous_position=GridCell(x=2, y=1),
        session_state=session,
    )
    assert events3 == []


def test_while_inside_fires_each_tick():
    st = initial_sandbox_state_clean()
    st.world.items.append(_region(2, 2, mode="while_inside"))
    st.creatures.append(_creature(2, 2))
    session = RegionTriggerSessionState()

    events = evaluate_while_inside_triggers(st, session_state=session)
    assert len(events) == 1
    assert events[0].mode == "while_inside"


def test_disabled_trigger_emits_nothing():
    st = initial_sandbox_state_clean()
    st.world.items.append(
        SandboxItem(
            id="r1",
            type="region",
            position=GridCell(x=2, y=2),
            color="#FF0000",
            trigger=default_region_trigger(),
        )
    )
    creature = _creature(2, 1)
    st.creatures.append(creature)
    session = RegionTriggerSessionState()

    creature.position = GridCell(x=2, y=2)
    events, _ = evaluate_transition_triggers(
        st,
        creature=creature,
        previous_position=GridCell(x=2, y=1),
        session_state=session,
    )
    assert events == []


def test_engine_apply_decision_returns_transition_events():
    st = initial_sandbox_state_clean()
    st.world.items.append(_region(2, 2, mode="enter"))
    creature = _creature(2, 3)
    st.creatures.append(creature)
    eng = SandboxEngine()
    session = RegionTriggerSessionState()

    from app.domain.schemas.sandbox import DecisionIntent

    events, session = eng.apply_decision(
        st,
        creature,
        DecisionIntent(action="move_forward"),
        region_trigger_session=session,
    )
    assert creature.position == GridCell(x=2, y=2)
    assert len(events) == 1
    assert isinstance(events[0], RegionTriggerEvent)
