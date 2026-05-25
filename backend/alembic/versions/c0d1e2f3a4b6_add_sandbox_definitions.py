"""Add sandbox definition tables, seeds, and migrate board JSON to 2.5.0

Revision ID: c0d1e2f3a4b6
Revises: b9c0d1e2f3a4
Create Date: 2026-05-24

Summary:
  - item_definitions, terrain_definitions, fixture_definitions, creature_definitions, region_definitions
  - Seed builtin food/ball/wall definitions
  - Migrate sandbox_boards.body and sandbox session documents to schema 2.5.0
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "c0d1e2f3a4b6"
down_revision: Union[str, Sequence[str], None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BUILTIN_FOOD_ID = "a1000000-0000-4000-8000-000000000001"
BUILTIN_BALL_ID = "a1000000-0000-4000-8000-000000000002"
BUILTIN_WALL_ID = "a1000000-0000-4000-8000-000000000003"
NOW = datetime.now(timezone.utc).isoformat()


def _definition_tables(conn) -> None:
    tables = inspect(conn).get_table_names()
    if "item_definitions" not in tables:
        op.create_table(
            "item_definitions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("name", sa.String(), nullable=False, index=True),
            sa.Column("label", sa.String(), nullable=False, server_default=""),
            sa.Column("default_energy", sa.Integer(), nullable=True),
            sa.Column("default_color", sa.String(), nullable=True),
            sa.Column("shape", sa.String(), nullable=False, server_default="circle"),
            sa.Column("pickable", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("0"), index=True),
            sa.Column("builtin_slug", sa.String(), nullable=True, unique=True, index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if "terrain_definitions" not in tables:
        op.create_table(
            "terrain_definitions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("name", sa.String(), nullable=False, index=True),
            sa.Column("label", sa.String(), nullable=False, server_default=""),
            sa.Column("default_color", sa.String(), nullable=True),
            sa.Column("shape", sa.String(), nullable=False, server_default="rect"),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("0"), index=True),
            sa.Column("builtin_slug", sa.String(), nullable=True, unique=True, index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if "fixture_definitions" not in tables:
        op.create_table(
            "fixture_definitions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("name", sa.String(), nullable=False, index=True),
            sa.Column("label", sa.String(), nullable=False, server_default=""),
            sa.Column("workflow_id", sa.String(), nullable=False, server_default=""),
            sa.Column("color", sa.String(), nullable=True),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("0"), index=True),
            sa.Column("builtin_slug", sa.String(), nullable=True, unique=True, index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if "creature_definitions" not in tables:
        op.create_table(
            "creature_definitions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("name", sa.String(), nullable=False, index=True),
            sa.Column("label", sa.String(), nullable=False, server_default=""),
            sa.Column("workflow_id", sa.String(), nullable=False, server_default=""),
            sa.Column("default_color", sa.String(), nullable=False, server_default="#3B82F6"),
            sa.Column("default_facing", sa.String(), nullable=False, server_default="N"),
            sa.Column("default_inventory", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("0"), index=True),
            sa.Column("builtin_slug", sa.String(), nullable=True, unique=True, index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if "region_definitions" not in tables:
        op.create_table(
            "region_definitions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("name", sa.String(), nullable=False, index=True),
            sa.Column("label", sa.String(), nullable=False, server_default=""),
            sa.Column("color", sa.String(), nullable=False, server_default="#3B82F6"),
            sa.Column("trigger", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("0"), index=True),
            sa.Column("builtin_slug", sa.String(), nullable=True, unique=True, index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def _seed_definitions(conn) -> None:
    seeds = [
        (
            "item_definitions",
            BUILTIN_FOOD_ID,
            {
                "name": "Food",
                "label": "Food",
                "default_energy": 48,
                "shape": "circle",
                "pickable": True,
                "is_system": True,
                "builtin_slug": "builtin-food",
            },
        ),
        (
            "item_definitions",
            BUILTIN_BALL_ID,
            {
                "name": "Ball",
                "label": "Ball",
                "default_color": "#EF4444",
                "shape": "circle",
                "pickable": True,
                "is_system": True,
                "builtin_slug": "builtin-ball",
            },
        ),
        (
            "terrain_definitions",
            BUILTIN_WALL_ID,
            {
                "name": "Wall",
                "label": "Wall",
                "shape": "rect",
                "is_system": True,
                "builtin_slug": "builtin-wall",
            },
        ),
    ]
    for table, id_str, fields in seeds:
        slug = fields.get("builtin_slug")
        row = conn.execute(text(f"SELECT id FROM {table} WHERE id = :id"), {"id": id_str}).first()
        if row:
            continue
        if slug:
            row = conn.execute(
                text(f"SELECT id FROM {table} WHERE builtin_slug = :slug"),
                {"slug": slug},
            ).first()
            if row:
                continue
        cols = ["id", "created_at", "updated_at"] + list(fields.keys())
        vals = [id_str, NOW, NOW] + list(fields.values())
        placeholders = ", ".join(f":{c}" for c in cols)
        col_names = ", ".join(cols)
        params = dict(zip(cols, vals))
        conn.execute(text(f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"), params)


def _migrate_item(raw: dict) -> dict:
    if raw.get("definition_id"):
        return raw
    item_type = raw.get("type")
    out = dict(raw)
    if item_type == "food":
        out["definition_id"] = BUILTIN_FOOD_ID
        out["definition_kind"] = "item"
        out["role"] = "pickable"
        out["builtin_slug"] = "builtin-food"
    elif item_type == "ball":
        out["definition_id"] = BUILTIN_BALL_ID
        out["definition_kind"] = "item"
        out["role"] = "pickable"
        out["builtin_slug"] = "builtin-ball"
    elif item_type == "wall":
        out["definition_id"] = BUILTIN_WALL_ID
        out["definition_kind"] = "terrain"
        out["role"] = "solid"
        out["builtin_slug"] = "builtin-wall"
    elif item_type == "region":
        out["definition_kind"] = "region"
    elif item_type == "fixture":
        out["definition_kind"] = "fixture"
        out["role"] = "solid"
    return out


def _migrate_board_body(body: str) -> str:
    if not body or not body.strip():
        return body
    data = json.loads(body)
    if data.get("schema_version", "2.4.0") >= "2.5.0":
        return body
    data["schema_version"] = "2.5.0"
    data["items"] = [_migrate_item(it) for it in data.get("items") or []]
    return json.dumps(data)


def _migrate_envelope(body: str) -> str:
    if not body or not body.strip():
        return body
    data = json.loads(body)
    if data.get("schema_version", "2.4.0") >= "2.5.0":
        return body
    data["schema_version"] = "2.5.0"
    sandbox = data.get("sandbox") or {}
    world = sandbox.get("world") or {}
    world["items"] = [_migrate_item(it) for it in world.get("items") or []]
    sandbox["world"] = world
    data["sandbox"] = sandbox
    return json.dumps(data)


def upgrade() -> None:
    conn = op.get_bind()
    _definition_tables(conn)
    _seed_definitions(conn)
    if inspect(conn).has_table("sandbox_boards"):
        rows = conn.execute(text("SELECT id, body FROM sandbox_boards")).fetchall()
        for row in rows:
            new_body = _migrate_board_body(row.body or "")
            if new_body != (row.body or ""):
                conn.execute(
                    text("UPDATE sandbox_boards SET body = :body WHERE id = :id"),
                    {"body": new_body, "id": str(row.id)},
                )
    if inspect(conn).has_table("documents"):
        rows = conn.execute(
            text("SELECT id, body FROM documents WHERE description = 'Sandbox simulation state'")
        ).fetchall()
        for row in rows:
            new_body = _migrate_envelope(row.body or "")
            if new_body != (row.body or ""):
                conn.execute(
                    text("UPDATE documents SET body = :body WHERE id = :id"),
                    {"body": new_body, "id": str(row.id)},
                )


def downgrade() -> None:
    conn = op.get_bind()
    for table in (
        "region_definitions",
        "creature_definitions",
        "fixture_definitions",
        "terrain_definitions",
        "item_definitions",
    ):
        if inspect(conn).has_table(table):
            op.drop_table(table)
