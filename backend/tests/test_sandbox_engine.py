"""Tests for sandbox engine atomic navigation."""

from __future__ import annotations

from app.domain.sandbox.engine import SandboxEngine, initial_sandbox_state_clean
from app.domain.schemas.sandbox import (
    CreatureState,
    DecisionIntent,
    GridCell,
    InventoryItem,
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


def test_remove_item_on_fixture_cell_preserves_fixture():
    from app.domain.schemas.sandbox import FIXTURE_ITEM_TYPE

    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(
        st,
        [
            {"type": "place_fixture", "cell": {"x": 2, "y": 2}, "definition_id": "fx-1"},
            {"type": "place_item", "cell": {"x": 2, "y": 2}, "item_type": "food"},
            {"type": "remove_item", "cell": {"x": 2, "y": 2}},
        ],
    )
    cell_items = [it for it in st.world.items if it.position.x == 2 and it.position.y == 2]
    assert len(cell_items) == 1
    assert cell_items[0].type == FIXTURE_ITEM_TYPE


def test_remove_item_with_item_id_removes_single_pickable():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(
        st,
        [
            {"type": "place_item", "cell": {"x": 1, "y": 1}, "item_type": "food"},
            {"type": "place_item", "cell": {"x": 1, "y": 1}, "item_type": "ball", "color": "#AABBCC"},
        ],
    )
    food = next(it for it in st.world.items if it.type == "food")
    eng.apply_interactions(
        st,
        [{"type": "remove_item", "cell": {"x": 1, "y": 1}, "item_id": food.id}],
    )
    types = {it.type for it in st.world.items if it.position.x == 1 and it.position.y == 1}
    assert types == {"ball"}


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
            {"type": "place_region", "cell": {"x": 1, "y": 1}, "color": "#111111", "label": "first"},
            {"type": "place_region", "cell": {"x": 1, "y": 1}, "color": "#222222", "label": "second"},
        ],
    )
    regions = [it for it in st.world.items if it.type == "region"]
    assert len(regions) == 1
    assert regions[0].color == "#222222"
    assert regions[0].label == "second"


def test_place_region_persists_label():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(
        st,
        [{"type": "place_region", "cell": {"x": 1, "y": 1}, "color": "#3B82F6", "label": "target"}],
    )
    region = next(it for it in st.world.items if it.type == "region")
    assert region.label == "target"


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


def test_place_ball_via_interaction():
    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(
        st,
        [{"type": "place_item", "cell": {"x": 1, "y": 1}, "item_type": "ball", "color": "#FF00FF"}],
    )
    ball = next(it for it in st.world.items if it.type == "ball")
    assert ball.color == "#FF00FF"
    assert ball.position == GridCell(x=1, y=1)


def test_pick_up_ball_forward_adjacent():
    st = _state_with_creature(x=2, y=2, facing="N")
    st.world.items.append(
        SandboxItem(id="b1", type="ball", position=GridCell(x=2, y=1), color="#3B82F6")
    )
    eng = SandboxEngine()
    eng.apply_decision(st, st.creatures[0], DecisionIntent(action="pick_up_item"))
    assert not any(it.type == "ball" for it in st.world.items)
    assert len(st.creatures[0].inventory) == 1
    assert st.creatures[0].inventory[0].type == "ball"
    assert st.creatures[0].inventory[0].color == "#3B82F6"


def test_pick_up_item_by_id_on_stacked_cell():
    st = _state_with_creature(x=2, y=2, facing="N")
    st.world.items.extend(
        [
            SandboxItem(id="f1", type="food", position=GridCell(x=2, y=1), energy=10),
            SandboxItem(id="f2", type="food", position=GridCell(x=2, y=1), energy=20),
        ]
    )
    eng = SandboxEngine()
    eng.apply_decision(
        st,
        st.creatures[0],
        DecisionIntent(action="pick_up_item", item_id="f1"),
    )
    remaining = [it for it in st.world.items if it.position == GridCell(x=2, y=1)]
    assert len(remaining) == 1
    assert remaining[0].id == "f2"
    assert len(st.creatures[0].inventory) == 1
    assert st.creatures[0].inventory[0].energy == 10


def test_pick_up_all_on_fixture_cell():
    from app.domain.schemas.sandbox import FIXTURE_ITEM_TYPE

    st = _state_with_creature(x=2, y=2, facing="N")
    st.world.items.extend(
        [
            SandboxItem(
                id="fx1",
                type=FIXTURE_ITEM_TYPE,
                definition_kind="fixture",
                role="solid",
                position=GridCell(x=2, y=1),
            ),
            SandboxItem(id="f1", type="food", position=GridCell(x=2, y=1), energy=10),
            SandboxItem(
                id="b1",
                type="ball",
                position=GridCell(x=2, y=1),
                color="#AABBCC",
            ),
        ]
    )
    eng = SandboxEngine()
    eng.apply_decision(
        st,
        st.creatures[0],
        DecisionIntent(action="pick_up_item", pick_all=True),
    )
    cell_items = [it for it in st.world.items if it.position == GridCell(x=2, y=1)]
    assert len(cell_items) == 1
    assert cell_items[0].type == FIXTURE_ITEM_TYPE
    assert len(st.creatures[0].inventory) == 2
    assert {entry.type for entry in st.creatures[0].inventory} == {"food", "ball"}


def test_place_item_from_inventory_forward():
    st = _state_with_creature(x=2, y=2, facing="N")
    st.creatures[0].inventory = [InventoryItem(type="ball", color="#AABBCC")]
    eng = SandboxEngine()
    eng.apply_decision(
        st,
        st.creatures[0],
        DecisionIntent(action="place_item", item_type="ball"),
    )
    ball = next(it for it in st.world.items if it.type == "ball")
    assert ball.position == GridCell(x=2, y=1)
    assert ball.color == "#AABBCC"
    assert st.creatures[0].inventory == []


def test_place_item_filters_by_type():
    st = _state_with_creature(x=2, y=2, facing="N")
    st.creatures[0].inventory = [
        InventoryItem(type="food", energy=10),
        InventoryItem(type="ball", color="#111111"),
    ]
    eng = SandboxEngine()
    eng.apply_decision(
        st,
        st.creatures[0],
        DecisionIntent(action="place_item", item_type="ball"),
    )
    ball = next(it for it in st.world.items if it.type == "ball")
    assert ball.color == "#111111"
    assert len(st.creatures[0].inventory) == 1
    assert st.creatures[0].inventory[0].type == "food"


def test_place_item_by_inventory_index():
    st = _state_with_creature(x=2, y=2, facing="N")
    st.creatures[0].inventory = [
        InventoryItem(type="food", energy=10),
        InventoryItem(type="ball", color="#222222"),
    ]
    eng = SandboxEngine()
    eng.apply_decision(
        st,
        st.creatures[0],
        DecisionIntent(action="place_item", item_type="food", inventory_index=0),
    )
    food = next(it for it in st.world.items if it.type == "food")
    assert food.position == GridCell(x=2, y=1)
    assert food.energy == 10
    assert len(st.creatures[0].inventory) == 1
    assert st.creatures[0].inventory[0].type == "ball"
    assert st.creatures[0].inventory[0].color == "#222222"


def test_pick_up_and_place_definition_backed_item_preserves_definition_id():
    st = _state_with_creature(x=2, y=2, facing="N")
    st.world.items.append(
        SandboxItem(
            id="key1",
            definition_id="item-def-golden-key",
            definition_kind="item",
            role="pickable",
            position=GridCell(x=2, y=1),
            energy=10,
        )
    )
    eng = SandboxEngine()
    eng.apply_decision(st, st.creatures[0], DecisionIntent(action="pick_up_item"))
    assert len(st.creatures[0].inventory) == 1
    assert st.creatures[0].inventory[0].definition_id == "item-def-golden-key"
    assert st.creatures[0].inventory[0].energy == 10

    eng.apply_decision(
        st,
        st.creatures[0],
        DecisionIntent(action="place_item", item_type="food", inventory_index=0),
    )
    placed = next(
        it for it in st.world.items if it.position == GridCell(x=2, y=1)
    )
    assert placed.definition_id == "item-def-golden-key"
    assert placed.energy == 10
    assert st.creatures[0].inventory == []


def test_pick_up_definition_backed_item_uses_definition_default_energy():
    from app.domain.sandbox.item_helpers import ItemDefinitionDefaults

    st = _state_with_creature(x=2, y=2, facing="N")
    st.world.items.append(
        SandboxItem(
            id="milk1",
            definition_id="item-def-milk",
            definition_kind="item",
            role="pickable",
            position=GridCell(x=2, y=1),
        )
    )
    defaults = {"item-def-milk": ItemDefinitionDefaults(default_energy=25, default_color="#FFFFFF")}
    eng = SandboxEngine()
    eng.apply_decision(
        st,
        st.creatures[0],
        DecisionIntent(action="pick_up_item"),
        definition_defaults=defaults,
    )
    assert len(st.creatures[0].inventory) == 1
    assert st.creatures[0].inventory[0].definition_id == "item-def-milk"
    assert st.creatures[0].inventory[0].energy == 25
    assert not any(it.id == "milk1" for it in st.world.items)


def test_pick_up_fails_without_removing_world_item_when_unconvertible():
    st = _state_with_creature(x=2, y=2, facing="N")
    st.world.items.append(
        SandboxItem(
            id="milk1",
            definition_id="item-def-milk",
            definition_kind="item",
            role="pickable",
            position=GridCell(x=2, y=1),
        )
    )
    eng = SandboxEngine()
    eng.apply_decision(st, st.creatures[0], DecisionIntent(action="pick_up_item"))
    assert st.creatures[0].inventory == []
    assert any(it.id == "milk1" for it in st.world.items)


def test_board_definition_accepts_milk_like_item_with_energy_only():
    from app.domain.schemas.sandbox import BoardDefinition, WorldGrid

    board = BoardDefinition(
        grid=WorldGrid(width=4, height=4),
        items=[
            SandboxItem(
                id="milk1",
                definition_id="item-def-milk",
                definition_kind="item",
                role="pickable",
                position=GridCell(x=1, y=1),
                energy=25,
            ),
        ],
    )
    assert board.items[0].energy == 25
    assert board.items[0].color is None
