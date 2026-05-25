"""Tests for sandbox definition CRUD API."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def test_item_definition_crud_smoke(client: TestClient):
    name = f"Test Item {uuid.uuid4().hex[:8]}"
    create = client.post(
        "/api/v1/sandbox-definitions/items",
        json={"name": name, "label": "Test", "custom_metadata": {"energy": 10}},
    )
    assert create.status_code == 201, create.text
    item = create.json()
    item_id = item["id"]

    listed = client.get("/api/v1/sandbox-definitions/items")
    assert listed.status_code == 200
    assert any(x["id"] == item_id for x in listed.json())

    updated = client.put(
        f"/api/v1/sandbox-definitions/items/{item_id}",
        json={"label": "Updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["label"] == "Updated"

    deleted = client.delete(f"/api/v1/sandbox-definitions/items/{item_id}")
    assert deleted.status_code == 204


def test_seeded_definitions_visible(client: TestClient):
    items = client.get("/api/v1/sandbox-definitions/items").json()
    terrain = client.get("/api/v1/sandbox-definitions/terrain").json()
    slugs = {x.get("builtin_slug") for x in items + terrain}
    assert "builtin-food" in slugs
    assert "builtin-ball" in slugs
    assert "builtin-wall" in slugs


def test_stacked_fixture_and_food_coexist():
    from app.domain.sandbox.engine import SandboxEngine, initial_sandbox_state_clean
    from app.domain.schemas.sandbox import FIXTURE_ITEM_TYPE, SandboxItem, GridCell

    st = initial_sandbox_state_clean()
    eng = SandboxEngine()
    eng.apply_interactions(
        st,
        [
            {"type": "place_fixture", "cell": {"x": 2, "y": 2}, "definition_id": "fx-1"},
            {"type": "place_item", "cell": {"x": 2, "y": 2}, "item_type": "food"},
        ],
    )
    cell_items = [it for it in st.world.items if it.position.x == 2 and it.position.y == 2]
    kinds = {it.type for it in cell_items}
    assert FIXTURE_ITEM_TYPE in kinds
    assert "food" in kinds


def test_use_fixture_records_action():
    from app.domain.sandbox.engine import SandboxEngine, initial_sandbox_state_clean
    from app.domain.schemas.sandbox import DecisionIntent, FIXTURE_ITEM_TYPE, SandboxItem, GridCell

    st = initial_sandbox_state_clean()
    st.creatures.append(
        __import__(
            "app.domain.schemas.sandbox", fromlist=["CreatureState"]
        ).CreatureState(
            id="c1",
            workflow_id="wf",
            position=GridCell(x=2, y=3),
            facing="N",
        )
    )
    st.world.items.append(
        SandboxItem(
            id="fx1",
            type=FIXTURE_ITEM_TYPE,
            definition_kind="fixture",
            role="solid",
            definition_id="def-1",
            position=GridCell(x=2, y=2),
            label="Steamer",
        )
    )
    eng = SandboxEngine()
    eng.apply_decision(st, st.creatures[0], DecisionIntent(action="use_fixture"))
    assert st.recent_actions[-1].action == "use_fixture"
