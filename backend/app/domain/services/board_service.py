"""Sandbox board CRUD."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Session, select

from app.domain.document_json import deterministic_json_dumps
from app.domain.sandbox.empty_board_seed import EMPTY_BOARD_BUILTIN_SLUG, empty_board_definition, parse_board_body
from app.domain.schemas.sandbox import BoardDefinition
from app.persistence.tables import SandboxBoard


class BoardService:
    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session = session
        self.user_id = user_id

    def list_boards(self) -> List[SandboxBoard]:
        rows = self.session.exec(
            select(SandboxBoard)
            .where((SandboxBoard.user_id == self.user_id) | (SandboxBoard.is_system == True))  # noqa: E712
            .order_by(SandboxBoard.is_system.desc(), SandboxBoard.updated_at.desc())
        ).all()
        return list(rows)

    def get_board(self, board_id: uuid.UUID) -> Optional[SandboxBoard]:
        row = self.session.get(SandboxBoard, board_id)
        if not row:
            return None
        if row.is_system or row.user_id == self.user_id:
            return row
        return None

    def get_board_definition(self, board_id: uuid.UUID) -> Optional[BoardDefinition]:
        row = self.get_board(board_id)
        if not row:
            return None
        return parse_board_body(row.body)

    def create_board(
        self,
        *,
        name: str,
        description: str = "",
        definition: Optional[BoardDefinition] = None,
    ) -> SandboxBoard:
        defn = definition or empty_board_definition()
        now = datetime.now(timezone.utc)
        row = SandboxBoard(
            user_id=self.user_id,
            name=name.strip() or "Untitled Board",
            description=description,
            body=deterministic_json_dumps(defn.model_dump(mode="json")),
            is_system=False,
            builtin_slug=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def update_board(
        self,
        board_id: uuid.UUID,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        definition: Optional[BoardDefinition] = None,
    ) -> Optional[SandboxBoard]:
        row = self.get_board(board_id)
        if not row or row.is_system:
            return None
        if name is not None:
            row.name = name.strip() or row.name
        if description is not None:
            row.description = description
        if definition is not None:
            row.body = deterministic_json_dumps(definition.model_dump(mode="json"))
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def delete_board(self, board_id: uuid.UUID) -> bool:
        row = self.get_board(board_id)
        if not row or row.is_system:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def duplicate_board(self, board_id: uuid.UUID, *, name: Optional[str] = None) -> Optional[SandboxBoard]:
        row = self.get_board(board_id)
        if not row:
            return None
        defn = parse_board_body(row.body)
        dup_name = name or f"{row.name} (copy)"
        return self.create_board(name=dup_name, description=row.description, definition=defn)

    def get_empty_board_id(self) -> uuid.UUID:
        row = self.session.exec(
            select(SandboxBoard).where(SandboxBoard.builtin_slug == EMPTY_BOARD_BUILTIN_SLUG)
        ).first()
        if row:
            return row.id
        from app.domain.sandbox.builtins import EMPTY_SANDBOX_BOARD_ID

        return EMPTY_SANDBOX_BOARD_ID
