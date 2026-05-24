"""
Board Project Service
=====================
CRUD for per-user board folders. The reserved **Shared** folder is created
per user and holds default and unassigned boards.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.domain.schemas.board_projects import BoardProjectCreate, BoardProjectUpdate
from app.persistence.tables import BoardProject, SandboxBoard

SHARED_PROJECT_NAME = "Shared"
SHARED_NAME_LOWER = "shared"


def normalize_project_name(name: str) -> str:
    return name.strip()


def project_name_lower(name: str) -> str:
    return normalize_project_name(name).lower()


class BoardProjectService:
    """Scoped CRUD for BoardProject rows."""

    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session = session
        self.user_id = user_id

    def ensure_shared_project(self) -> BoardProject:
        """Return the user's Shared folder, creating it if missing."""
        row = self.session.exec(
            select(BoardProject).where(
                BoardProject.user_id == self.user_id,
                BoardProject.name_lower == SHARED_NAME_LOWER,
            )
        ).first()
        if row:
            return row
        now = datetime.now(timezone.utc)
        row = BoardProject(
            user_id=self.user_id,
            name=SHARED_PROJECT_NAME,
            name_lower=SHARED_NAME_LOWER,
            sort_order=0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def touch_project(self, project_id: uuid.UUID) -> None:
        """Bump updated_at when a board in the folder changes (caller commits)."""
        proj = self.session.get(BoardProject, project_id)
        if not proj or proj.user_id != self.user_id:
            return
        proj.updated_at = datetime.now(timezone.utc)
        self.session.add(proj)

    def list_projects(self) -> List[BoardProject]:
        """All folders for this user, including Shared, ordered for display."""
        self.ensure_shared_project()
        return list(
            self.session.exec(
                select(BoardProject)
                .where(BoardProject.user_id == self.user_id)
                .order_by(col(BoardProject.sort_order), col(BoardProject.name_lower))
            ).all()
        )

    def count_boards(self, project_id: uuid.UUID) -> int:
        shared = self.ensure_shared_project()
        if project_id == shared.id:
            n = self.session.exec(
                select(func.count(col(SandboxBoard.id))).where(
                    SandboxBoard.user_id == self.user_id,
                    SandboxBoard.is_system == False,  # noqa: E712
                    (SandboxBoard.project_id == project_id) | (SandboxBoard.project_id == None),  # noqa: E711
                )
            ).one()
        else:
            n = self.session.exec(
                select(func.count(col(SandboxBoard.id))).where(SandboxBoard.project_id == project_id)
            ).one()
        return int(n)

    def get_project(self, project_id: uuid.UUID) -> Optional[BoardProject]:
        row = self.session.get(BoardProject, project_id)
        if not row or row.user_id != self.user_id:
            return None
        return row

    def create_project(self, data: BoardProjectCreate) -> BoardProject:
        name = normalize_project_name(data.name)
        nl = project_name_lower(name)
        if nl == SHARED_NAME_LOWER:
            raise ValueError("Reserved project name")
        existing = self.session.exec(
            select(BoardProject).where(
                BoardProject.user_id == self.user_id,
                BoardProject.name_lower == nl,
            )
        ).first()
        if existing:
            raise ValueError("A project with that name already exists")

        max_so = self.session.exec(
            select(func.max(BoardProject.sort_order)).where(BoardProject.user_id == self.user_id)
        ).one()
        next_order = (max_so if max_so is not None else -1) + 1
        if data.sort_order is not None:
            next_order = data.sort_order

        now = datetime.now(timezone.utc)
        row = BoardProject(
            user_id=self.user_id,
            name=name,
            name_lower=nl,
            sort_order=next_order,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def update_project(self, project_id: uuid.UUID, data: BoardProjectUpdate) -> Optional[BoardProject]:
        row = self.get_project(project_id)
        if not row:
            return None
        if row.name_lower == SHARED_NAME_LOWER:
            if data.name is not None:
                raise ValueError("Reserved project name")
        elif data.name is not None:
            name = normalize_project_name(data.name)
            nl = project_name_lower(name)
            if nl == SHARED_NAME_LOWER:
                raise ValueError("Reserved project name")
            conflict = self.session.exec(
                select(BoardProject).where(
                    BoardProject.user_id == self.user_id,
                    BoardProject.name_lower == nl,
                    BoardProject.id != project_id,
                )
            ).first()
            if conflict:
                raise ValueError("A project with that name already exists")
            row.name = name
            row.name_lower = nl

        if data.sort_order is not None:
            row.sort_order = data.sort_order
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def delete_project(self, project_id: uuid.UUID, *, delete_boards: bool = False) -> bool:
        row = self.get_project(project_id)
        if not row:
            return False
        if row.name_lower == SHARED_NAME_LOWER:
            raise ValueError("Cannot delete Shared folder")
        boards = list(
            self.session.exec(select(SandboxBoard).where(SandboxBoard.project_id == project_id)).all()
        )
        if boards and not delete_boards:
            raise ValueError(
                "Project is not empty; pass delete_boards=true to delete all boards in this project."
            )
        if delete_boards:
            from app.domain.services.board_service import BoardService

            board_svc = BoardService(self.session, self.user_id)
            for board in boards:
                board_svc.delete_board(board.id)
        self.session.delete(row)
        self.session.commit()
        return True

    def resolve_project_id(self, project_id: Optional[uuid.UUID]) -> uuid.UUID:
        """Return a valid owned project id, defaulting to Shared."""
        shared = self.ensure_shared_project()
        if project_id is None:
            return shared.id
        proj = self.get_project(project_id)
        if proj:
            return proj.id
        return shared.id
