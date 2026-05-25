"""Migrate legacy 2.4 board JSON to 2.5 definition-backed format."""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.domain.schemas.sandbox import (
    BALL_ITEM_TYPE,
    REGION_ITEM_TYPE,
    SANDBOX_SCHEMA_VERSION,
    SandboxItem,
)
from app.domain.schemas.sandbox_definitions import (
    BUILTIN_BALL_ID,
    BUILTIN_FOOD_ID,
    BUILTIN_WALL_ID,
)


def _migrate_item(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("definition_id"):
        return raw
    item_type = raw.get("type")
    out = dict(raw)
    out["schema_version"] = SANDBOX_SCHEMA_VERSION
    if item_type == "food":
        out["definition_id"] = BUILTIN_FOOD_ID
        out["definition_kind"] = "item"
        out["role"] = "pickable"
        out["builtin_slug"] = "builtin-food"
    elif item_type == BALL_ITEM_TYPE:
        out["definition_id"] = BUILTIN_BALL_ID
        out["definition_kind"] = "item"
        out["role"] = "pickable"
        out["builtin_slug"] = "builtin-ball"
    elif item_type == "wall":
        out["definition_id"] = BUILTIN_WALL_ID
        out["definition_kind"] = "terrain"
        out["role"] = "solid"
        out["builtin_slug"] = "builtin-wall"
    elif item_type == REGION_ITEM_TYPE:
        out["definition_kind"] = "region"
    else:
        raise ValueError(f"unmapped legacy item type: {item_type}")
    return out


def migrate_board_body(body: str) -> str:
    data = json.loads(body) if body else {}
    if not data:
        return body
    version = data.get("schema_version", "2.4.0")
    if version >= SANDBOX_SCHEMA_VERSION:
        return body
    data["schema_version"] = SANDBOX_SCHEMA_VERSION
    items = data.get("items") or []
    data["items"] = [_migrate_item(it) for it in items]
    return json.dumps(data)


def migrate_envelope_body(body: str) -> str:
    data = json.loads(body) if body else {}
    if not data:
        return body
    version = data.get("schema_version", "2.4.0")
    if version >= SANDBOX_SCHEMA_VERSION:
        return body
    data["schema_version"] = SANDBOX_SCHEMA_VERSION
    sandbox = data.get("sandbox") or {}
    world = sandbox.get("world") or {}
    items = world.get("items") or []
    world["items"] = [_migrate_item(it) for it in items]
    sandbox["world"] = world
    data["sandbox"] = sandbox
    return json.dumps(data)
