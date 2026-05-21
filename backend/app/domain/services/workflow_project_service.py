"""
Workflow Project Service
========================
CRUD for per-user workflow folders. The reserved **Shared** folder is created
per user and holds default and unassigned workflows.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.domain.schemas import WorkflowProjectCreate, WorkflowProjectUpdate
from app.persistence.tables import WorkflowDefinition, WorkflowProject

SHARED_PROJECT_NAME = "Shared"
SHARED_NAME_LOWER = "shared"


def normalize_project_name(name: str) -> str:
    return name.strip()


def project_name_lower(name: str) -> str:
    return normalize_project_name(name).lower()


class WorkflowProjectService:
    """Scoped CRUD for WorkflowProject rows."""

    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session = session
        self.user_id = user_id

    def ensure_shared_project(self) -> WorkflowProject:
        """Return the user's Shared folder, creating it if missing."""
        row = self.session.exec(
            select(WorkflowProject).where(
                WorkflowProject.user_id == self.user_id,
                WorkflowProject.name_lower == SHARED_NAME_LOWER,
            )
        ).first()
        if row:
            return row
        now = datetime.now(timezone.utc)
        # Shared is always first in manual order.
        row = WorkflowProject(
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
        """Bump updated_at when a workflow in the folder changes (caller commits)."""
        proj = self.session.get(WorkflowProject, project_id)
        if not proj or proj.user_id != self.user_id:
            return
        proj.updated_at = datetime.now(timezone.utc)
        self.session.add(proj)

    def list_projects(self) -> List[WorkflowProject]:
        """All folders for this user, including Shared, ordered for display."""
        self.ensure_shared_project()
        return list(
            self.session.exec(
                select(WorkflowProject)
                .where(WorkflowProject.user_id == self.user_id)
                .order_by(col(WorkflowProject.sort_order), col(WorkflowProject.name_lower))
            ).all()
        )

    def count_workflows(self, project_id: uuid.UUID) -> int:
        n = self.session.exec(
            select(func.count(col(WorkflowDefinition.id))).where(WorkflowDefinition.project_id == project_id)
        ).one()
        return int(n)

    def get_project(self, project_id: uuid.UUID) -> Optional[WorkflowProject]:
        row = self.session.get(WorkflowProject, project_id)
        if not row or row.user_id != self.user_id:
            return None
        return row

    def create_project(self, data: WorkflowProjectCreate) -> WorkflowProject:
        name = normalize_project_name(data.name)
        nl = project_name_lower(name)
        if nl == SHARED_NAME_LOWER:
            raise ValueError("Reserved project name")
        existing = self.session.exec(
            select(WorkflowProject).where(
                WorkflowProject.user_id == self.user_id,
                WorkflowProject.name_lower == nl,
            )
        ).first()
        if existing:
            raise ValueError("A project with that name already exists")

        max_so = self.session.exec(
            select(func.max(WorkflowProject.sort_order)).where(WorkflowProject.user_id == self.user_id)
        ).one()
        next_order = (max_so if max_so is not None else -1) + 1
        if data.sort_order is not None:
            next_order = data.sort_order

        now = datetime.now(timezone.utc)
        row = WorkflowProject(
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

    def update_project(self, project_id: uuid.UUID, data: WorkflowProjectUpdate) -> Optional[WorkflowProject]:
        row = self.get_project(project_id)
        if not row:
            return None
        if row.name_lower == SHARED_NAME_LOWER:
            # Allow sort_order only for Shared
            if data.name is not None:
                raise ValueError("Reserved project name")
        elif data.name is not None:
            name = normalize_project_name(data.name)
            nl = project_name_lower(name)
            if nl == SHARED_NAME_LOWER:
                raise ValueError("Reserved project name")
            conflict = self.session.exec(
                select(WorkflowProject).where(
                    WorkflowProject.user_id == self.user_id,
                    WorkflowProject.name_lower == nl,
                    WorkflowProject.id != project_id,
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

    def delete_project(self, project_id: uuid.UUID, *, delete_workflows: bool = False) -> bool:
        row = self.get_project(project_id)
        if not row:
            return False
        if row.name_lower == SHARED_NAME_LOWER:
            raise ValueError("Cannot delete Shared folder")
        wfs = list(
            self.session.exec(select(WorkflowDefinition).where(WorkflowDefinition.project_id == project_id)).all()
        )
        if wfs and not delete_workflows:
            raise ValueError(
                "Project is not empty; pass delete_workflows=true to delete all workflows in this project."
            )
        if delete_workflows:
            from app.domain.services.workflow_definition_service import WorkflowDefinitionService

            wf_svc = WorkflowDefinitionService(self.session, self.user_id)
            for wf in wfs:
                wf_svc.delete_workflow(wf.id)
        self.session.delete(row)
        self.session.commit()
        return True
