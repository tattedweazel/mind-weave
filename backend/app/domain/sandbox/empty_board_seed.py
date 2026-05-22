"""Built-in empty sandbox board + idempotent DB seed."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.domain.document_json import deterministic_json_dumps
from app.domain.sandbox.builtins import EMPTY_SANDBOX_BOARD_ID
from app.domain.sandbox.constants import DEFAULT_GRID_HEIGHT, DEFAULT_GRID_WIDTH
from app.domain.schemas.sandbox import BoardDefinition, WorldGrid
from app.persistence.tables import SandboxBoard

EMPTY_BOARD_BUILTIN_SLUG = "empty_sandbox_board"


def empty_board_definition() -> BoardDefinition:
    return BoardDefinition(
        grid=WorldGrid(width=DEFAULT_GRID_WIDTH, height=DEFAULT_GRID_HEIGHT),
        items=[],
        creatures=[],
    )


def ensure_empty_sandbox_board(session: Session) -> SandboxBoard:
    """Ensure the system empty board row exists and matches canonical definition."""
    canonical = empty_board_definition()
    body = deterministic_json_dumps(canonical.model_dump(mode="json"))
    row = session.exec(
        select(SandboxBoard).where(SandboxBoard.builtin_slug == EMPTY_BOARD_BUILTIN_SLUG)
    ).first()
    now = datetime.now(timezone.utc)
    if row is None:
        row = SandboxBoard(
            id=EMPTY_SANDBOX_BOARD_ID,
            user_id=None,
            name="Empty Board",
            description="Default empty sandbox grid with no items or creatures",
            body=body,
            is_system=True,
            builtin_slug=EMPTY_BOARD_BUILTIN_SLUG,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row
    if row.body != body or row.name != "Empty Board":
        row.body = body
        row.name = "Empty Board"
        row.description = "Default empty sandbox grid with no items or creatures"
        row.updated_at = now
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def parse_board_body(body: str) -> BoardDefinition:
    data = json.loads(body) if body.strip() else {}
    return BoardDefinition.model_validate(data)
