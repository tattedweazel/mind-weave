"""Sandbox domain engine unit tests (no LLM)."""

import random

from app.domain.sandbox.constants import EAT_FOOD_DRAIN_PER_TICK, MAX_RETRY
from app.domain.sandbox.engine import SandboxEngine, initial_sandbox_state_clean, resize_world_grid
from app.domain.sandbox.starter_behavior import starter_behavior_decision
from app.domain.schemas.sandbox import GridCell, PetIntent, SandboxItem, SandboxTickInput


def test_initial_state():
    st = initial_sandbox_state_clean()
    assert st.tick == 0
    assert st.pet.intent is None
    assert st.world.grid.width >= 1


def test_starter_decision_wander_when_comfortable():
    st = initial_sandbox_state_clean()
    inp = SandboxTickInput(
        tick=1,
        pet=st.pet,
        world=st.world,
        recent_actions=[],
    )
    dec = starter_behavior_decision(inp)
    assert dec.action == "wander"


def test_interaction_place_food_place_item():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(st, [{"type": "place_item", "cell": {"x": 1, "y": 1}, "item_type": "food"}])
    assert len(st.world.items) == 1
    assert st.world.items[0].type == "food"
    assert st.world.items[0].position.x == 1 and st.world.items[0].position.y == 1


def test_interaction_place_food_two_distinct_cells():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(
        st,
        [
            {"type": "place_item", "cell": {"x": 1, "y": 1}, "item_type": "food"},
            {"type": "place_item", "cell": {"x": 2, "y": 2}, "item_type": "food"},
        ],
    )
    assert len(st.world.items) == 2
    positions = {(it.position.x, it.position.y) for it in st.world.items}
    assert positions == {(1, 1), (2, 2)}
    assert all(it.type == "food" for it in st.world.items)


def test_interaction_place_food_same_cell_second_is_noop():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(st, [{"type": "place_item", "cell": {"x": 1, "y": 1}, "item_type": "food"}])
    assert len(st.world.items) == 1
    eng.apply_interactions(st, [{"type": "place_item", "cell": {"x": 1, "y": 1}, "item_type": "food"}])
    assert len(st.world.items) == 1


def test_interaction_remove_item():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(st, [{"type": "place_item", "cell": {"x": 1, "y": 1}, "item_type": "food"}])
    assert len(st.world.items) == 1
    eng.apply_interactions(st, [{"type": "remove_item", "cell": {"x": 1, "y": 1}}])
    assert st.world.items == []


def test_interaction_cell_click_legacy_toggle():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(st, [{"type": "cell_click", "cell": {"x": 1, "y": 1}}])
    assert len(st.world.items) == 1
    eng.apply_interactions(st, [{"type": "cell_click", "cell": {"x": 1, "y": 1}}])
    assert st.world.items == []


def test_place_item_skips_when_pet_on_cell():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    px, py = st.pet.position.x, st.pet.position.y
    eng.apply_interactions(st, [{"type": "place_item", "cell": {"x": px, "y": py}, "item_type": "food"}])
    assert st.world.items == []


def test_resize_world_grid_clamps_pet_drops_oob_items_clears_intent():
    st = initial_sandbox_state_clean()
    st.world.items = [
        SandboxItem(id="keep", type="food", position=GridCell(x=1, y=1)),
        SandboxItem(id="gone", type="food", position=GridCell(x=20, y=20)),
    ]
    st.pet.intent = PetIntent(
        action="move_to",
        status="in_progress",
        target_item_id="gone",
        target_cell=None,
        reason=None,
        retry_count=0,
    )
    resize_world_grid(st, 8, 8)
    assert st.world.grid.width == 8 and st.world.grid.height == 8
    assert len(st.world.items) == 1 and st.world.items[0].id == "keep"
    assert st.pet.intent is None
    assert 0 <= st.pet.position.x < 8 and 0 <= st.pet.position.y < 8


def test_move_to_target_cell_blocked_completes_when_adjacent8():
    """Food on target cell: cannot step onto it; finish move_to when 8-adjacent."""
    st = initial_sandbox_state_clean()
    st.pet.position = GridCell(x=0, y=1)
    st.world.items = [
        SandboxItem(id="food", type="food", position=GridCell(x=0, y=0), energy=10),
    ]
    st.pet.intent = PetIntent(
        action="move_to",
        status="in_progress",
        target_item_id=None,
        target_cell=GridCell(x=0, y=0),
        reason=None,
        retry_count=0,
    )
    eng = SandboxEngine()
    assert eng.continue_intent_step(st) is True
    assert st.pet.intent is None


def test_move_to_target_cell_empty_remains_in_progress_until_reached():
    st = initial_sandbox_state_clean()
    st.pet.position = GridCell(x=3, y=3)
    st.pet.intent = PetIntent(
        action="move_to",
        status="in_progress",
        target_item_id=None,
        target_cell=GridCell(x=0, y=0),
        reason=None,
        retry_count=0,
    )
    eng = SandboxEngine(rng=random.Random(0))
    assert eng.continue_intent_step(st) is True
    assert st.pet.intent is not None
    assert st.pet.intent.status == "in_progress"


def test_move_to_target_cell_empty_completes_when_already_on_cell():
    st = initial_sandbox_state_clean()
    st.pet.position = GridCell(x=2, y=2)
    st.pet.intent = PetIntent(
        action="move_to",
        status="in_progress",
        target_item_id=None,
        target_cell=GridCell(x=2, y=2),
        reason=None,
        retry_count=0,
    )
    eng = SandboxEngine()
    assert eng.continue_intent_step(st) is True
    assert st.pet.intent is None


def test_eat_nearby_depletes_food_then_completes():
    st = initial_sandbox_state_clean()
    st.pet.position = GridCell(x=2, y=2)
    energy = EAT_FOOD_DRAIN_PER_TICK * 3
    st.world.items = [
        SandboxItem(id="f1", type="food", position=GridCell(x=3, y=2), energy=energy),
    ]
    st.pet.intent = PetIntent(
        action="eat_nearby",
        status="in_progress",
        target_item_id="f1",
        target_cell=None,
        reason=None,
        retry_count=0,
    )
    eng = SandboxEngine()
    for _ in range(3):
        assert st.pet.intent is not None
        assert eng.continue_intent_step(st) is True
    assert st.pet.intent is None
    assert st.world.items == []


def test_eat_nearby_resolves_without_target_when_adjacent_food_exists():
    st = initial_sandbox_state_clean()
    st.pet.position = GridCell(x=2, y=2)
    st.world.items = [
        SandboxItem(id="f1", type="food", position=GridCell(x=2, y=1), energy=EAT_FOOD_DRAIN_PER_TICK),
    ]
    st.pet.intent = PetIntent(
        action="eat_nearby",
        status="in_progress",
        target_item_id=None,
        target_cell=None,
        reason=None,
        retry_count=0,
    )
    eng = SandboxEngine()
    assert eng.continue_intent_step(st) is True
    assert st.pet.intent is None
    assert st.world.items == []


def test_eat_nearby_wrong_target_id_still_eats_first_adjacent_food():
    st = initial_sandbox_state_clean()
    st.pet.position = GridCell(x=2, y=2)
    st.world.items = [
        SandboxItem(id="near", type="food", position=GridCell(x=2, y=1), energy=EAT_FOOD_DRAIN_PER_TICK),
    ]
    st.pet.intent = PetIntent(
        action="eat_nearby",
        status="in_progress",
        target_item_id="wrong-id",
        target_cell=None,
        reason=None,
        retry_count=0,
    )
    eng = SandboxEngine()
    assert eng.continue_intent_step(st) is True
    assert st.pet.intent is None
    assert st.world.items == []


def test_eat_nearby_no_adjacent_food_clears_after_max_retries():
    st = initial_sandbox_state_clean()
    st.pet.position = GridCell(x=2, y=2)
    st.world.items = [
        SandboxItem(id="far", type="food", position=GridCell(x=2, y=5), energy=24),
    ]
    st.pet.intent = PetIntent(
        action="eat_nearby",
        status="in_progress",
        target_item_id="far",
        target_cell=None,
        reason=None,
        retry_count=0,
    )
    eng = SandboxEngine()
    for _ in range(MAX_RETRY + 1):
        assert eng.continue_intent_step(st) is True
    assert st.pet.intent is None


def test_continue_intent_unknown_action_clears_intent():
    st = initial_sandbox_state_clean()
    st.pet.intent = PetIntent.model_construct(
        action="not_a_decision_action",
        status="in_progress",
        target_item_id=None,
        target_cell=None,
        reason=None,
        retry_count=0,
    )
    eng = SandboxEngine()
    assert eng.continue_intent_step(st) is True
    assert st.pet.intent is None
