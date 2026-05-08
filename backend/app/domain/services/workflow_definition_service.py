"""
Workflow Definition Service
============================
CRUD operations for WorkflowDefinitions, scoped to the requesting user.
Workflow graphs are stored as opaque JSON — validation happens at run-time
in the executor.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Session, col, or_, select

from app.domain.schemas import WorkflowDefinitionCreate, WorkflowDefinitionUpdate
from app.domain.services.workflow_project_service import WorkflowProjectService
from app.persistence.tables import WorkflowDefinition

# Current persisted graph schema; written on create/update when absent.
GRAPH_SCHEMA_VERSION = 1


def normalize_workflow_graph(graph: dict | None) -> dict:
    """Return a graph dict with schema_version set for new writes (legacy graphs: implicit v1)."""
    if not graph:
        return {"nodes": [], "edges": [], "schema_version": GRAPH_SCHEMA_VERSION}
    merged = {**graph}
    if merged.get("schema_version") is None:
        merged["schema_version"] = GRAPH_SCHEMA_VERSION
    return merged


class WorkflowDefinitionService:
    """Scoped CRUD service for WorkflowDefinitions.

    Rows with user_id NULL (legacy / pre-ownership data) are visible to any
    logged-in user, similar to system-level Personas. Saving assigns ownership.
    """

    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session = session
        self.user_id = user_id

    def _ownership_clause(self):
        """Match workflows owned by this user or not yet assigned to a user."""
        return or_(
            WorkflowDefinition.user_id == self.user_id,
            WorkflowDefinition.user_id.is_(None),  # noqa: E711
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_workflow(self, id: uuid.UUID) -> Optional[WorkflowDefinition]:
        """Return a WorkflowDefinition by ID if this user may access it."""
        return self.session.exec(
            select(WorkflowDefinition).where(
                WorkflowDefinition.id == id,
                or_(
                    self._ownership_clause(),
                    WorkflowDefinition.is_system == True,  # noqa: E712
                ),
            )
        ).first()

    def list_workflows(self) -> List[WorkflowDefinition]:
        """Return all WorkflowDefinitions visible to this user, newest first."""
        return list(
            self.session.exec(
                select(WorkflowDefinition)
                .where(self._ownership_clause())
                .order_by(col(WorkflowDefinition.updated_at).desc(), col(WorkflowDefinition.id))
            ).all()
        )

    def claim_orphan_if_needed(self, wf: WorkflowDefinition) -> None:
        """Persist ownership for legacy rows (user_id NULL) and assign project for orphans."""
        if getattr(wf, "is_system", False):
            return
        changed = False
        if wf.user_id is None:
            wf.user_id = self.user_id
            wf.updated_at = datetime.now(timezone.utc)
            changed = True
        if wf.user_id == self.user_id and wf.project_id is None:
            proj_svc = WorkflowProjectService(self.session, self.user_id)
            shared = proj_svc.ensure_shared_project()
            wf.project_id = shared.id
            changed = True
        if changed:
            self.session.add(wf)
            self.session.commit()
            self.session.refresh(wf)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create_workflow(self, data: WorkflowDefinitionCreate) -> WorkflowDefinition:
        """Create and persist a new WorkflowDefinition."""
        proj_svc = WorkflowProjectService(self.session, self.user_id)
        shared = proj_svc.ensure_shared_project()
        payload = data.model_dump()
        payload["graph"] = normalize_workflow_graph(payload.get("graph"))
        pid = payload.pop("project_id", None)
        if pid is None:
            pid = shared.id
        else:
            if proj_svc.get_project(pid) is None:
                raise ValueError("Invalid project")
        wf = WorkflowDefinition(**payload, user_id=self.user_id, project_id=pid)
        self.session.add(wf)
        self.session.commit()
        self.session.refresh(wf)
        proj_svc.touch_project(pid)
        self.session.commit()
        self.session.refresh(wf)
        return wf

    def update_workflow(self, id: uuid.UUID, data: WorkflowDefinitionUpdate) -> Optional[WorkflowDefinition]:
        """Update a user-owned WorkflowDefinition. Returns None if not found."""
        proj_svc = WorkflowProjectService(self.session, self.user_id)
        wf = self.get_workflow(id)
        if not wf:
            return None

        if getattr(wf, "is_system", False):
            return None

        if wf.user_id is None:
            wf.user_id = self.user_id

        payload = data.model_dump(exclude_unset=True)
        if "project_id" in payload:
            new_pid = payload["project_id"]
            if new_pid is not None and proj_svc.get_project(new_pid) is None:
                # Orphan or other-user folder id (e.g. after ownership claim): assign Shared.
                new_pid = proj_svc.ensure_shared_project().id
                payload["project_id"] = new_pid

        for key, value in payload.items():
            if key == "graph" and value is not None:
                value = normalize_workflow_graph(value)
            setattr(wf, key, value)
        wf.updated_at = datetime.now(timezone.utc)

        self.session.add(wf)
        if wf.project_id:
            proj_svc.touch_project(wf.project_id)
        self.session.commit()
        self.session.refresh(wf)
        return wf

    def delete_workflow(self, id: uuid.UUID) -> bool:
        """Delete a user-owned WorkflowDefinition. Returns False if not found."""
        wf = self.get_workflow(id)
        if not wf:
            return False
        if getattr(wf, "is_system", False):
            return False
        self.session.delete(wf)
        self.session.commit()
        return True
